"""
Audio file conversion functionality.
"""

import os
import subprocess
import logging
import time
import re
from concurrent.futures import ProcessPoolExecutor
from typing import List, Tuple, Optional

from ..utils.resource_manager import (
    managed_processing, get_signal_handler, get_timeout_manager
)
from ..utils.file_utils import get_audio_duration
from ..utils.progress_tracker import format_file_status
from ..exceptions import (
    DependencyError, ConversionError, FileProcessingError,
    ProcessingError, ConcatenationError
)


class AudioConverter:
    """Handles audio file conversion operations."""
    
    def __init__(self, bitrate="128k", cores=None):
        """
        Initialize the audio converter.
        
        Args:
            bitrate (str): Target bitrate for conversion
            cores (int): Number of CPU cores to use
        """
        self.bitrate = bitrate
        self.cores = cores or os.cpu_count() or 4
        
        # Check for optional dependencies
        try:
            from pydub import AudioSegment
            self.pydub_available = True
        except ImportError:
            self.pydub_available = False
    
    def check_ffmpeg_dependency(self):
        """
        Check if FFmpeg is available and accessible.
        
        Raises:
            DependencyError: If FFmpeg is not found or not accessible.
        """
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, text=True)
            logging.info('FFmpeg dependency check passed')
            
            # Extract version information
            version_line = result.stderr.split('\n')[0] if result.stderr else result.stdout.split('\n')[0]
            return version_line
            
        except FileNotFoundError:
            raise DependencyError(
                "ffmpeg",
                "FFmpeg is not installed or not found in system PATH"
            )
        except subprocess.CalledProcessError as e:
            raise DependencyError(
                "ffmpeg", 
                f"FFmpeg is installed but not working properly: {e}"
            )
    
    def process_audio_files(self, input_files: List[str], output_file: str, 
                           bitrate: str, cores: int, progress_tracker=None,
                           resume_mode: str = "auto") -> Tuple[List[int], List[Exception]]:
        """
        Process audio files with comprehensive resource management and resume functionality.
        
        Args:
            input_files: List of paths to input audio files
            output_file: Path to output audio file
            bitrate: Bitrate for conversion
            cores: Number of CPU cores to use
            progress_tracker: Progress tracking instance
            resume_mode: Resume behavior - 'auto', 'never', or 'force'
            
        Returns:
            tuple: (durations_list, errors_list) - Successfully processed durations and any errors
        """
        from .concatenator import AudioConcatenator
        
        # Handle resume modes and create temporary directory
        temp_dir = self._setup_temp_directory(input_files, output_file, bitrate, resume_mode)
        
        # Check for existing conversions
        existing_conversions = self._check_existing_conversions(
            input_files, temp_dir, resume_mode
        )
        
        # Handle different resume modes
        if resume_mode == "force" and not existing_conversions:
            raise ProcessingError("Resume forced but no resumable work found", "resume_validation")
        
        # Notify user of resume scenario
        if existing_conversions and resume_mode != "never":
            total_files = len(input_files)
            logging.info(f"Resume detected: {len(existing_conversions)}/{total_files} files already converted")
            if not progress_tracker:
                print(f"Resume detected: {len(existing_conversions)}/{total_files} files already converted")
                print(f"Skipping {len(existing_conversions)} files, converting {total_files - len(existing_conversions)} remaining files")
        
        # Use managed processing context
        with managed_processing(input_files, temp_dir=temp_dir, monitor_resources=True) as context:
            temp_dir = context['temp_dir']
            resource_monitor = context['resource_monitor']
            requirements = context['requirements']
            
            converted_files = []
            durations = []
            processing_errors = []
            
            # Register cleanup callback
            signal_handler = get_signal_handler()
            signal_handler.add_cleanup_callback(lambda: self._cleanup_temp_files(temp_dir))
            
            try:
                if not progress_tracker:
                    print(f"\nConverting {len(input_files)} audio files...")
                    print(f"Using temporary directory: {temp_dir}")
                    print(f"Using {cores} CPU cores")
                    print(f"Estimated memory usage: {requirements['estimated_memory_mb']}MB")
                    print(f"Estimated temp space: {requirements['estimated_temp_space_mb']}MB")
                
                # Convert files with progress tracking
                converted_files, durations, processing_errors = self._convert_files_parallel(
                    input_files, temp_dir, bitrate, cores, progress_tracker, 
                    signal_handler, resource_monitor
                )
                
                # Concatenate files
                if converted_files:
                    concatenator = AudioConcatenator()
                    concatenator.concatenate_audio_files(converted_files, output_file, temp_dir)
                
                return durations, processing_errors
                
            except Exception as e:
                processing_errors.append(e)
                logging.error(f'Error during audio processing: {str(e)}')
                raise
    
    def _setup_temp_directory(self, input_files: List[str], output_file: str, 
                             bitrate: str, resume_mode: str) -> str:
        """Set up temporary directory for processing."""
        from ..utils.file_utils import create_predictable_temp_dir, cleanup_old_cache_directories
        
        # Clean up old cache directories
        try:
            removed, freed_mb = cleanup_old_cache_directories(max_age_days=30)
            if removed > 0:
                logging.info(f"Automatic cache cleanup: removed {removed} old directories, freed {freed_mb:.1f}MB")
        except Exception as e:
            logging.warning(f"Cache cleanup failed: {e}")
        
        # Create predictable temp directory
        temp_dir = create_predictable_temp_dir(input_files, output_file, bitrate)
        
        if resume_mode == "never":
            # Force fresh start
            if os.path.exists(temp_dir):
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                    logging.info("Cleared previous job directory due to --resume never")
                except Exception as e:
                    logging.warning(f"Failed to clear previous job directory: {e}")
        
        # Ensure directory exists
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir
    
    def _check_existing_conversions(self, input_files: List[str], temp_dir: str,
                                   resume_mode: str) -> List[str]:
        """Check for existing conversion files."""
        from ..utils.file_utils import validate_receipt_file
        
        if resume_mode == "never":
            return []
        
        existing_conversions = []
        for input_file in input_files:
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            temp_file = os.path.join(temp_dir, f"{base_name}_converted.m4a")
            if os.path.exists(temp_file) and validate_receipt_file(input_file, temp_dir):
                existing_conversions.append(input_file)
        
        return existing_conversions
    
    def _convert_files_parallel(self, input_files: List[str], temp_dir: str, 
                               bitrate: str, cores: int, progress_tracker,
                               signal_handler, resource_monitor) -> Tuple[List[str], List[int], List[Exception]]:
        """Convert files in parallel with error handling."""
        converted_files = []
        durations = []
        processing_errors = []
        
        # Progress tracking setup
        if progress_tracker:
            conversion_context = progress_tracker.conversion_progress(len(input_files))
        else:
            from contextlib import nullcontext
            conversion_context = nullcontext()
        
        with conversion_context as conversion_progress:
            with ProcessPoolExecutor(max_workers=cores) as executor:
                # Create tasks
                future_to_file = {
                    executor.submit(self._convert_file_for_concatenation, input_file, temp_dir, bitrate): input_file
                    for input_file in input_files
                }
                
                # Process results
                completed = 0
                successful = 0
                for future in future_to_file:
                    input_file = future_to_file[future]
                    
                    # Check for shutdown
                    if signal_handler.check_shutdown_requested():
                        if progress_tracker:
                            conversion_progress.set_description("Shutdown requested - cancelling...")
                        else:
                            print("\nShutdown requested, cancelling remaining tasks...")
                        break
                    
                    # Check memory usage periodically
                    if completed % 5 == 0:
                        resource_monitor.check_memory_limit()
                    
                    try:
                        temp_file_path, duration_ms = future.result()
                        converted_files.append(temp_file_path)
                        durations.append(duration_ms)
                        successful += 1
                        
                        if progress_tracker:
                            status_msg = format_file_status(input_file, "OK")
                            conversion_progress.update(1, status_msg)
                        else:
                            print(f"[OK] Converted {os.path.basename(input_file)}")
                            
                    except FileProcessingError as e:
                        processing_errors.append(e)
                        if progress_tracker:
                            status_msg = format_file_status(input_file, "FAIL")
                            conversion_progress.update(1, status_msg)
                        else:
                            print(f"[FAIL] Failed to convert {os.path.basename(input_file)}: {e}")
                        logging.warning(f"Skipping file due to conversion error: {e}")
                        
                    except Exception as e:
                        wrapped_error = ProcessingError(f"Unexpected error: {str(e)}", "conversion", recoverable=False)
                        processing_errors.append(wrapped_error)
                        if progress_tracker:
                            status_msg = format_file_status(input_file, "ERROR")
                            conversion_progress.update(1, status_msg)
                        else:
                            print(f"[ERROR] Unexpected error with {os.path.basename(input_file)}: {e}")
                        logging.error(f"Unexpected error during conversion: {e}")
                    
                    completed += 1
                    if not progress_tracker:
                        print(f"Progress: {completed}/{len(input_files)} files processed ({successful} successful)")
        
        # Validate results
        if not converted_files:
            raise ProcessingError("No files were successfully converted", "conversion", recoverable=False)
        elif len(converted_files) < len(input_files):
            print(f"\nWarning: Only {len(converted_files)}/{len(input_files)} files converted successfully")
            print("Proceeding with available files...")
        
        return converted_files, durations, processing_errors
    
    def _convert_file_for_concatenation(self, input_file: str, temp_dir: str, 
                                       bitrate: str = "128k") -> Tuple[str, int]:
        """
        Convert an audio file to AAC format for concatenation with resume functionality.
        
        Args:
            input_file: Path to the input audio file
            temp_dir: Directory for temporary files
            bitrate: Output bitrate
            
        Returns:
            tuple: (temp_file_path, duration_in_ms)
        """
        from ..utils.file_utils import validate_receipt_file, create_receipt_file
        
        try:
            # Generate temporary file path
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            temp_file = os.path.join(temp_dir, f"{base_name}_converted.m4a")
            
            # Check for existing conversion
            if os.path.exists(temp_file) and validate_receipt_file(input_file, temp_dir):
                try:
                    if self.pydub_available:
                        from pydub import AudioSegment
                        audio = AudioSegment.from_file(temp_file)
                        duration_ms = len(audio)
                    else:
                        duration_ms = get_audio_duration(temp_file)
                    
                    logging.info(f'Resuming: {input_file} already converted (duration: {duration_ms}ms)')
                    return temp_file, duration_ms
                    
                except Exception as e:
                    logging.warning(f'Failed to read existing converted file {temp_file}: {e}')
                    self._cleanup_corrupted_conversion(temp_file, temp_dir, base_name)
            
            # Perform conversion
            logging.info(f'Converting {input_file} for concatenation')
            
            if self.pydub_available:
                duration_ms = self._convert_with_pydub(input_file, temp_file, bitrate)
            else:
                duration_ms = self._convert_with_ffmpeg(input_file, temp_file, bitrate)
            
            # Create receipt file
            create_receipt_file(input_file, temp_dir)
            
            logging.info(f'Converted {input_file} to {temp_file}, duration: {duration_ms}ms')
            return temp_file, duration_ms
            
        except Exception as e:
            logging.error(f'Error converting {input_file}: {str(e)}')
            raise ConversionError(f"Conversion failed: {str(e)}", input_file, 
                                  source_format=os.path.splitext(input_file)[1], 
                                  target_format=".m4a") from e
    
    def _convert_with_pydub(self, input_file: str, output_file: str, bitrate: str) -> int:
        """Convert using pydub."""
        from pydub import AudioSegment
        
        audio = AudioSegment.from_file(input_file)
        audio.export(
            output_file, 
            format="ipod",  # M4A/M4B compatible format
            bitrate=bitrate,
            parameters=["-ar", "44100", "-ac", "2"]
        )
        return len(audio)
    
    def _convert_with_ffmpeg(self, input_file: str, output_file: str, bitrate: str) -> int:
        """Convert using FFmpeg."""
        try:
            return self._convert_with_ffmpeg_progress(input_file, output_file, bitrate)
        except Exception as e:
            logging.warning(f"FFmpeg progress tracking failed: {e}, trying basic conversion")
            return self._convert_with_basic_ffmpeg(input_file, output_file, bitrate)
    
    def _convert_with_ffmpeg_progress(self, input_file: str, output_file: str, bitrate: str) -> int:
        """Convert with FFmpeg progress tracking."""
        total_duration_ms = get_audio_duration(input_file)
        total_duration_seconds = total_duration_ms / 1000.0
        
        ffmpeg_command = [
            'ffmpeg', '-y', '-i', input_file, '-vn', '-c:a', 'aac', 
            '-b:a', f'{bitrate}', '-ar', '44100', '-ac', '2', output_file,
            '-loglevel', 'error', '-stats'
        ]
        
        process = subprocess.Popen(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Progress tracking patterns
        time_pattern = re.compile(r'time[=\s]*(\d{2}):(\d{2}):(\d{2}(?:\.\d{2,3})?)')
        
        try:
            for line in iter(process.stderr.readline, ''):
                if not line:
                    continue
                    
                logging.debug(f"FFmpeg stderr: {line.strip()}")
                
                # Parse progress (simplified for multiprocessing)
                time_match = time_pattern.search(line)
                if time_match and total_duration_seconds > 0:
                    hours, minutes, seconds = time_match.groups()
                    current_seconds = float(hours) * 3600 + float(minutes) * 60 + float(seconds)
                    progress_percent = min(100.0, (current_seconds / total_duration_seconds) * 100)
                    # Progress emission disabled in multiprocessing
            
            process.wait(timeout=300)  # 5 minute timeout
            
            if process.returncode != 0:
                stderr_output = process.stderr.read()
                raise ConversionError(f"FFmpeg conversion failed: {stderr_output}", input_file)
                
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise ConversionError("FFmpeg conversion timed out after 5 minutes", input_file)
        except Exception as e:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
        
        return get_audio_duration(input_file)
    
    def _convert_with_basic_ffmpeg(self, input_file: str, output_file: str, bitrate: str) -> int:
        """Basic FFmpeg conversion without progress tracking."""
        ffmpeg_command = [
            'ffmpeg', '-y', '-i', input_file, '-vn', '-c:a', 'aac', 
            '-b:a', f'{bitrate}', '-ar', '44100', '-ac', '2', output_file,
            '-loglevel', 'error'
        ]
        
        try:
            result = subprocess.run(
                ffmpeg_command,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                raise ConversionError(f"FFmpeg conversion failed: {result.stderr}", input_file)
                
            return get_audio_duration(input_file)
            
        except subprocess.TimeoutExpired:
            raise ConversionError("FFmpeg conversion timed out after 5 minutes", input_file)
        except Exception as e:
            raise ConversionError(f"FFmpeg conversion error: {str(e)}", input_file)
    
    def _cleanup_corrupted_conversion(self, temp_file: str, temp_dir: str, base_name: str):
        """Clean up corrupted conversion files."""
        try:
            os.remove(temp_file)
            receipt_file = os.path.join(temp_dir, f"{base_name}.receipt")
            if os.path.exists(receipt_file):
                os.remove(receipt_file)
        except Exception:
            pass
    
    def _cleanup_temp_files(self, temp_dir: str):
        """Clean up temporary files."""
        if temp_dir and os.path.exists(temp_dir):
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception as e:
                logging.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")