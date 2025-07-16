"""
Main audiobook processor orchestrating the conversion workflow.
"""

import os
import sys
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from .converter import AudioConverter
from .concatenator import AudioConcatenator  
from .metadata import MetadataExtractor, MetadataWriter
from ..utils.validation import AudioFileValidator, ValidationLevel, validate_audio_files
from ..utils.progress_tracker import format_file_status
from ..exceptions import (
    AudiobookMakerError, DependencyError, ProcessingError, 
    ConfigurationError, ValidationError
)


@dataclass
class ProcessingResult:
    """Result of audiobook processing."""
    success: bool
    output_file: Optional[str] = None
    total_hours: int = 0
    total_minutes: int = 0
    errors: List[str] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class AudiobookProcessor:
    """Main processor for converting audio files to audiobook format."""
    
    def __init__(self, bitrate="128k", cores=None, validation_level=ValidationLevel.NORMAL,
                 resume_mode="auto", progress_tracker=None, quiet=False, gui_mode=False,
                 json_mode=False):
        """
        Initialize the audiobook processor.
        
        Args:
            bitrate (str): Audio bitrate for conversion
            cores (int): Number of CPU cores to use
            validation_level (ValidationLevel): Validation strictness
            resume_mode (str): Resume behavior ('auto', 'never', 'force')
            progress_tracker: Progress tracking instance
            quiet (bool): Reduce output verbosity
            gui_mode (bool): GUI mode behavior
            json_mode (bool): JSON output mode
        """
        self.bitrate = bitrate
        self.cores = cores or os.cpu_count() or 4
        self.validation_level = validation_level
        self.resume_mode = resume_mode
        self.progress_tracker = progress_tracker
        self.quiet = quiet
        self.gui_mode = gui_mode
        self.json_mode = json_mode
        
        # Initialize components
        self.converter = AudioConverter(bitrate=bitrate, cores=cores)
        self.concatenator = AudioConcatenator()
        self.metadata_extractor = MetadataExtractor()
        self.metadata_writer = MetadataWriter()
        
        # Check dependencies
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check for required dependencies."""
        try:
            self.converter.check_ffmpeg_dependency()
            logging.info('Dependencies check passed')
        except DependencyError as e:
            logging.error(f'Dependency check failed: {e}')
            raise
    
    def process_audiobook(self, input_paths: List[str], output_path: Optional[str] = None,
                         output_dir: Optional[str] = None, output_name: Optional[str] = None,
                         template: str = "{title}", title: Optional[str] = None,
                         author: Optional[str] = None, cover_art_path: Optional[str] = None,
                         chapter_titles_mode: str = "auto") -> ProcessingResult:
        """
        Main processing function to convert audio files to audiobook.
        
        Args:
            input_paths: List of input file/directory paths
            output_path: Explicit output file path
            output_dir: Output directory
            output_name: Custom output filename
            template: Filename template
            title: Custom title
            author: Custom author
            cover_art_path: Path to cover art image
            chapter_titles_mode: How to generate chapter titles
            
        Returns:
            ProcessingResult: Results of the processing operation
        """
        all_errors = []
        
        try:
            # Step 1: Validate and collect input files
            if self.progress_tracker:
                self.progress_tracker.print_step("Scanning input files", 1, 5)
            
            input_files = self._validate_and_get_input_files(input_paths)
            
            if self.json_mode:
                self._emit_log("info", f"Total audio files to process: {len(input_files)}")
            
            # Step 2: Pre-flight validation
            if self.progress_tracker:
                self.progress_tracker.print_step("Pre-flight validation", 2, 5)
            
            valid_files = self._validate_audio_files(input_files)
            
            if len(valid_files) != len(input_files):
                if not valid_files:
                    return ProcessingResult(
                        success=False,
                        error_message="No valid audio files found. Processing cannot continue."
                    )
                
                # Handle partial validation success
                if not self.gui_mode and not self.quiet:
                    response = input(f"Only {len(valid_files)}/{len(input_files)} files passed validation. Continue? (y/N): ").strip().lower()
                    if response not in ['y', 'yes']:
                        return ProcessingResult(
                            success=False,
                            error_message="Operation cancelled by user"
                        )
                
                input_files = valid_files
            
            # Step 3: Extract metadata
            if self.progress_tracker:
                self.progress_tracker.print_step("Extracting metadata", 3, 5)
            
            metadata = self._extract_metadata(input_files, title, author, chapter_titles_mode)
            output_file = self._determine_output_path(input_files, output_path, output_dir, 
                                                    output_name, template, metadata)
            
            # Check for existing output file
            if os.path.exists(output_file):
                if not self.quiet and not self.gui_mode:
                    response = input(f"Output file exists: {output_file}. Overwrite? (y/N): ").strip().lower()
                    if response not in ['y', 'yes']:
                        return ProcessingResult(
                            success=False,
                            error_message="Operation cancelled by user"
                        )
            
            # Step 4: Process audio files
            if self.progress_tracker:
                self.progress_tracker.print_step("Processing audio files", 4, 5)
            
            file_durations, processing_errors = self.converter.process_audio_files(
                input_files, output_file, self.bitrate, self.cores, 
                self.progress_tracker, self.resume_mode
            )
            
            all_errors.extend(processing_errors)
            
            if not file_durations:
                return ProcessingResult(
                    success=False,
                    error_message="No files were successfully processed",
                    errors=[str(e) for e in all_errors]
                )
            
            # Step 5: Add metadata
            if self.progress_tracker:
                self.progress_tracker.print_step("Adding metadata", 5, 5)
            
            try:
                self.metadata_writer.add_metadata_to_audiobook(
                    output_file, input_files, file_durations,
                    metadata=metadata, cover_art_path=cover_art_path,
                    chapter_titles=metadata.get('chapter_titles')
                )
            except Exception as e:
                all_errors.append(str(e))
                logging.warning(f"Metadata processing failed but audiobook was created: {e}")
            
            # Calculate results
            total_duration_ms = sum(file_durations)
            total_hours = total_duration_ms // (1000 * 60 * 60)
            total_minutes = (total_duration_ms % (1000 * 60 * 60)) // (1000 * 60)
            
            return ProcessingResult(
                success=True,
                output_file=output_file,
                total_hours=total_hours,
                total_minutes=total_minutes,
                errors=[str(e) for e in all_errors]
            )
            
        except Exception as e:
            return ProcessingResult(
                success=False,
                error_message=str(e),
                errors=[str(e) for e in all_errors]
            )
    
    def _validate_and_get_input_files(self, input_paths: List[str]) -> List[str]:
        """Validate and collect input files from paths."""
        input_files = []
        supported_extensions = ('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.m4b')
        
        if not self.quiet:
            print(f"Scanning {len(input_paths)} input path(s)...")
        
        for input_path in input_paths:
            if os.path.isdir(input_path):
                folder_files = [
                    os.path.join(input_path, f) 
                    for f in os.listdir(input_path) 
                    if f.lower().endswith(supported_extensions)
                ]
                input_files.extend(folder_files)
                if not self.quiet:
                    print(f"Found {len(folder_files)} audio files in directory: {input_path}")
                    
            elif os.path.isfile(input_path):
                if input_path.lower().endswith(supported_extensions):
                    input_files.append(input_path)
                    if not self.quiet:
                        print(f"Added audio file: {os.path.basename(input_path)}")
                else:
                    if not self.quiet:
                        print(f"Warning: Skipping unsupported file format: {input_path}")
            else:
                raise ValidationError(f"Path does not exist: {input_path}")
        
        if not input_files:
            raise ValidationError("No valid audio files found in the specified paths")
        
        # Sort files naturally
        from ..utils.file_utils import natural_keys
        input_files.sort(key=natural_keys)
        
        if not self.quiet:
            print(f"Total audio files to process: {len(input_files)}")
            if len(input_files) <= 10:
                print("Files to process:")
                for i, file in enumerate(input_files, 1):
                    print(f"   {i:2d}. {os.path.basename(file)}")
        
        return input_files
    
    def _validate_audio_files(self, input_files: List[str]) -> List[str]:
        """Validate audio files."""
        def validation_progress_callback(current, file_path, is_valid):
            status = "OK" if is_valid else "FAIL"
            return format_file_status(file_path, status)
        
        if self.progress_tracker:
            with self.progress_tracker.validation_progress(len(input_files)) as validation_progress:
                def progress_update(current, file_path, is_valid):
                    description = validation_progress_callback(current, file_path, is_valid)
                    validation_progress.update(1, description)
                
                valid_files, validation_report = validate_audio_files(
                    input_files, self.validation_level, progress_update
                )
        else:
            valid_files, validation_report = validate_audio_files(
                input_files, self.validation_level
            )
        
        if len(valid_files) != len(input_files) and not self.quiet:
            print("\n" + "=" * 50)
            print("VALIDATION REPORT")
            print("=" * 50)
            print(validation_report)
            print("=" * 50)
        
        return valid_files
    
    def _extract_metadata(self, input_files: List[str], title: Optional[str], 
                         author: Optional[str], chapter_titles_mode: str) -> Dict[str, Any]:
        """Extract and prepare metadata."""
        metadata = self.metadata_extractor.extract_comprehensive_metadata(input_files)
        
        # Override with user-provided values
        if title:
            metadata['title'] = title
        if author:
            metadata['author'] = author
        
        # Handle chapter titles
        if chapter_titles_mode == 'auto':
            # Use smart extracted titles
            pass
        elif chapter_titles_mode == 'filename':
            metadata['chapter_titles'] = [
                os.path.splitext(os.path.basename(f))[0] for f in input_files
            ]
        else:  # generic
            metadata['chapter_titles'] = [
                f"Chapter {i+1}" for i in range(len(input_files))
            ]
        
        if not self.quiet:
            print(f"Detected metadata - Title: {metadata.get('title', 'N/A')}, Author: {metadata.get('author', 'N/A')}")
            if chapter_titles_mode == 'auto' and metadata.get('chapter_titles'):
                print(f"Smart chapter titles: {len(metadata['chapter_titles'])} extracted")
        
        return metadata
    
    def _determine_output_path(self, input_files: List[str], output_path: Optional[str],
                              output_dir: Optional[str], output_name: Optional[str],
                              template: str, metadata: Dict[str, Any]) -> str:
        """Determine the output file path."""
        if output_path:
            return output_path
        
        if output_dir:
            directory = output_dir
        else:
            directory = os.path.dirname(input_files[0])
        
        if output_name:
            filename = output_name
        else:
            filename = template.format(
                title=metadata.get('title', 'Audiobook'),
                author=metadata.get('author', 'Unknown'),
                album=metadata.get('album', 'Audiobook'),
                year=metadata.get('year', '')
            )
        
        if not filename.lower().endswith('.m4b'):
            filename += '.m4b'
        
        return os.path.join(directory, filename)
    
    def _emit_log(self, level: str, message: str):
        """Emit log message."""
        if self.json_mode:
            import json
            log_data = {
                "type": "log",
                "level": level,
                "message": message
            }
            print(json.dumps(log_data))
        else:
            print(message)