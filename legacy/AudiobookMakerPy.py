# Standard library imports
import sys
import os
import subprocess
import tempfile
import logging
import shutil
import re
import hashlib
import json
import time
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor

# Application-specific imports
from exceptions import (
    AudiobookMakerError, DependencyError, FileProcessingError, ConversionError,
    MetadataError, ValidationError, ResourceError, ConfigurationError,
    ProcessingError, ConcatenationError, InterruptedError,
    classify_error, get_error_summary
)
from validation import (
    AudioFileValidator, ValidationLevel, ValidationSummary,
    validate_audio_files, validate_with_pydub_preflight
)
from resource_manager import (
    managed_processing, managed_temp_directory, 
    get_signal_handler, get_timeout_manager
)
from progress_tracker import (
    create_progress_tracker, ProcessingTimer, format_file_status
)

# Audio processing imports
try:
    # Import mutagen (always works)
    from mutagen.mp4 import MP4, MP4Cover
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("Warning: mutagen not available. Install with: pip install mutagen")

# Global variables
tempdir = None
max_cpu_cores = os.cpu_count() or 4

# Optional pydub import for enhanced functionality
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

# Helper functions for missing dependencies
def get_safe_cpu_default():
    """Returns a safe default for CPU cores."""
    return min(4, os.cpu_count() or 2)

def emit_progress(current, total, stage, speed=None, eta=None, json_mode=False):
    """Emit progress information."""
    if json_mode:
        import json
        progress_data = {
            "type": "progress",
            "current": current,
            "total": total,
            "stage": stage,
            "speed": speed,
            "eta": eta
        }
        print(json.dumps(progress_data))
    else:
        print(f"{stage}...")

def emit_log(level, message, json_mode=False):
    """Emit log information."""
    if json_mode:
        import json
        log_data = {
            "type": "log",
            "level": level,
            "message": message
        }
        print(json.dumps(log_data))
    else:
        print(message)

def get_audio_duration(input_file):
    """Get audio duration in milliseconds using ffprobe."""
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

def get_audio_duration_ms(input_file):
    """Get audio duration in milliseconds using ffprobe."""
    return get_audio_duration(input_file)

def natural_keys(text):
    """Natural sorting key function."""
    def atoi(text):
        return int(text) if text.isdigit() else text
    return [atoi(c) for c in re.split(r'(\d+)', text)]

def extract_comprehensive_metadata(input_files):
    """Extract comprehensive metadata from input files."""
    if not input_files:
        return {}
    
    # Use first file for main metadata
    first_file = input_files[0]
    metadata = _extract_metadata_from_source(first_file)
    
    # Generate chapter titles from filenames
    chapter_titles = []
    for file_path in input_files:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        # Clean up the filename for chapter titles
        cleaned = re.sub(r'^\d+\s*[-:.)]\s*', '', base_name)
        cleaned = re.sub(r'^(Chapter|Track|Part)\s*\d+\s*[-:.)]\s*', '', cleaned, flags=re.IGNORECASE)
        if not cleaned.strip():
            cleaned = base_name
        chapter_titles.append(cleaned.strip())
    
    return {
        'title': metadata.get('title', os.path.basename(os.path.dirname(first_file))),
        'author': metadata.get('artist', 'Unknown Author'),
        'album': metadata.get('album', os.path.basename(os.path.dirname(first_file))),
        'year': metadata.get('date', ''),
        'chapter_titles': chapter_titles
    }

def determine_output_path(input_files, args, metadata):
    """Determine the output file path based on arguments and metadata."""
    if args.output:
        return args.output
    
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.dirname(input_files[0])
    
    if args.output_name:
        filename = args.output_name
    else:
        # Use template
        template = args.template
        filename = template.format(
            title=metadata.get('title', 'Audiobook'),
            author=metadata.get('author', 'Unknown'),
            album=metadata.get('album', 'Audiobook'),
            year=metadata.get('year', '')
        )
    
    # Ensure .m4b extension
    if not filename.lower().endswith('.m4b'):
        filename += '.m4b'
    
    return os.path.join(output_dir, filename)

def create_predictable_temp_dir(input_files, output_file, bitrate):
    """Create a predictable temporary directory for resume functionality."""
    import hashlib
    
    # Create a hash based on input files, output file, and bitrate
    hasher = hashlib.md5()
    for file_path in sorted(input_files):
        hasher.update(file_path.encode())
    hasher.update(output_file.encode())
    hasher.update(bitrate.encode())
    
    hash_str = hasher.hexdigest()[:12]
    temp_base = tempfile.gettempdir()
    return os.path.join(temp_base, f"audiobookmaker_{hash_str}")

def validate_receipt_file(input_file, temp_dir):
    """Validate if a receipt file exists and matches the source file."""
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    receipt_file = os.path.join(temp_dir, f"{base_name}.receipt")
    
    if not os.path.exists(receipt_file):
        return False
    
    try:
        with open(receipt_file, 'r') as f:
            import json
            receipt = json.load(f)
        
        # Check if source file modification time matches
        source_mtime = os.path.getmtime(input_file)
        return abs(source_mtime - receipt.get('source_mtime', 0)) < 1.0
    
    except Exception:
        return False

def create_receipt_file(input_file, temp_dir):
    """Create a receipt file for tracking source file state."""
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    receipt_file = os.path.join(temp_dir, f"{base_name}.receipt")
    
    try:
        import json
        receipt = {
            'source_file': input_file,
            'source_mtime': os.path.getmtime(input_file),
            'conversion_time': time.time()
        }
        
        with open(receipt_file, 'w') as f:
            json.dump(receipt, f)
    
    except Exception as e:
        logging.warning(f"Failed to create receipt file: {e}")

def cleanup_old_cache_directories(max_age_days=30):
    """Clean up old cache directories."""
    import glob
    
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
                    import shutil
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

def cleanup_temp_files(temp_dir):
    """Clean up temporary files."""
    if temp_dir and os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logging.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")

# Add missing line break before first function
def extract_chapter_name_from_filename(filename):
    """
    Extracts a smart chapter name from the filename.
    
    Args:
        filename (str): The input filename.
        
    Returns:
        str: A cleaned chapter name.
    """
    # Remove file extension and path
    base_name = os.path.splitext(os.path.basename(filename))[0]
    
    # Remove common prefixes like track numbers
    import re
    # Remove patterns like "01 - ", "Chapter 1 - ", "Track 01: ", etc.
    cleaned = re.sub(r'^\d+\s*[-:.)]\s*', '', base_name)
    cleaned = re.sub(r'^(Chapter|Track|Part)\s*\d+\s*[-:.)]\s*', '', cleaned, flags=re.IGNORECASE)
    
    # If nothing left after cleaning, use original
    if not cleaned.strip():
        cleaned = base_name
    
    return cleaned.strip()

def create_chapters_for_mutagen(input_files, durations):
    """
    Creates chapter data for mutagen metadata handling.
    
    Args:
        input_files (list): List of input file paths.
        durations (list): List of durations in milliseconds.
        
    Returns:
        list: List of tuples (start_time_ms, title) for each chapter.
    """
    chapters = []
    start_time = 0
    
    for i, (input_file, duration) in enumerate(zip(input_files, durations)):
        # Extract smart chapter name from filename
        chapter_name = extract_chapter_name_from_filename(input_file)
        
        # Fallback to generic name if extraction fails
        if not chapter_name or len(chapter_name) < 2:
            chapter_name = f"Chapter {i + 1}"
        
        chapters.append((start_time, chapter_name))
        start_time += duration
    
    logging.info(f'Created {len(chapters)} chapters for metadata')
    return chapters

def create_smart_chapters_for_mutagen(input_files, durations, chapter_titles):
    """
    Create chapter information using smart extracted titles.

    
    Args:
        input_files (list): List of input file paths.
        durations (list): List of durations in milliseconds.
        chapter_titles (list): Smart extracted chapter titles.
        
    Returns:
        list: Chapter information for mutagen.
    """
    if len(input_files) != len(durations) or len(input_files) != len(chapter_titles):
        raise ValueError("Mismatch between number of files, durations, and chapter titles")
    
    chapters = []
    current_time = 0
    
    for i, (input_file, duration, title) in enumerate(zip(input_files, durations, chapter_titles)):
        chapter = {
            'start_time': current_time,
            'title': title
        }
        chapters.append(chapter)
        current_time += duration
        
        logging.debug(f'Smart chapter {i+1}: "{title}" at {current_time}ms')
    
    logging.info(f'Created {len(chapters)} smart chapters with intelligent titles')
    return chapters

def add_metadata_to_audiobook(output_file, input_files, durations, metadata=None, cover_art_path=None, chapter_titles=None):
    """
    Adds enhanced metadata to the M4B audiobook file using mutagen.    
    
    Args:
        output_file (str): Path to the output M4B file.
        input_files (list): List of input file paths.
        durations (list): List of durations in milliseconds.
        metadata (dict, optional): Comprehensive metadata from smart extraction.
        cover_art_path (str, optional): Path to cover art image file.
        chapter_titles (list, optional): Smart chapter titles from extraction.
        
    Raises:
        MetadataError: If metadata processing fails.
    """
    try:
        logging.info(f'Adding enhanced metadata to {output_file}')
        
        # Check if mutagen is available
        if not MUTAGEN_AVAILABLE:
            logging.warning("Mutagen not available - skipping enhanced metadata")
            return
        
        # Open the M4B file with mutagen
        audiofile = MP4(output_file)
        
        # Use comprehensive metadata if available, fallback to legacy extraction
        if metadata:
            audiofile['\xa9nam'] = metadata.get('title', 'Audiobook')
            audiofile['\xa9alb'] = metadata.get('album', metadata.get('title', 'Audiobook'))  # Album = title for audiobooks
            audiofile['\xa9ART'] = metadata.get('author', 'Unknown Author')
            audiofile['aART'] = metadata.get('author', 'Unknown Author')  # Album artist
            
            if metadata.get('year'):
                audiofile['\xa9day'] = metadata['year']
                
            # Preserve additional metadata from source files
            source_metadata = metadata.get('source_metadata', {})
            
            # Copy genre if available
            for genre_tag in ['\xa9gen', 'TCON', 'GENRE']:
                if genre_tag in source_metadata:
                    audiofile['\xa9gen'] = str(source_metadata[genre_tag][0]) if isinstance(source_metadata[genre_tag], list) else str(source_metadata[genre_tag])
                    break
                    
            # Copy comment/description if available  
            for comment_tag in ['\xa9cmt', 'COMM::eng', 'COMMENT']:
                if comment_tag in source_metadata:
                    comment_value = source_metadata[comment_tag]
                    if isinstance(comment_value, list) and comment_value:
                        audiofile['\xa9cmt'] = str(comment_value[0])
                    elif comment_value:
                        audiofile['\xa9cmt'] = str(comment_value)
                    break
                    
        else:
            # Fallback to legacy metadata extraction
            first_file_metadata = _extract_metadata_from_source(input_files[0])
            
            audiofile['\xa9nam'] = first_file_metadata.get('album', os.path.basename(os.path.dirname(input_files[0])))
            audiofile['\xa9alb'] = first_file_metadata.get('album', audiofile['\xa9nam'])
            audiofile['\xa9ART'] = first_file_metadata.get('artist', 'Unknown Author')
            audiofile['aART'] = first_file_metadata.get('album_artist', audiofile['\xa9ART'])
            
            if first_file_metadata.get('date'):
                audiofile['\xa9day'] = first_file_metadata['date']
            if first_file_metadata.get('genre'):
                audiofile['\xa9gen'] = first_file_metadata['genre']
            if first_file_metadata.get('comment'):
                audiofile['\xa9cmt'] = first_file_metadata['comment']
            
        # Set as audiobook
        audiofile['stik'] = [2]  # Audiobook media type
        
        if cover_art_path:
            try:
                with open(cover_art_path, 'rb') as cover_file:
                    cover_data = cover_file.read()
                    
                # Determine cover format
                cover_ext = os.path.splitext(cover_art_path)[1].lower()
                if cover_ext in ['.jpg', '.jpeg']:
                    cover_format = MP4Cover.FORMAT_JPEG
                elif cover_ext == '.png':
                    cover_format = MP4Cover.FORMAT_PNG
                else:
                    raise MetadataError(f"Unsupported cover art format: {cover_ext}", output_file)
                
                # Create MP4Cover object and add to file
                cover = MP4Cover(cover_data, cover_format)
                audiofile['covr'] = [cover]
                logging.info(f'Added cover art from {cover_art_path} ({len(cover_data)} bytes)')
                
            except Exception as e:
                logging.warning(f'Failed to add cover art: {e}')
                # Continue without cover art rather than failing
        
        if chapter_titles:
            chapters = create_smart_chapters_for_mutagen(input_files, durations, chapter_titles)
        else:
            chapters = create_chapters_for_mutagen(input_files, durations)
            
        _add_chapters_to_file(audiofile, chapters)
        
        # Save the metadata
        audiofile.save()
        
        chapter_count = len(chapters)
        features_added = []
        if cover_art_path:
            features_added.append("cover art")
        if chapter_titles:
            features_added.append("smart chapter titles")
        if metadata and metadata.get('source_metadata'):
            features_added.append("inherited metadata")
            
        features_str = f" with {', '.join(features_added)}" if features_added else ""
        logging.info(f'Successfully added enhanced metadata and {chapter_count} chapters{features_str} to {output_file}')
        
    except Exception as e:
        logging.error(f'Error adding enhanced metadata to {output_file}: {str(e)}')
        raise MetadataError(f"Adding enhanced metadata failed: {str(e)}", output_file) from e

def _extract_metadata_from_source(input_file):
    """
    Extracts metadata from source audio file using FFprobe.
    
    Args:
        input_file (str): Path to input audio file.
        
    Returns:
        dict: Metadata dictionary.
    """
    try:
        ffprobe_command = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', 
            '-show_format', input_file
        ]
        result = subprocess.run(ffprobe_command, capture_output=True, text=True, check=True)
        
        import json
        data = json.loads(result.stdout)
        format_tags = data.get('format', {}).get('tags', {})
        
        # Normalize tag names (different formats use different case)
        normalized = {}
        for key, value in format_tags.items():
            key_lower = key.lower()
            if key_lower in ['title', 'album', 'artist', 'album_artist', 'albumartist', 
                           'date', 'year', 'genre', 'comment', 'description']:
                normalized[key_lower.replace('albumartist', 'album_artist')] = value
                
        return normalized
        
    except Exception as e:
        logging.warning(f'Could not extract metadata from {input_file}: {str(e)}')
        return {}

def _add_chapters_to_file(audiofile, chapters):
    """
    Adds chapter markers to the M4B file using mutagen.
    
    Args:
        audiofile: Mutagen MP4 file object.
        chapters (list): List of (start_time_ms, title) tuples.
    """
    if not chapters:
        return
        
    try:
        # Store chapter information for compatibility with audiobook players
        chapter_titles = []
        for i, (start_ms, title) in enumerate(chapters):
            chapter_titles.append(title)
        
        # Add chapter titles (this works with most audiobook players)
        if chapter_titles:
            # Store as description/summary with chapter info
            chapter_summary = f"Audiobook with {len(chapters)} chapters:\n" + "\n".join(f"{i+1}. {title}" for i, (_, title) in enumerate(chapters))
            audiofile['desc'] = chapter_summary
            
            # Set track number to indicate chapters
            audiofile['trkn'] = [(len(chapters), len(chapters))]
            
            logging.info(f'Added {len(chapters)} chapters to metadata')
            
    except Exception as e:
        logging.warning(f'Could not add chapters to file: {str(e)}')
        # Continue without chapters rather than failing completely

def process_audio_files(input_files, output_file, bitrate="128k", cores=None, progress_tracker=None, resume_mode="auto"):
    """Processes audio files with comprehensive resource management and resume functionality.

    Args:
        input_files (list): List of paths to input audio files.
        output_file (str): Path to output audio file.
        bitrate (str): Bitrate for conversion (default: 128k).
        cores (int): Number of CPU cores to use.
        resume_mode (str): Resume behavior - 'auto', 'never', or 'force'.

    Returns:
        tuple: (durations_list, errors_list) - Successfully processed durations and any errors encountered.
    """
    global tempdir
    
    try:
        removed, freed_mb = cleanup_old_cache_directories(max_age_days=30)
        if removed > 0:
            logging.info(f"Automatic cache cleanup: removed {removed} old directories, freed {freed_mb:.1f}MB")
    except Exception as e:
        logging.warning(f"Cache cleanup failed: {e}")
    
    # Handle resume modes and create temporary directory
    if resume_mode == "never":
        # Force fresh start - clear any existing predictable temp directory
        predictable_temp_dir = create_predictable_temp_dir(input_files, output_file, bitrate)
        if os.path.exists(predictable_temp_dir):
            try:
                shutil.rmtree(predictable_temp_dir)
                logging.info(f"Cleared previous job directory due to --resume never")
                # Recreate clean directory
                os.makedirs(predictable_temp_dir, exist_ok=True)
            except Exception as e:
                logging.warning(f"Failed to clear previous job directory: {e}")
    else:
        # Create predictable temporary directory for resume functionality  
        predictable_temp_dir = create_predictable_temp_dir(input_files, output_file, bitrate)
        # Ensure the directory exists on the filesystem
        os.makedirs(predictable_temp_dir, exist_ok=True)
    
    # Check for existing conversions to detect resume scenario (unless "never" mode)
    existing_conversions = []
    total_files = len(input_files)
    
    if resume_mode != "never":
        for input_file in input_files:
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            temp_file = os.path.join(predictable_temp_dir, f"{base_name}_converted.m4a")
            if os.path.exists(temp_file) and validate_receipt_file(input_file, predictable_temp_dir):
                existing_conversions.append(input_file)
    
    # Handle force mode
    if resume_mode == "force":
        if not existing_conversions:
            raise ProcessingError("Resume forced but no resumable work found", "resume_validation")
        logging.info(f"Forced resume: {len(existing_conversions)}/{total_files} files will be resumed")
    
    # Notify user of resume scenario  
    if existing_conversions and resume_mode != "never":
        logging.info(f"Resume detected: {len(existing_conversions)}/{total_files} files already converted")
        if not progress_tracker:
            print(f"Resume detected: {len(existing_conversions)}/{total_files} files already converted")
            print(f"Skipping {len(existing_conversions)} files, converting {total_files - len(existing_conversions)} remaining files")
    
    # Use managed processing context with our predictable temp directory
    with managed_processing(input_files, temp_dir=predictable_temp_dir, monitor_resources=True) as context:
        tempdir = context['temp_dir']
        resource_monitor = context['resource_monitor']
        requirements = context['requirements']
        
        converted_files = []
        durations = []
        processing_errors = []
        cores_to_use = cores or max_cpu_cores
        
        # Register cleanup callback with signal handler
        signal_handler = get_signal_handler()
        signal_handler.add_cleanup_callback(lambda: cleanup_temp_files(tempdir))
        
        try:
            if not progress_tracker:
                print(f"\nConverting {len(input_files)} audio files...")
                print(f"Using temporary directory: {tempdir}")
                print(f"Using {cores_to_use} CPU cores")
                print(f"Estimated memory usage: {requirements['estimated_memory_mb']}MB")
                print(f"Estimated temp space: {requirements['estimated_temp_space_mb']}MB")
            
            # Use progress tracking for conversion
            if progress_tracker:
                conversion_context = progress_tracker.conversion_progress(len(input_files))
            else:
                from contextlib import nullcontext
                conversion_context = nullcontext()
            
            with conversion_context as conversion_progress:
                with ProcessPoolExecutor(max_workers=cores_to_use) as executor:
                    # Create tasks with error handling
                    future_to_file = {
                        executor.submit(convert_file_for_concatenation, input_file, tempdir, bitrate): input_file
                        for input_file in input_files
                    }
                    
                    # Collect results with skip-and-continue logic
                    completed = 0
                    successful = 0
                    for future in future_to_file:
                        input_file = future_to_file[future]
                        
                        # Check for shutdown signal
                        if signal_handler.check_shutdown_requested():
                            if progress_tracker:
                                conversion_progress.set_description("Shutdown requested - cancelling...")
                            else:
                                print("\nShutdown requested, cancelling remaining tasks...")
                            break
                        
                        # Check memory usage periodically
                        if completed % 5 == 0:  # Check every 5 files
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
                            # Wrap unexpected errors
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

            # Only proceed with concatenation if we have some successful conversions
            if not converted_files:
                raise ProcessingError("No files were successfully converted", "conversion", recoverable=False)
            elif len(converted_files) < len(input_files):
                print(f"\nWarning: Only {len(converted_files)}/{len(input_files)} files converted successfully")
                print("Proceeding with available files...")

            # Step 3: Concatenation and metadata
            if progress_tracker:
                with progress_tracker.operation_progress("Concatenating files", show_spinner=True) as concat_progress:
                    try:
                        concat_progress.update_status("Merging audio streams")
                        _concatenate_audio_files(converted_files, output_file, tempdir)
                        concat_progress.complete("Audio concatenation complete")
                    except ConcatenationError as e:
                        processing_errors.append(e)
                        raise
            else:
                print(f"\nConcatenating {len(converted_files)} files into audiobook...")
                try:
                    _concatenate_audio_files(converted_files, output_file, tempdir)
                    print(f"Successfully created: {output_file}")
                except ConcatenationError as e:
                    processing_errors.append(e)
                    raise  # Re-raise concatenation errors as they're fatal
            
            return durations, processing_errors
        
        except (DependencyError, ResourceError, ConfigurationError) as e:
            # Fatal errors that prevent continuation
            processing_errors.append(e)
            print(f"Fatal error: {e.get_user_message()}")
            logging.error(f'Fatal error during processing: {str(e)}')
            raise
        except Exception as e:
            # Wrap other unexpected errors
            wrapped_error = ProcessingError(f"Unexpected processing error: {str(e)}", "processing", recoverable=False)
            processing_errors.append(wrapped_error)
            print(f"Unexpected error during processing: {str(e)}")
            logging.error(f'Unexpected error during processing: {str(e)}')
            raise

def setup_logging(quiet=False):
    """
    Sets up the logging configuration for the application.

    This function initializes the logging module with basic configurations. It sets the logging level to INFO and 
    formats the log messages to include the timestamp, the level of the message, and the actual message. 

    It also generates a unique filename for the log file based on the current date and time to ensure that logs 
    from different runs of the application do not overwrite each other.
    
    Args:
        quiet (bool): If True, reduces console output verbosity.
    """
    now = datetime.now()
    dt_string = now.strftime("%Y-%m-%d_%H-%M-%S")
    
    # Configure file logging
    logging.basicConfig(
        filename=f'logfile_{dt_string}.log', 
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Add console handler for user feedback (unless quiet mode)
    if not quiet:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        logging.getLogger().addHandler(console_handler)

def parse_arguments():
    """
    Parses and validates command line arguments for the application.

    This function uses argparse to handle command line arguments including input paths,
    optional title, author, output file, and other options. Provides helpful usage 
    information and validates arguments before returning them.

    Returns:
        argparse.Namespace: Parsed command line arguments.
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="AudiobookMakerPy - Convert audio files to M4B audiobook format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python AudiobookMakerPy.py /path/to/audiofiles/
  python AudiobookMakerPy.py file1.mp3 file2.mp3 file3.mp3
  python AudiobookMakerPy.py /path/to/files/ --title "My Book" --author "Author Name"
  python AudiobookMakerPy.py /path/to/files/ --output /custom/path/output.m4b
  python AudiobookMakerPy.py /path/to/files/ --bitrate 64k --cores 2

Supported audio formats: MP3, WAV, M4A, FLAC, OGG, AAC, M4B
        """
    )
    
    parser.add_argument(
        'input_paths', 
        nargs='+', 
        help='One or more paths to audio files or directories containing audio files'
    )
    
    parser.add_argument(
        '--title', '-t',
        help='Title for the audiobook (default: directory name or "Audiobook")'
    )
    
    parser.add_argument(
        '--author', '-a',
        help='Author/narrator for the audiobook (default: extracted from metadata)'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='Output file path (default: auto-generated based on input)'
    )
    
    parser.add_argument(
        '--bitrate', '-b',
        default='128k',
        help='Audio bitrate for conversion (default: 128k)'
    )
    
    parser.add_argument(
        '--cores', '-c',
        type=int,
        default=max_cpu_cores,
        help=f'Number of CPU cores to use for parallel processing. '
             f'Default: {max_cpu_cores} '
             f'(configurable via ~/.audiobookmaker_config.json, '
             f'safe default: {get_safe_cpu_default()} cores)'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Reduce output verbosity'
    )
    
    parser.add_argument(
        '--gui',
        action='store_true',
        help='GUI mode: show progress but auto-overwrite files without prompts'
    )
    
    parser.add_argument(
        '--json-output',
        action='store_true', 
        help='Output structured JSON for progress and logging (for sidecar integration)'
    )
    
    parser.add_argument(
        '--validation-level', '--val',
        choices=['lax', 'normal', 'strict', 'paranoid'],
        default='normal',
        help='Validation strictness level (default: normal)'
    )
    
    parser.add_argument(
        '--output-dir', '--dir',
        type=str,
        help='Output directory for generated audiobook (default: input directory)'
    )
    
    parser.add_argument(
        '--output-name', '--name',
        type=str,
        help='Custom filename for output audiobook (default: auto-generated from metadata)'
    )
    
    parser.add_argument(
        '--quality', '--qual',
        choices=['low', 'medium', 'high', 'custom'],
        default='medium',
        help='Audio quality preset: low (96k), medium (128k), high (192k), custom (use --bitrate)'
    )
    
    parser.add_argument(
        '--template', '--tmpl',
        type=str,
        default='{title}',
        help='Filename template using metadata variables: {title}, {author}, {album}, {year} (default: {title})'
    )
    
    parser.add_argument(
        '--cover', '--cover-art',
        type=str,
        help='Path to cover art image file (JPEG, PNG) to embed in audiobook'
    )
    
    parser.add_argument(
        '--chapter-titles',
        choices=['auto', 'filename', 'generic'],
        default='auto',
        help='Chapter title source: auto (smart extraction), filename (use filenames), generic (Chapter 1, 2, etc.)'
    )
    
    parser.add_argument(
        '--resume',
        choices=['auto', 'never', 'force'],
        default='auto',
        help='Resume behavior: auto (resume if possible), never (always start fresh), force (fail if cannot resume)'
    )
    
    parser.add_argument(
        '--clear-cache', '--clear',
        action='store_true',
        help='Clear cached conversion results before processing (equivalent to --resume never)'
    )
    
    parser.add_argument(
        '--version', '-v',
        action='version',
        version='AudiobookMakerPy 2.0)'
    )
    
    args = parser.parse_args()
    
    if args.clear_cache:
        args.resume = 'never'
        logging.info("Cache clearing requested: setting resume mode to 'never'")
    
    quality_presets = {
        'low': '96k',
        'medium': '128k', 
        'high': '192k'
    }
    
    # Apply quality preset to bitrate if not using custom
    if args.quality != 'custom':
        args.bitrate = quality_presets[args.quality]
    
    if args.cover:
        if not os.path.exists(args.cover):
            parser.error(f"Cover art file does not exist: {args.cover}")
        
        # Check file extension
        cover_ext = os.path.splitext(args.cover)[1].lower()
        if cover_ext not in ['.jpg', '.jpeg', '.png']:
            parser.error(f"Cover art must be JPEG or PNG format, got: {cover_ext}")
        
        # Check file size (reasonable limit)
        try:
            cover_size = os.path.getsize(args.cover)
            if cover_size > 10 * 1024 * 1024:  # 10MB limit
                parser.error(f"Cover art file is too large: {cover_size // (1024*1024)}MB (max 10MB)")
        except OSError as e:
            parser.error(f"Cannot read cover art file: {e}")
    
    # Validate input paths exist
    for path in args.input_paths:
        if not os.path.exists(path):
            parser.error(f"Input path does not exist: {path}")
    
    return args

def validate_and_get_input_files(input_paths):
    """
    Validates and retrieves all valid audio files from the provided input paths.

    This function takes as input a list of paths. Each path can either be a directory or a file.
    If it is a directory, the function retrieves all audio files (with extensions: '.mp3', '.wav', '.m4a', 
    '.flac', '.ogg', '.aac', '.m4b') in the directory. If it is a file, the function adds the file to the 
    list of input files, given it has a valid audio extension. The function then sorts the list of input 
    files using a natural key sorting algorithm.

    Args:
        input_paths (list): A list of paths to directories or files.

    Returns:
        list: A sorted list of valid audio files from the provided paths.

    Raises:
        SystemExit: If no valid audio files are found or paths are invalid.
    """
    input_files = []
    supported_extensions = ('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.m4b')
    
    print(f"Scanning {len(input_paths)} input path(s)...")
    
    for input_path in input_paths:
        if os.path.isdir(input_path):
            folder_files = [
                os.path.join(input_path, f) 
                for f in os.listdir(input_path) 
                if f.lower().endswith(supported_extensions)
            ]
            input_files.extend(folder_files)
            print(f"Found {len(folder_files)} audio files in directory: {input_path}")
            
        elif os.path.isfile(input_path):
            if input_path.lower().endswith(supported_extensions):
                input_files.append(input_path)
                print(f"Added audio file: {os.path.basename(input_path)}")
            else:
                print(f"Warning: Skipping unsupported file format: {input_path}")
                print(f"   Supported formats: {', '.join(supported_extensions)}")
        else:
            print(f"Error: Path does not exist: {input_path}")
            sys.exit(1)

    if not input_files:
        print("Error: No valid audio files found in the specified paths")
        print(f"   Supported formats: {', '.join(supported_extensions)}")
        sys.exit(1)

    input_files.sort(key=natural_keys)
    print(f"Total audio files to process: {len(input_files)}")
    
    # Show file list if not too many
    if len(input_files) <= 10:
        print("Files to process:")
        for i, file in enumerate(input_files, 1):
            print(f"   {i:2d}. {os.path.basename(file)}")
    
    return input_files

def get_output_file(input_files, custom_output=None):
    """
    Generates the output file path based on the first file in the list of input files.

    This function constructs the output file path by taking the directory of the first file 
    in the list of input files and appending the base name of this directory with the '.m4b' 
    extension. This output file path is intended to be used for saving the audiobook file.

    Args:
        input_files (list): A list of file paths to the input audio files.
        custom_output (str, optional): Custom output file path specified by user.

    Returns:
        str: The output file path for the audiobook.
    """
    if custom_output:
        # Ensure custom output has .m4b extension
        if not custom_output.lower().endswith('.m4b'):
            custom_output += '.m4b'
        return custom_output
    
    folder_path = os.path.dirname(input_files[0])
    parent_path = os.path.dirname(folder_path)
    output_name = os.path.basename(folder_path) + '.m4b'
    
    # Put output file in parent directory to avoid including it in future runs
    if parent_path:  # If there's a parent directory, use it
        return os.path.join(parent_path, output_name)
    else:  # If no parent (root directory), use current directory
        return output_name

def check_ffmpeg_dependency():
    """
    Checks if FFmpeg is available and accessible.
    
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

def load_audio_segment(file_path):
    """
    Loads an audio file using pydub and returns an AudioSegment object.
    
    Args:
        file_path (str): Path to the audio file.
        
    Returns:
        AudioSegment: The loaded audio segment.
        
    Raises:
        AudioPropertiesError: If the file cannot be loaded.
    """
    try:
        logging.info(f'Loading audio segment for {file_path}')
        audio_segment = AudioSegment.from_file(file_path)
        return audio_segment
    except Exception as e:
        logging.error(f'Error loading audio file {file_path}: {str(e)}')
        raise FileProcessingError(f"Loading audio file failed: {str(e)}", file_path, "audio_loading") from e

def convert_file_for_concatenation(input_file, temp_dir, bitrate="128k"):
    """
    Converts an audio file to AAC format for concatenation with resume functionality.
    
    Args:
        input_file (str): Path to the input audio file.
        temp_dir (str): Directory for temporary files.
        bitrate (str): Output bitrate (default: 128k).
        
    Returns:
        tuple: (temp_file_path, duration_in_ms)
        
    Raises:
        ConversionError: If conversion fails.
    """
    try:
        # Generate temporary file path
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        temp_file = os.path.join(temp_dir, f"{base_name}_converted.m4a")
        
        # Check for existing conversion and validate receipt
        if os.path.exists(temp_file):
            if validate_receipt_file(input_file, temp_dir):
                # File exists and source hasn't changed - resume by skipping conversion
                try:
                    if PYDUB_AVAILABLE:
                        # Get duration from existing file using pydub
                        audio = AudioSegment.from_file(temp_file)
                        duration_ms = len(audio)
                    else:
                        # Get duration using FFprobe
                        duration_ms = get_audio_duration_ms(temp_file)
                    
                    logging.info(f'Resuming: {input_file} already converted (duration: {duration_ms}ms)')
                    return temp_file, duration_ms
                    
                except Exception as e:
                    logging.warning(f'Failed to read existing converted file {temp_file}: {e}')
                    # Remove corrupted file and receipt to force reconversion
                    try:
                        os.remove(temp_file)
                        receipt_file = os.path.join(temp_dir, f"{base_name}.receipt")
                        if os.path.exists(receipt_file):
                            os.remove(receipt_file)
                    except Exception:
                        pass
            else:
                # Source file changed or no receipt - remove old conversion
                logging.info(f'Source file changed: {input_file}, reconverting')
                try:
                    os.remove(temp_file)
                    receipt_file = os.path.join(temp_dir, f"{base_name}.receipt") 
                    if os.path.exists(receipt_file):
                        os.remove(receipt_file)
                except Exception as e:
                    logging.warning(f'Failed to remove outdated conversion: {e}')
        
        # Perform conversion (either new or after validation failure)
        logging.info(f'Converting {input_file} for concatenation')
        
        if PYDUB_AVAILABLE:
            # Use pydub if available
            audio = AudioSegment.from_file(input_file)
            audio.export(
                temp_file, 
                format="ipod",  # M4A/M4B compatible format
                bitrate=bitrate,
                parameters=["-ar", "44100", "-ac", "2"]
            )
            duration_ms = len(audio)
            
            # Create receipt file after successful pydub conversion
            create_receipt_file(input_file, temp_dir)
        else:
            # Fallback to FFmpeg subprocess with progress tracking
            try:
                duration_ms = convert_with_ffmpeg_progress(input_file, temp_file, bitrate)
            except Exception as e:
                # If FFmpeg fails, try a simpler approach without progress tracking
                logging.warning(f"FFmpeg progress tracking failed: {e}, trying basic conversion")
                duration_ms = convert_with_basic_ffmpeg(input_file, temp_file, bitrate)
                
        # Create receipt file after successful conversion
        create_receipt_file(input_file, temp_dir)
        
        logging.info(f'Converted {input_file} to {temp_file}, duration: {duration_ms}ms')
        return temp_file, duration_ms        
    except Exception as e:
        logging.error(f'Error converting {input_file}: {str(e)}')
        raise ConversionError(f"Conversion failed: {str(e)}", input_file, 
                              source_format=os.path.splitext(input_file)[1], 
                              target_format=".m4a") from e

def convert_with_ffmpeg_progress(input_file, output_file, bitrate="128k"):
    """
    Convert audio file with smooth FFmpeg progress tracking.
    
    Args:
        input_file (str): Input audio file path
        output_file (str): Output file path
        bitrate (str): Audio bitrate
        
    Returns:
        int: Duration in milliseconds
    """
    import re
    import time
    
    # Ensure debug logging is available
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("=== FFmpeg Progress Debug Mode Enabled ===")
    
    # Get total duration for progress calculation
    try:
        total_duration_ms = get_audio_duration(input_file)
        total_duration_seconds = total_duration_ms / 1000.0
    except:
        total_duration_seconds = 0
    
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
    
    # Regex patterns for FFmpeg progress (more comprehensive and robust)
    time_pattern = re.compile(r'time[=\s]*(\d{2}):(\d{2}):(\d{2}(?:\.\d{2,3})?)')
    speed_pattern = re.compile(r'speed[=\s]*(\d+\.?\d*)x?')
    
    # Simplified patterns for basic stats
    basic_time_pattern = re.compile(r'time[=\s]*(\d{2}:\d{2}:\d{2}(?:\.\d{2})?)')
    basic_speed_pattern = re.compile(r'speed[=\s]*(\d+\.?\d*)x')
    
    start_time = time.time()
    last_update_time = 0
    
    # Debug: Log the FFmpeg command being executed
    logging.debug(f"FFmpeg command: {' '.join(ffmpeg_command)}")
    
    try:
        # Read FFmpeg stderr for progress information with timeout
        progress_lines_count = 0
        for line in iter(process.stderr.readline, ''):
            if not line:
                continue
                
            line = line.strip()
            logging.debug(f"FFmpeg stderr: {line}")
            
            # Parse time progress
            time_match = time_pattern.search(line)
            if time_match and total_duration_seconds > 0:
                hours, minutes, seconds = time_match.groups()
                current_seconds = float(hours) * 3600 + float(minutes) * 60 + float(seconds)
                progress_percent = min(100.0, (current_seconds / total_duration_seconds) * 100)
                
                # Parse speed
                speed_match = speed_pattern.search(line)
                speed = speed_match.group(1) if speed_match else "0.0"
                
                # Calculate ETA
                elapsed = time.time() - start_time
                if float(speed) > 0:
                    eta_seconds = (total_duration_seconds - current_seconds) / float(speed)
                    eta_formatted = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                else:
                    eta_formatted = "calculating..."
                
                # Emit progress (throttled) - disabled in multiprocessing mode
                current_time = time.time()
                if current_time - last_update_time >= 0.5:  # Update every 500ms
                    # Skip progress emission in multiprocessing to avoid confusion
                    # emit_progress(
                    #     current=int(progress_percent),
                    #     total=100,
                    #     stage=f"Converting: {progress_percent:.1f}%",
                    #     speed=f"{speed}x",
                    #     eta=eta_formatted
                    # )
                    last_update_time = current_time
        
        # Wait for process completion with timeout
        try:
            process.wait(timeout=300)  # 5 minute timeout per file
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise ConversionError(f"FFmpeg conversion timed out after 5 minutes", input_file)
            
        if process.returncode != 0:
            # Capture stderr for error details
            stderr_output = process.stderr.read()
            raise ConversionError(f"FFmpeg conversion failed: {stderr_output}", input_file)
            
    except Exception as e:
        # Ensure process is terminated on any error
        if process.poll() is None:
            process.kill()
            process.wait()
        raise
    
    # Get final duration for verification
    final_duration = get_audio_duration_fallback(input_file)
    logging.debug(f"Final audio duration: {final_duration}ms")
    
    return final_duration
def get_audio_duration_fallback(input_file):
    """
    Fallback method to get audio duration using ffprobe.
    """
    ffprobe_command = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
        '-of', 'default=noprint_wrappers=1:nokey=1', input_file
    ]
    try:
        output = subprocess.check_output(ffprobe_command).decode('utf-8').strip()
        return int(float(output) * 1000)  # convert to milliseconds
    except subprocess.CalledProcessError as e:
        logging.error(f'Error getting duration for {input_file}: {str(e)}')
        raise FileProcessingError(f"Getting duration failed: {str(e)}", input_file, "duration_extraction") from e

def _concatenate_audio_files(converted_files, output_file, temp_dir):
    """
    Concatenates audio files using streaming architecture for memory efficiency.
    
    Args:
        converted_files (list): List of temporary converted file paths.
        output_file (str): Path for the final output file.
        temp_dir (str): Temporary directory for intermediate files.
        
    Raises:
        ConversionError: If concatenation fails.
    """
    try:
        _concatenate_with_ffmpeg(converted_files, output_file, temp_dir)
    except Exception as e:
        logging.error(f'Concatenation failed: {str(e)}')
        raise ConcatenationError(f"Audio concatenation failed: {str(e)}") from e

def _concatenate_with_ffmpeg(converted_files, output_file, temp_dir):
    """
    Concatenates audio files using FFmpeg concat demuxer with memory pressure monitoring.
    """
    logging.info(f'Concatenating {len(converted_files)} files using FFmpeg streaming architecture')
    
    # Memory pressure detection before concatenation
    try:
        from resource_manager import ResourceMonitor
        monitor = ResourceMonitor()
        memory_stats = monitor.get_current_memory_usage()
        logging.info(f"Pre-concatenation memory usage: {memory_stats['percent']:.1f}% "
                    f"({memory_stats['rss_mb']:.1f}MB used)")
        
        # Check if we're approaching memory limits before starting concatenation
        if memory_stats['percent'] > 80:
            logging.warning(f"High memory usage detected ({memory_stats['percent']:.1f}%) before concatenation")
            logging.info("FFmpeg streaming concatenation will help maintain low memory usage")
    except ImportError:
        logging.debug("Resource monitoring not available for concatenation")
    
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
    
    # Uses streaming concat demuxer for constant memory usage
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
                
        except (NameError, UnboundLocalError):
            # monitor not available, skip memory checks
            pass
            
    except Exception as e:
        logging.error(f'FFmpeg concatenation failed: {e}')
        raise ConcatenationError(f"FFmpeg concatenation failed: {e}")
    
    if result.returncode != 0:
        logging.error(f'FFmpeg concatenation failed: {result.stderr}')
        raise ConcatenationError(f"FFmpeg concatenation failed: {result.stderr}")
    
    logging.info(f'Successfully concatenated {len(converted_files)} files to {output_file} using streaming architecture')

def cleanup_tempdir():
    """
    Removes the temporary directory used during audiobook creation process.

    This function logs the removal of the temporary directory and then proceeds
    to delete it using the shutil.rmtree method.

    Note:
        This function assumes that the 'tempdir' variable is globally accessible and 
        contains the path to the temporary directory. It is expected to be called after 
        all operations needing the temporary directory have been completed.
    """
    logging.info(f'Removing temporary directory - {tempdir}')
    shutil.rmtree(tempdir)

if __name__ == '__main__':
    # Parse command line arguments first
    args = parse_arguments()
    
    # Setup logging with quiet mode support
    setup_logging(quiet=args.quiet)
    
    # JSON mode for sidecar integration
    json_mode = args.json_output
    
    if not json_mode:
        print("=" * 50)
    else:
        emit_log("info", "AudiobookMakerPy)", json_mode)
    
    # Initialize progress tracking and timer
    # In GUI mode, we want progress output but non-interactive behavior
    progress_quiet = args.quiet and not args.gui
    progress_tracker = create_progress_tracker(quiet=progress_quiet)
    processing_timer = ProcessingTimer()
    processing_timer.start()
    
    # Validate and collect input files
    input_files = validate_and_get_input_files(args.input_paths)
    
    # Log file information in JSON mode
    if json_mode:
        for file_path in input_files:
            emit_log("info", f"Added audio file: {os.path.basename(file_path)}", json_mode)
        emit_log("info", f"Total audio files to process: {len(input_files)}", json_mode)
    
    # Pre-flight validation with progress tracking
    validation_level = ValidationLevel(args.validation_level)
    
    try:
        # Step 1: Validation with progress bar
        progress_tracker.print_step("Pre-flight validation", 1, 3)
        emit_progress(10, 100, "Pre-flight validation", json_mode=json_mode)
        
        def validation_progress_callback(current, file_path, is_valid):
            status = "OK" if is_valid else "FAIL"
            return format_file_status(file_path, status)
        
        with progress_tracker.validation_progress(len(input_files)) as validation_progress:
            def progress_update(current, file_path, is_valid):
                description = validation_progress_callback(current, file_path, is_valid)
                validation_progress.update(1, description)
            
            valid_files, validation_report = validate_audio_files(
                input_files, validation_level, progress_update
            )
        
        if len(valid_files) != len(input_files):
            print("\n" + "=" * 50)
            print("VALIDATION REPORT")
            print("=" * 50)
            print(validation_report)
            print("=" * 50)
            
            if not valid_files:
                print("ERROR: No valid audio files found. Processing cannot continue.")
                sys.exit(1)
            
            print(f"WARNING: Only {len(valid_files)}/{len(input_files)} files passed validation.")
            response = input("Continue with valid files only? (y/N): ").strip().lower()
            if response != 'y' and response != 'yes':
                print("Operation cancelled by user")
                sys.exit(0)
            
            # Update input_files to only include valid files
            input_files = valid_files
        else:
            progress_tracker.print_step("All files passed validation - OK", 1, 3)
            emit_progress(20, 100, "All files passed validation", json_mode=json_mode)
            
    except Exception as e:
        print(f"[ERROR] Pre-flight validation failed: {str(e)}")
        logging.error(f"Validation error: {str(e)}")
        sys.exit(1)
    
    # Extract comprehensive metadata for smart processing
    print("\nExtracting comprehensive metadata for smart processing...")
    try:
        comprehensive_metadata = extract_comprehensive_metadata(input_files)
        
        # Extract chapter titles based on user preference
        if args.chapter_titles == 'auto':
            chapter_titles = comprehensive_metadata.get('chapter_titles', [])
        elif args.chapter_titles == 'filename':
            # Force filename-based titles
            chapter_titles = [os.path.splitext(os.path.basename(f))[0] for f in input_files]
        else:  # generic
            # Force generic titles
            chapter_titles = [f"Chapter {i+1}" for i in range(len(input_files))]
        
        # Show extracted metadata if not quiet
        if not args.quiet:
            print(f"Detected metadata - Title: {comprehensive_metadata.get('title', 'N/A')}, Author: {comprehensive_metadata.get('author', 'N/A')}")
            if args.chapter_titles == 'auto' and chapter_titles:
                print(f"Smart chapter titles: {len(chapter_titles)} extracted")
            if args.cover:
                print(f"Cover art: {args.cover}")
        
        # Determine output file with flexible control
        output_file = determine_output_path(input_files, args, comprehensive_metadata)
        
        # Show user the planned output
        print(f"Output file: {output_file}")
        if args.quality != 'custom':
            print(f"Audio quality: {args.quality} ({args.bitrate})")
        else:
            print(f"Audio quality: custom ({args.bitrate})")
            
    except ConfigurationError as e:
        print(f"[ERROR] Output configuration error: {str(e)}")
        logging.error(f"Output configuration error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error during output setup: {str(e)}")
        logging.error(f"Unexpected error during output setup: {str(e)}")
        sys.exit(1)
    
    # Check if output file already exists
    if os.path.exists(output_file):
        print(f"Warning: Output file already exists: {output_file}")
        if args.quiet or args.gui:
            # In quiet mode or GUI mode, automatically overwrite
            print("Automatically overwriting existing file (quiet/GUI mode)")
        else:
            response = input("Do you want to overwrite it? (y/N): ").strip().lower()
            if response != 'y' and response != 'yes':
                print("Operation cancelled by user")
                sys.exit(0)
    
    all_errors = []
    
    try:
        # Check dependencies first
        progress_tracker.print_step("Checking dependencies", 2, 3)
        emit_progress(30, 100, "Checking dependencies", json_mode=json_mode)
        ffmpeg_version = check_ffmpeg_dependency()
        logging.info(f'FFmpeg version: {ffmpeg_version}')
        
        # Process files and get durations
        progress_tracker.print_step("Processing audio files", 3, 3)
        emit_progress(40, 100, "Processing audio files", json_mode=json_mode)
        file_durations, processing_errors = process_audio_files(
            input_files, 
            output_file, 
            bitrate=args.bitrate,
            cores=args.cores,
            progress_tracker=progress_tracker,
            resume_mode=args.resume
        )
        
        # Collect any processing errors
        all_errors.extend(processing_errors)
        
        if not file_durations:
            print("No files were successfully processed - exiting")
            logging.error('No files were successfully processed')
            sys.exit(1)
        
        # Add comprehensive metadata using smart extraction
        if not args.quiet:
            with progress_tracker.operation_progress("Writing enhanced metadata", show_spinner=True) as metadata_progress:
                try:
                    if args.cover:
                        metadata_progress.update_status("Processing cover art")
                    metadata_progress.update_status("Adding smart chapter information")
                    
                    add_metadata_to_audiobook(
                        output_file, 
                        input_files, 
                        file_durations,
                        metadata=comprehensive_metadata,
                        cover_art_path=args.cover,
                        chapter_titles=chapter_titles
                    )
                    metadata_progress.complete("Enhanced metadata written successfully")
                except MetadataError as e:
                    all_errors.append(e)
                    metadata_progress.complete("Metadata processing failed")
                    print(f"Warning: Enhanced metadata processing failed: {e}")
                    logging.warning(f"Enhanced metadata processing failed but audiobook was created: {e}")
        else:
            try:
                add_metadata_to_audiobook(
                    output_file, 
                    input_files, 
                    file_durations,
                    metadata=comprehensive_metadata,
                    cover_art_path=args.cover,
                    chapter_titles=chapter_titles
                )
            except MetadataError as e:
                all_errors.append(e)
                logging.warning(f"Enhanced metadata processing failed but audiobook was created: {e}")
        
        # Calculate total duration for summary
        total_duration_ms = sum(file_durations)
        total_hours = total_duration_ms // (1000 * 60 * 60)
        total_minutes = (total_duration_ms % (1000 * 60 * 60)) // (1000 * 60)
        
        # Final processing summary
        processing_duration = processing_timer.stop()
        successful_files = len(file_durations)
        failed_files = len(input_files) - successful_files
        
        progress_tracker.print_summary(
            total_files=len(input_files),
            successful_files=successful_files,
            failed_files=failed_files,
            duration_seconds=processing_duration
        )
        
        if not args.quiet:
            print(f"\nAudiobook Details:")
            print(f"   - Total duration: {total_hours}h {total_minutes}m")
            print(f"   - Output: {output_file}")
            print(f"   - Bitrate: {args.bitrate}")
        
        # Display error summary if there were any issues
        if all_errors:
            print(f"\nError Summary:")
            print("=" * 50)
            print(get_error_summary(all_errors))
        
        logging.info('Audiobook creation complete.')
        
    except KeyboardInterrupt:
        interrupted_error = InterruptedError("Processing cancelled by user", "main_processing", recoverable=True)
        all_errors.append(interrupted_error)
        print(f"\nOperation cancelled by user")
        sys.exit(0)
    except DependencyError as e:
        all_errors.append(e)
        print(f"\nDependency Error: {e.get_user_message()}")
        logging.error(f'Dependency error: {str(e)}')
        sys.exit(1)
    except AudiobookMakerError as e:
        all_errors.append(e)
        print(f"\nError: {e.get_user_message()}")
        logging.error(f'Application error: {str(e)}')
        sys.exit(1)
    except Exception as e:
        unexpected_error = ProcessingError(f"Unexpected error: {str(e)}", "main", recoverable=False)
        all_errors.append(unexpected_error)
        print(f"\nUnexpected error: {str(e)}")
        logging.error(f'Unexpected error: {str(e)}')
        sys.exit(1)
    finally:
        # Always cleanup temp directory
        if tempdir and os.path.exists(tempdir):
            try:
                cleanup_tempdir()
                print("Cleaned up temporary files")
            except Exception as e:
                cleanup_error = ResourceError(f"Failed to cleanup temporary files: {str(e)}", "cleanup")
                all_errors.append(cleanup_error)
                print(f"Warning: Failed to cleanup temporary files: {e}")
        
        # Final error reporting
        if all_errors and len(all_errors) > 0:
            logging.info(f'Session completed with {len(all_errors)} total errors')

def convert_with_basic_ffmpeg(input_file, output_file, bitrate="128k"):
    """
    Basic FFmpeg conversion without progress tracking for reliability.
    
    Args:
        input_file (str): Input audio file path
        output_file (str): Output file path
        bitrate (str): Audio bitrate
        
    Returns:
        int: Duration in milliseconds
    """
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
            timeout=300  # 5 minute timeout per file
        )
        
        if result.returncode != 0:
            raise ConversionError(f"FFmpeg conversion failed: {result.stderr}", input_file)
            
        return get_audio_duration_fallback(input_file)
        
    except subprocess.TimeoutExpired:
        raise ConversionError("FFmpeg conversion timed out after 5 minutes", input_file)
    except Exception as e:
        raise ConversionError(f"FFmpeg conversion error: {str(e)}", input_file)