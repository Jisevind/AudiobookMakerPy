"""
Audio file concatenation functionality.
"""

import os
import subprocess
import logging
from typing import List

from ..exceptions import ConcatenationError


class AudioConcatenator:
    """Handles audio file concatenation operations."""
    
    def __init__(self):
        """Initialize the audio concatenator."""
        pass
    
    def concatenate_audio_files(self, converted_files: List[str], output_file: str, temp_dir: str):
        """
        Concatenate audio files using streaming architecture for memory efficiency.
        
        Args:
            converted_files: List of temporary converted file paths
            output_file: Path for the final output file
            temp_dir: Temporary directory for intermediate files
            
        Raises:
            ConcatenationError: If concatenation fails
        """
        try:
            self._concatenate_with_ffmpeg(converted_files, output_file, temp_dir)
        except Exception as e:
            logging.error(f'Concatenation failed: {str(e)}')
            raise ConcatenationError(f"Audio concatenation failed: {str(e)}") from e
    
    def _concatenate_with_ffmpeg(self, converted_files: List[str], output_file: str, temp_dir: str):
        """
        Concatenate audio files using FFmpeg concat demuxer with memory pressure monitoring.
        
        Args:
            converted_files: List of converted file paths
            output_file: Output file path
            temp_dir: Temporary directory
        """
        logging.info(f'Concatenating {len(converted_files)} files using FFmpeg streaming architecture')
        
        # Memory pressure detection before concatenation
        try:
            from ..utils.resource_manager import ResourceMonitor
            monitor = ResourceMonitor()
            memory_stats = monitor.get_current_memory_usage()
            logging.info(f"Pre-concatenation memory usage: {memory_stats['percent']:.1f}% "
                        f"({memory_stats['rss_mb']:.1f}MB used)")
            
            # Check if we're approaching memory limits
            if memory_stats['percent'] > 80:
                logging.warning(f"High memory usage detected ({memory_stats['percent']:.1f}%) before concatenation")
                logging.info("FFmpeg streaming concatenation will help maintain low memory usage")
        except ImportError:
            logging.debug("Resource monitoring not available for concatenation")
            monitor = None
            memory_stats = None
        
        # Create concat list file with proper escaping
        concat_file = os.path.join(temp_dir, 'concat_list.txt')
        with open(concat_file, 'w', encoding='utf-8') as f:
            for temp_file in converted_files:
                # Escape file paths for FFmpeg
                escaped_path = temp_file.replace('\\', '/').replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
        
        # Remove existing output file to avoid overwrite prompts
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except PermissionError:
                logging.warning(f'Could not remove existing {output_file}, FFmpeg will overwrite')
        
        # Use streaming concat demuxer for constant memory usage
        ffmpeg_concat_command = [
            'ffmpeg', 
            '-y',  # Automatically overwrite existing files
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',  # Copy streams without re-encoding (streaming)
            '-movflags', '+faststart',  # Optimize for streaming
            output_file
        ]
        
        logging.debug(f'Running FFmpeg streaming command: {" ".join(ffmpeg_concat_command)}')
        
        # Monitor memory during concatenation operation
        try:
            result = subprocess.run(ffmpeg_concat_command, capture_output=True, text=True)
            
            # Post-concatenation memory check
            if monitor and memory_stats:
                try:
                    post_memory = monitor.get_current_memory_usage()
                    logging.info(f"Post-concatenation memory usage: {post_memory['percent']:.1f}% "
                                f"({post_memory['rss_mb']:.1f}MB used)")
                    
                    # Verify streaming architecture maintained low memory usage
                    memory_increase = post_memory['rss_mb'] - memory_stats['rss_mb']
                    if memory_increase < 100:  # Less than 100MB increase is expected for streaming
                        logging.info(f"Streaming concatenation successful: only {memory_increase:.1f}MB memory increase")
                    else:
                        logging.warning(f"Higher than expected memory increase: {memory_increase:.1f}MB")
                        
                except Exception as e:
                    logging.debug(f"Post-concatenation memory check failed: {e}")
                    
        except Exception as e:
            logging.error(f'FFmpeg concatenation failed: {e}')
            raise ConcatenationError(f"FFmpeg concatenation failed: {e}")
        
        if result.returncode != 0:
            logging.error(f'FFmpeg concatenation failed: {result.stderr}')
            raise ConcatenationError(f"FFmpeg concatenation failed: {result.stderr}")
        
        logging.info(f'Successfully concatenated {len(converted_files)} files to {output_file} using streaming architecture')