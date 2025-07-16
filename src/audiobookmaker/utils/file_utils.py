"""
File utility functions for audiobook processing.
"""

import os
import subprocess
import tempfile
import hashlib
import time
import json
import logging
import glob
import shutil
import re
from typing import List, Union


def natural_keys(text: str) -> List[Union[int, str]]:
    """
    Natural sorting key function.
    
    Args:
        text: Text to generate natural sort key for
        
    Returns:
        List of integers and strings for natural sorting
    """
    def atoi(text):
        return int(text) if text.isdigit() else text
    return [atoi(c) for c in re.split(r'(\d+)', text)]


def get_audio_duration(input_file: str) -> int:
    """
    Get audio duration in milliseconds using ffprobe.
    
    Args:
        input_file: Path to the input audio file
        
    Returns:
        int: Duration in milliseconds
    """
    try:
        ffprobe_command = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', input_file
        ]
        output = subprocess.check_output(ffprobe_command).decode('utf-8').strip()
        return int(float(output) * 1000)
    except subprocess.CalledProcessError as e:
        logging.error(f'Error getting duration for {input_file}: {str(e)}')
        return 0


def get_audio_duration_ms(input_file: str) -> int:
    """
    Get audio duration in milliseconds using ffprobe.
    
    Args:
        input_file: Path to the input audio file
        
    Returns:
        int: Duration in milliseconds
    """
    return get_audio_duration(input_file)


def create_predictable_temp_dir(input_files: List[str], output_file: str, bitrate: str) -> str:
    """
    Create a predictable temporary directory for resume functionality.
    
    Args:
        input_files: List of input file paths
        output_file: Output file path
        bitrate: Audio bitrate setting
        
    Returns:
        str: Path to the predictable temporary directory
    """
    # Create a hash based on input files, output file, and bitrate
    hasher = hashlib.md5()
    for file_path in sorted(input_files):
        hasher.update(file_path.encode())
    hasher.update(output_file.encode())
    hasher.update(bitrate.encode())
    
    hash_str = hasher.hexdigest()[:12]
    temp_base = tempfile.gettempdir()
    return os.path.join(temp_base, f"audiobookmaker_{hash_str}")


def validate_receipt_file(input_file: str, temp_dir: str) -> bool:
    """
    Validate if a receipt file exists and matches the source file.
    
    Args:
        input_file: Path to the input file
        temp_dir: Temporary directory path
        
    Returns:
        bool: True if receipt is valid, False otherwise
    """
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    receipt_file = os.path.join(temp_dir, f"{base_name}.receipt")
    
    if not os.path.exists(receipt_file):
        return False
    
    try:
        with open(receipt_file, 'r') as f:
            receipt = json.load(f)
        
        # Check if source file modification time matches
        source_mtime = os.path.getmtime(input_file)
        return abs(source_mtime - receipt.get('source_mtime', 0)) < 1.0
    
    except Exception:
        return False


def create_receipt_file(input_file: str, temp_dir: str):
    """
    Create a receipt file for tracking source file state.
    
    Args:
        input_file: Path to the input file
        temp_dir: Temporary directory path
    """
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    receipt_file = os.path.join(temp_dir, f"{base_name}.receipt")
    
    try:
        receipt = {
            'source_file': input_file,
            'source_mtime': os.path.getmtime(input_file),
            'conversion_time': time.time()
        }
        
        with open(receipt_file, 'w') as f:
            json.dump(receipt, f)
    
    except Exception as e:
        logging.warning(f"Failed to create receipt file: {e}")


def cleanup_old_cache_directories(max_age_days: int = 30) -> tuple:
    """
    Clean up old cache directories.
    
    Args:
        max_age_days: Maximum age in days before cleanup
        
    Returns:
        tuple: (number_removed, space_freed_mb)
    """
    temp_base = tempfile.gettempdir()
    pattern = os.path.join(temp_base, "audiobookmaker_*")
    
    removed = 0
    freed_space = 0
    
    try:
        for cache_dir in glob.glob(pattern):
            if os.path.isdir(cache_dir):
                mtime = os.path.getmtime(cache_dir)
                age_days = (time.time() - mtime) / (24 * 3600)
                
                if age_days > max_age_days:
                    size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(cache_dir)
                        for filename in filenames
                    )
                    
                    shutil.rmtree(cache_dir)
                    removed += 1
                    freed_space += size
    
    except Exception as e:
        logging.warning(f"Cache cleanup failed: {e}")
    
    return removed, freed_space / (1024 * 1024)  # Return MB


def cleanup_temp_files(temp_dir: str):
    """
    Clean up temporary files.
    
    Args:
        temp_dir: Temporary directory path
    """
    if temp_dir and os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logging.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")


def get_safe_cpu_default() -> int:
    """
    Get a safe default number of CPU cores for processing.
    
    Returns:
        int: Safe number of CPU cores to use
    """
    return min(4, os.cpu_count() or 2)


def ms_to_timestamp(ms: int) -> str:
    """
    Convert milliseconds to HH:MM:SS.mmm format.
    
    Args:
        ms: Milliseconds
        
    Returns:
        str: Formatted timestamp
    """
    hours = ms // (1000 * 60 * 60)
    minutes = (ms % (1000 * 60 * 60)) // (1000 * 60)
    seconds = (ms % (1000 * 60)) // 1000
    milliseconds = ms % 1000
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        str: Sanitized filename
    """
    # Remove invalid characters for most filesystems
    invalid_chars = r'<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove multiple consecutive underscores
    filename = re.sub(r'_{2,}', '_', filename)
    
    # Remove leading/trailing underscores and spaces
    filename = filename.strip('_ ')
    
    return filename


def ensure_directory_exists(directory: str):
    """
    Ensure that a directory exists, creating it if necessary.
    
    Args:
        directory: Path to the directory
    """
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            logging.error(f"Failed to create directory {directory}: {e}")
            raise


def get_file_size_mb(file_path: str) -> float:
    """
    Get file size in megabytes.
    
    Args:
        file_path: Path to the file
        
    Returns:
        float: File size in MB
    """
    try:
        return os.path.getsize(file_path) / (1024 * 1024)
    except OSError:
        return 0.0


def is_audio_file(file_path: str) -> bool:
    """
    Check if a file is an audio file based on extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        bool: True if it's an audio file, False otherwise
    """
    audio_extensions = {'.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.m4b'}
    return os.path.splitext(file_path)[1].lower() in audio_extensions


def get_directory_size_mb(directory: str) -> float:
    """
    Get total size of a directory in megabytes.
    
    Args:
        directory: Path to the directory
        
    Returns:
        float: Directory size in MB
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(file_path)
                except OSError:
                    continue
    except Exception as e:
        logging.warning(f"Failed to calculate directory size for {directory}: {e}")
    
    return total_size / (1024 * 1024)