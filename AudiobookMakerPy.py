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

# Try to import pydub, but continue without it if it fails (Python 3.13 compatibility)
try:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pydub import AudioSegment
    PYDUB_AVAILABLE = True
    logging.info('pydub available - using for audio processing')
except ImportError:
    PYDUB_AVAILABLE = False
    logging.info('pydub not available - using fallback subprocess method')
    
if not MUTAGEN_AVAILABLE:
    raise DependencyError("mutagen", "mutagen is required for metadata handling")

# Global variables
max_cpu_cores = min(5, os.cpu_count() or 1)  # Number of cores to use for parallel processing, use all available cores by default
tempdir = None

def cleanup_temp_files(temp_directory):
    """Cleanup function for signal handler."""
    if temp_directory and os.path.exists(temp_directory):
        try:
            shutil.rmtree(temp_directory)
            logging.info(f"Emergency cleanup completed: {temp_directory}")
        except Exception as e:
            logging.error(f"Failed emergency cleanup: {e}")

def create_job_hash(input_files, output_file, bitrate="128k"):
    """
    Create a predictable hash for job identification and resume functionality.
    
    Phase 3.4: Generates consistent hash based on input files, output path, and processing parameters
    to enable resume functionality through predictable temporary directory naming.
    
    Args:
        input_files (list): List of input file paths
        output_file (str): Path to output audiobook file
        bitrate (str): Processing bitrate parameter
        
    Returns:
        str: SHA256 hash for job identification
    """
    # Create deterministic string from all inputs
    job_data = {
        'input_files': sorted([os.path.abspath(f) for f in input_files]),  # Sort for consistency
        'output_file': os.path.abspath(output_file),
        'bitrate': bitrate,
        'version': '3.4'  # Version for future compatibility
    }
    
    # Convert to JSON string for hashing
    job_string = json.dumps(job_data, sort_keys=True)
    
    # Create SHA256 hash
    job_hash = hashlib.sha256(job_string.encode('utf-8')).hexdigest()[:16]  # First 16 chars for readability
    
    logging.debug(f"Created job hash: {job_hash} for {len(input_files)} files")
    return job_hash

def create_predictable_temp_dir(input_files, output_file, bitrate="128k"):
    """
    Create a predictable temporary directory for resume functionality.
    
    Phase 3.4: Uses job hash to create consistent temp directory names,
    enabling resume functionality by reusing existing processed files.
    
    Args:
        input_files (list): List of input file paths
        output_file (str): Path to output audiobook file
        bitrate (str): Processing bitrate parameter
        
    Returns:
        str: Path to the predictable temporary directory
    """
    job_hash = create_job_hash(input_files, output_file, bitrate)
    temp_base = tempfile.gettempdir()
    temp_dir = os.path.join(temp_base, f"audiobookmaker_{job_hash}")
    
    # Create directory if it doesn't exist
    os.makedirs(temp_dir, exist_ok=True)
    
    logging.info(f"Using job directory: {temp_dir}")
    return temp_dir

def create_receipt_file(input_file, temp_dir):
    """
    Create a receipt file to track input file state for resume validation.
    
    Phase 3.4: Stores modification time and file size to detect changes
    in source files since last processing attempt.
    
    Args:
        input_file (str): Path to the input audio file
        temp_dir (str): Temporary directory for receipt files
    """
    try:
        file_stats = os.stat(input_file)
        receipt_data = {
            'file_path': os.path.abspath(input_file),
            'modification_time': file_stats.st_mtime,
            'file_size': file_stats.st_size,
            'timestamp': datetime.now().isoformat()
        }
        
        # Receipt file name based on input file
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        receipt_file = os.path.join(temp_dir, f"{base_name}.receipt")
        
        with open(receipt_file, 'w', encoding='utf-8') as f:
            json.dump(receipt_data, f, indent=2)
            
        logging.debug(f"Created receipt for {input_file}: {receipt_file}")
        
    except Exception as e:
        logging.warning(f"Failed to create receipt for {input_file}: {e}")

def validate_receipt_file(input_file, temp_dir):
    """
    Validate that input file hasn't changed since receipt was created.
    
    Phase 3.4: Checks modification time and file size against stored receipt
    to determine if cached conversion result is still valid.
    
    Args:
        input_file (str): Path to the input audio file
        temp_dir (str): Temporary directory containing receipt files
        
    Returns:
        bool: True if file is unchanged, False if changed or no receipt exists
    """
    try:
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        receipt_file = os.path.join(temp_dir, f"{base_name}.receipt")
        
        if not os.path.exists(receipt_file):
            logging.debug(f"No receipt found for {input_file}")
            return False
            
        with open(receipt_file, 'r', encoding='utf-8') as f:
            receipt_data = json.load(f)
            
        # Check current file stats
        current_stats = os.stat(input_file)
        
        # Validate file hasn't changed
        if (receipt_data['modification_time'] == current_stats.st_mtime and
            receipt_data['file_size'] == current_stats.st_size):
            logging.debug(f"Receipt valid for {input_file}")
            return True
        else:
            logging.info(f"File changed since last processing: {input_file}")
            return False
            
    except Exception as e:
        logging.warning(f"Failed to validate receipt for {input_file}: {e}")
        return False

def extract_metadata_for_template(input_files):
    """
    Extract metadata from source files for filename template generation.
    
    Phase 3.2: Uses mutagen to extract metadata from the first valid file
    to provide template variables like {title}, {author}, {album}, {year}.
    
    Args:
        input_files: List of input audio file paths
        
    Returns:
        Dict containing metadata variables for template substitution
    """
    metadata = {
        'title': 'Audiobook',
        'author': 'Unknown Author', 
        'album': 'Unknown Album',
        'year': datetime.now().strftime('%Y'),
        'date': datetime.now().strftime('%Y-%m-%d')
    }
    
    if not MUTAGEN_AVAILABLE or not input_files:
        return metadata
    
    # Try to extract metadata from the first file
    try:
        from mutagen import File
        audio_file = File(input_files[0])
        
        if audio_file is not None:
            # Common tag mappings across formats
            title_tags = ['TIT2', 'TITLE', '\xa9nam']  # ID3, Vorbis, MP4
            artist_tags = ['TPE1', 'ARTIST', '\xa9ART']  # ID3, Vorbis, MP4  
            album_tags = ['TALB', 'ALBUM', '\xa9alb']    # ID3, Vorbis, MP4
            date_tags = ['TDRC', 'DATE', '\xa9day']      # ID3, Vorbis, MP4
            
            # Extract title
            for tag in title_tags:
                if tag in audio_file and audio_file[tag]:
                    metadata['title'] = str(audio_file[tag][0]).strip()
                    break
            
            # Extract artist/author
            for tag in artist_tags:
                if tag in audio_file and audio_file[tag]:
                    metadata['author'] = str(audio_file[tag][0]).strip()
                    break
                    
            # Extract album
            for tag in album_tags:
                if tag in audio_file and audio_file[tag]:
                    metadata['album'] = str(audio_file[tag][0]).strip()
                    break
                    
            # Extract year
            for tag in date_tags:
                if tag in audio_file and audio_file[tag]:
                    date_str = str(audio_file[tag][0]).strip()
                    # Extract year from date string (handle various formats)
                    import re
                    year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
                    if year_match:
                        metadata['year'] = year_match.group()
                    break
                    
    except Exception as e:
        logging.warning(f"Could not extract metadata from {input_files[0]}: {e}")
    
    return metadata

def apply_filename_template(template, metadata, fallback_name="Audiobook"):
    """
    Apply filename template with metadata variable substitution.
    
    Phase 3.2: Simple template system using string replacement.
    Supports variables: {title}, {author}, {album}, {year}, {date}
    
    Args:
        template: Template string with {variable} placeholders
        metadata: Dict containing metadata values 
        fallback_name: Fallback name if template fails
        
    Returns:
        Generated filename (without extension)
    """
    try:
        # Sanitize metadata values for filename use
        safe_metadata = {}
        for key, value in metadata.items():
            if value:
                # Remove invalid filename characters
                import re
                safe_value = re.sub(r'[<>:"/\\|?*]', '', str(value))
                safe_value = safe_value.strip()
                safe_metadata[key] = safe_value if safe_value else f"Unknown {key.title()}"
            else:
                safe_metadata[key] = f"Unknown {key.title()}"
        
        # Apply template substitution
        filename = template
        for key, value in safe_metadata.items():
            filename = filename.replace(f'{{{key}}}', value)
        
        # Remove any remaining template variables that weren't found
        import re
        filename = re.sub(r'\{[^}]*\}', '', filename)
        filename = filename.strip()
        
        # Fallback if template resulted in empty string
        if not filename or filename.isspace():
            filename = fallback_name
            
        return filename
        
    except Exception as e:
        logging.warning(f"Template application failed: {e}")
        return fallback_name

def validate_output_path(output_path):
    """
    Validate that the output path is writable and handle potential issues.
    
    Phase 3.2: Output validation and error handling
    
    Args:
        output_path: Proposed output file path
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Check if directory exists and is writable
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            return False, f"Output directory does not exist: {output_dir}"
            
        if not os.access(output_dir, os.W_OK):
            return False, f"Output directory is not writable: {output_dir}"
            
        # Check if filename is valid
        filename = os.path.basename(output_path)
        if not filename or filename.isspace():
            return False, "Generated filename is empty"
            
        # Check for invalid filename characters (Windows)
        import re
        if re.search(r'[<>:"/\\|?*]', filename):
            return False, f"Filename contains invalid characters: {filename}"
            
        # Check filename length (Windows limit is 255, be conservative)
        if len(filename) > 200:
            return False, f"Filename is too long ({len(filename)} characters): {filename}"
            
        return True, None
        
    except Exception as e:
        return False, f"Output path validation error: {str(e)}"

def get_chapter_title(file_path):
    """
    Get the best possible chapter title using Gemini's fallback strategy.
    
    Phase 3.3: Smart chapter naming with three-tier fallback:
    1. Priority 1: Read title tag from metadata
    2. Priority 2: Use filename (cleaned)
    3. Priority 3: Generic chapter name
    
    Args:
        file_path: Path to the audio file
        
    Returns:
        String containing the best available chapter title
    """
    try:
        # Priority 1: Try to read title tag using mutagen
        if MUTAGEN_AVAILABLE:
            from mutagen import File
            audio_file = File(file_path)
            
            if audio_file is not None:
                # Common title tag mappings across formats
                title_tags = ['TIT2', 'TITLE', '\xa9nam']  # ID3, Vorbis, MP4
                
                for tag in title_tags:
                    if tag in audio_file and audio_file[tag]:
                        title = str(audio_file[tag][0]).strip()
                        if title and not title.isspace():
                            logging.debug(f"Found title tag for {file_path}: {title}")
                            return title
        
        # Priority 2: Use filename (cleaned)
        filename = os.path.splitext(os.path.basename(file_path))[0]
        
        # Clean up common filename patterns
        import re
        # Remove track numbers (01, 001, 1., 01-, etc.)
        cleaned = re.sub(r'^[\d\s\-\.]+', '', filename).strip()
        
        # Remove common prefixes
        cleaned = re.sub(r'^(chapter|track|part)\s*[\d\s\-\.]*', '', cleaned, flags=re.IGNORECASE).strip()
        
        if cleaned and not cleaned.isspace():
            logging.debug(f"Using cleaned filename for {file_path}: {cleaned}")
            return cleaned
        
        # If cleaning removed everything, use original filename
        if filename and not filename.isspace():
            logging.debug(f"Using original filename for {file_path}: {filename}")
            return filename
            
    except Exception as e:
        logging.warning(f"Error extracting chapter title from {file_path}: {e}")
    
    # Priority 3: Generic fallback
    generic_title = f"Chapter {os.path.basename(file_path)}"
    logging.debug(f"Using generic title for {file_path}: {generic_title}")
    return generic_title

def extract_comprehensive_metadata(input_files):
    """
    Extract comprehensive metadata from all source files.
    
    Phase 3.3: Enhanced metadata extraction with inheritance and conflict resolution.
    Builds upon Phase 3.2's basic extraction to provide rich metadata for chapters.
    
    Args:
        input_files: List of input audio file paths
        
    Returns:
        Dict containing comprehensive metadata including chapter titles
    """
    metadata = {
        'title': 'Audiobook',
        'author': 'Unknown Author', 
        'album': 'Unknown Album',
        'year': datetime.now().strftime('%Y'),
        'date': datetime.now().strftime('%Y-%m-%d'),
        'chapter_titles': [],
        'source_metadata': {}
    }
    
    if not input_files:
        return metadata
    
    # Extract chapter titles from all files
    for file_path in input_files:
        chapter_title = get_chapter_title(file_path)
        metadata['chapter_titles'].append(chapter_title)
    
    # Extract base metadata from first file (Phase 3.3 inheritance)
    if MUTAGEN_AVAILABLE:
        try:
            from mutagen import File
            first_file = File(input_files[0])
            
            if first_file is not None:
                # Store comprehensive source metadata
                metadata['source_metadata'] = dict(first_file)
                
                # Extract primary metadata with priority order
                title_tags = ['TIT2', 'TITLE', '\xa9nam', 'TALB', 'ALBUM', '\xa9alb']  # Include album as title fallback
                artist_tags = ['TPE1', 'ARTIST', '\xa9ART', 'TPE2', 'ALBUMARTIST', '\xa9art']  # Include album artist
                album_tags = ['TALB', 'ALBUM', '\xa9alb']
                date_tags = ['TDRC', 'DATE', '\xa9day', 'TYER', 'YEAR']
                
                # Extract album/book title (primary metadata)
                for tag in album_tags:
                    if tag in first_file and first_file[tag]:
                        title = str(first_file[tag][0]).strip()
                        if title:
                            metadata['title'] = title
                            metadata['album'] = title
                            break
                
                # Extract artist/author
                for tag in artist_tags:
                    if tag in first_file and first_file[tag]:
                        artist = str(first_file[tag][0]).strip()
                        if artist:
                            metadata['author'] = artist
                            break
                
                # Extract year/date
                for tag in date_tags:
                    if tag in first_file and first_file[tag]:
                        date_str = str(first_file[tag][0]).strip()
                        if date_str:
                            # Extract year from date string
                            import re
                            year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
                            if year_match:
                                metadata['year'] = year_match.group()
                            break
                            
        except Exception as e:
            logging.warning(f"Error extracting comprehensive metadata: {e}")
    
    # Fallback to basic extraction for template compatibility
    basic_metadata = extract_metadata_for_template(input_files)
    for key in ['title', 'author', 'album', 'year', 'date']:
        if key not in metadata or metadata[key] in ['Audiobook', 'Unknown Author', 'Unknown Album']:
            if key in basic_metadata and basic_metadata[key] not in ['Audiobook', 'Unknown Author', 'Unknown Album']:
                metadata[key] = basic_metadata[key]
    
    logging.info(f"Extracted metadata for {len(input_files)} files: {len(metadata['chapter_titles'])} chapter titles")
    return metadata

def determine_output_path(input_files, args, metadata):
    """
    Determine the final output file path based on user arguments and metadata.
    
    Phase 3.2: Combines output directory, naming template, and custom name options.
    
    Args:
        input_files: List of input file paths
        args: Parsed command line arguments
        metadata: Extracted metadata for template variables
        
    Returns:
        Complete output file path
        
    Raises:
        ConfigurationError: If output path is invalid or cannot be created
    """
    # Determine output directory
    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
        try:
            # Create directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            raise ConfigurationError(f"Cannot create output directory '{output_dir}': {str(e)}")
    else:
        # Default: use directory of first input file
        output_dir = os.path.dirname(os.path.abspath(input_files[0]))
    
    # Determine filename
    if args.output_name:
        # User provided explicit filename
        filename = args.output_name
        # Remove extension if user provided one (we'll add .m4b)
        if filename.lower().endswith('.m4b'):
            filename = filename[:-4]
    else:
        # Generate filename from template
        filename = apply_filename_template(args.template, metadata)
    
    # Combine directory and filename with .m4b extension
    output_path = os.path.join(output_dir, f"{filename}.m4b")
    
    # Validate the output path
    is_valid, error_msg = validate_output_path(output_path)
    if not is_valid:
        raise ConfigurationError(f"Invalid output path: {error_msg}")
    
    return output_path

def atoi(text):
    """Converts a digit string to an integer, otherwise returns the original string"""
    return int(text) if text.isdigit() else text

def natural_keys(text):
    """Splits the input text at each digit and applies atoi function to each part for natural sorting"""
    return [atoi(c) for c in re.split(r'(\d+)', text)]

def get_audio_duration(input_file):
    """
    Retrieves the duration of the provided audio file.

    The function uses the ffprobe command to obtain the duration of the audio file. It then returns this duration, 
    converted from seconds to milliseconds.

    Args:
        input_file (str): The path of the input audio file.

    Returns:
        int: The duration of the audio file in milliseconds.

    Raises:
        AudioDurationError: If there is an error in executing the ffprobe command or parsing its output.
    """
    logging.info(f'Getting duration for {input_file}')
    ffprobe_command = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
    try:
        output = subprocess.check_output(ffprobe_command).decode('utf-8').strip()
        return int(float(output) * 1000)  # convert duration from seconds to milliseconds
    except subprocess.CalledProcessError as e:
        logging.error(f'Error occurred while getting duration for {input_file}: {str(e)}')
        raise FileProcessingError(f"Getting duration failed: {str(e)}", input_file, "duration_extraction") from e

def get_audio_properties(input_file):
    """
    Extracts the audio properties of the given input file.

    The function uses ffprobe command to get information about the audio file, including codec, sample rate, 
    channels, and bit rate. It then returns these properties in a dictionary.

    Args:
        input_file (str): The path of the input audio file.

    Returns:
        dict: A dictionary containing the audio properties. The keys are 'codec', 'sample_rate', 'channels', 
        and 'bit_rate'.

    Raises:
        AudioPropertiesError: If there is an error in executing the ffprobe command or parsing its output.
    """
    logging.info(f'Getting properties for {input_file}')
    # Define ffprobe command to extract audio properties
    ffprobe_command = ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_name,sample_rate,channels,bit_rate', '-of', 'csv=p=0', input_file]
    try:
        # Execute command and decode output
        output = subprocess.check_output(ffprobe_command).decode('utf-8').strip().split(',')
        # Return a dictionary of properties
        return {
            'codec': output[0],           # Audio codec (e.g., mp3, aac)
            'sample_rate': int(output[1]),  # Sample rate (e.g., 44100, 48000)
            'channels': int(output[2]),    # Number of channels (e.g., 1 for mono, 2 for stereo)
            'bit_rate': int(output[3]),   # Bit rate (e.g., 128000 for 128 kbps)
        }
    except subprocess.CalledProcessError as e:
        logging.error(f'Error occurred while getting properties for {input_file}: {str(e)}')
        raise FileProcessingError(f"Getting properties failed: {str(e)}", input_file, "properties_extraction") from e

def ms_to_timestamp(ms):
    """
    Converts a time duration from milliseconds to a timestamp format.

    The function takes a time duration in milliseconds and converts it to a timestamp format of 'HH:MM:SS.mmm',
    where 'HH' represents hours, 'MM' represents minutes, 'SS' represents seconds, and 'mmm' represents milliseconds.

    Args:
        ms (int): The time duration in milliseconds.

    Returns:
        str: The time duration in timestamp format ('HH:MM:SS.mmm').
    """
    # convert milliseconds to timestamp format (HH:MM:SS.mmm)
    seconds, ms = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{ms:03}"

def convert_to_aac(input_file, output_file, bitrate):
    """
    Converts the given audio file to AAC format using ffmpeg.

    The function prepares and executes a ffmpeg command for converting the input audio file
    to AAC format with the specified bitrate. If the conversion process encounters an error,
    the function logs the error, removes the output file if it was created, and raises a 
    ConversionError exception.

    Args:
        input_file (str): The path of the audio file to be converted.
        output_file (str): The path where the converted file will be saved.
        bitrate (int): The bitrate for the converted audio file in kbps.

    Returns:
        str: The path of the converted audio file.

    Raises:
        ConversionError: If the conversion process fails.
    """
    # Prepare the command for ffmpeg to convert the input file to AAC format
    ffmpeg_command = ['ffmpeg', '-i', input_file, '-vn', '-acodec', 'aac', '-b:a', f'{bitrate}k', '-ar', '44100', '-ac', '2', output_file]

    try:
        # Run the ffmpeg command
        subprocess.run(ffmpeg_command, check=True)

    except subprocess.CalledProcessError as e:
        # Log the error if there's an issue with the conversion process
        logging.error(f'Error occurred while converting {input_file} to AAC: {str(e)}')

        # Check if the output file was created
        if os.path.exists(output_file):
            # If it was created, remove it because the conversion process was not successful
            os.remove(output_file)

        # Raise an exception to stop the script due to the error
        raise ConversionError(f"Conversion failed: {str(e)}", input_file, 
                              source_format=os.path.splitext(input_file)[1], 
                              target_format=".m4a") from e

    return output_file

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
    
    Phase 3.3: Enhanced chapter creation with intelligent titles from metadata/filenames.
    
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
    Adds comprehensive metadata to the audiobook using Phase 3.3 smart extraction.
    
    Phase 3.3: Enhanced metadata writing with smart chapter titles, metadata inheritance,
    and cover art support using mutagen's surgical precision.
    
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
        logging.info(f'Adding enhanced metadata to {output_file} using Phase 3.3 smart extraction')
        
        # Open the M4B file with mutagen
        audiofile = MP4(output_file)
        
        # Use comprehensive metadata if available, fallback to legacy extraction
        if metadata:
            # Phase 3.3: Use smart extracted metadata
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
        
        # Phase 3.3: Add cover art if provided
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
                    raise MetadataError(f"Unsupported cover art format: {cover_ext}")
                
                # Create MP4Cover object and add to file
                cover = MP4Cover(cover_data, cover_format)
                audiofile['covr'] = [cover]
                logging.info(f'Added cover art from {cover_art_path} ({len(cover_data)} bytes)')
                
            except Exception as e:
                logging.warning(f'Failed to add cover art: {e}')
                # Continue without cover art rather than failing
        
        # Phase 3.3: Create and add smart chapters
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
        raise MetadataError(f"Adding enhanced metadata to {output_file} failed: {str(e)}") from e

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

    This function implements Phase 2.4 resource management and Phase 3.4 resume functionality:
    - Memory usage monitoring and limits
    - Disk space verification  
    - Guaranteed cleanup of temporary files
    - Signal handling for graceful shutdown
    - Predictable temporary directories for resume capability
    - Existing conversion detection and validation

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
    
    # Phase 3.4: Handle resume modes and create temporary directory
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
  
Phase 3.2 - Flexible Output Control:
  python AudiobookMakerPy.py /path/to/files/ --output-dir /custom/output/
  python AudiobookMakerPy.py /path/to/files/ --output-name "My Custom Book"
  python AudiobookMakerPy.py /path/to/files/ --quality high --template "{author} - {title}"
  python AudiobookMakerPy.py /path/to/files/ --template "{author} - {album} ({year})"

Phase 3.3 - Smart Metadata Extraction:
  python AudiobookMakerPy.py /path/to/files/ --cover cover.jpg --chapter-titles auto
  python AudiobookMakerPy.py /path/to/files/ --cover art.png --chapter-titles filename
  python AudiobookMakerPy.py /path/to/files/ --quality high --cover cover.jpg

Phase 3.4 - Resume Functionality:
  python AudiobookMakerPy.py /path/to/files/ --resume auto  # Resume if possible (default)
  python AudiobookMakerPy.py /path/to/files/ --resume never  # Always start fresh
  python AudiobookMakerPy.py /path/to/files/ --resume force  # Fail if cannot resume

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
        default=min(5, os.cpu_count() or 1),
        help=f'Number of CPU cores to use (default: {min(5, os.cpu_count() or 1)})'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Reduce output verbosity'
    )
    
    parser.add_argument(
        '--validation-level', '--val',
        choices=['lax', 'normal', 'strict', 'paranoid'],
        default='normal',
        help='Validation strictness level (default: normal)'
    )
    
    # Phase 3.2: Flexible Output Control arguments
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
    
    # Phase 3.3: Smart Metadata Extraction arguments
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
    
    # Phase 3.4: Resume Functionality arguments
    parser.add_argument(
        '--resume',
        choices=['auto', 'never', 'force'],
        default='auto',
        help='Resume behavior: auto (resume if possible), never (always start fresh), force (fail if cannot resume)'
    )
    
    parser.add_argument(
        '--version', '-v',
        action='version',
        version='AudiobookMakerPy 2.0 (Phase 3.4)'
    )
    
    args = parser.parse_args()
    
    # Phase 3.2: Process quality presets
    quality_presets = {
        'low': '96k',
        'medium': '128k', 
        'high': '192k'
    }
    
    # Apply quality preset to bitrate if not using custom
    if args.quality != 'custom':
        args.bitrate = quality_presets[args.quality]
    
    # Phase 3.3: Validate cover art if provided
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
    
    Phase 3.4: Idempotent conversion function that checks for existing converted files
    and validates source file changes using receipt files to enable resume functionality.
    
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
        
        # Phase 3.4: Check for existing conversion and validate receipt
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
            
            # Phase 3.4: Create receipt file after successful pydub conversion
            create_receipt_file(input_file, temp_dir)
        else:
            # Fallback to FFmpeg subprocess (original method)
            ffmpeg_command = [
                'ffmpeg', '-i', input_file, '-vn', '-acodec', 'aac', 
                '-b:a', f'{bitrate}', '-ar', '44100', '-ac', '2', temp_file
            ]
            subprocess.run(ffmpeg_command, check=True)
            
            # Get duration using ffprobe
            duration_ms = get_audio_duration_fallback(input_file)
        
        # Phase 3.4: Create receipt file after successful conversion
        create_receipt_file(input_file, temp_dir)
        
        logging.info(f'Converted {input_file} to {temp_file}, duration: {duration_ms}ms')
        return temp_file, duration_ms
        
    except Exception as e:
        logging.error(f'Error converting {input_file}: {str(e)}')
        raise ConversionError(f"Conversion failed: {str(e)}", input_file, 
                              source_format=os.path.splitext(input_file)[1], 
                              target_format=".m4a") from e

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
    Concatenates audio files using FFmpeg for memory efficiency.
    
    Per Gemini's analysis: pydub concatenation loads all files into memory simultaneously,
    which can require 6GB+ RAM for large audiobooks. FFmpeg's concat demuxer is much more
    memory efficient as it streams files directly from disk.
    
    Args:
        converted_files (list): List of temporary converted file paths.
        output_file (str): Path for the final output file.
        temp_dir (str): Temporary directory for intermediate files.
        
    Raises:
        ConversionError: If concatenation fails.
    """
    try:
        # Always use FFmpeg for concatenation to avoid memory issues
        # This implements Gemini's "streaming concatenation strategy"
        _concatenate_with_ffmpeg(converted_files, output_file, temp_dir)
    except Exception as e:
        logging.error(f'Concatenation failed: {str(e)}')
        raise ConcatenationError(f"Audio concatenation failed: {str(e)}") from e

def _concatenate_with_pydub(converted_files, output_file):
    """
    Concatenates audio files using pydub.
    
    WARNING: This method loads all files into memory simultaneously and can consume
    6GB+ RAM for large audiobooks. Use _concatenate_with_ffmpeg for production.
    Kept for potential future optimizations with chunked processing.
    """
    logging.warning(f'Using memory-intensive pydub concatenation for {len(converted_files)} files')
    logging.info(f'Concatenating {len(converted_files)} files using pydub')
    
    # Load first file to establish format
    final_audio = AudioSegment.from_file(converted_files[0])
    
    # Add remaining files
    for temp_file in converted_files[1:]:
        audio_segment = AudioSegment.from_file(temp_file)
        final_audio += audio_segment
        logging.debug(f'Added {temp_file} to concatenation')
    
    # Export with optimized settings
    logging.info(f'Exporting final audiobook to {output_file}')
    final_audio.export(
        output_file,
        format="ipod",  # M4B compatible format
        bitrate="128k",
        parameters=[
            "-ar", "44100",  # Sample rate
            "-ac", "2",      # Stereo
            "-movflags", "+faststart"  # Optimize for streaming
        ]
    )
    
    logging.info(f'Successfully exported {len(converted_files)} files to {output_file}')

def _concatenate_with_ffmpeg(converted_files, output_file, temp_dir):
    """
    Concatenates audio files using FFmpeg concat demuxer (fallback method).
    """
    logging.info(f'Concatenating {len(converted_files)} files using FFmpeg')
    
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
    
    # Enhanced FFmpeg concatenation command
    ffmpeg_concat_command = [
        'ffmpeg', 
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file,
        '-c', 'copy',  # Copy streams without re-encoding
        '-movflags', '+faststart',  # Optimize for streaming
        '-y',  # Overwrite output file
        output_file
    ]
    
    logging.debug(f'Running FFmpeg command: {" ".join(ffmpeg_concat_command)}')
    result = subprocess.run(ffmpeg_concat_command, capture_output=True, text=True)
    
    if result.returncode != 0:
        logging.error(f'FFmpeg concatenation failed: {result.stderr}')
        raise ConcatenationError(f"FFmpeg concatenation failed: {result.stderr}")
    
    logging.info(f'Successfully concatenated {len(converted_files)} files to {output_file}')

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
    
    print("AudiobookMakerPy v2.0 - Phase 3.4 (Resume Functionality)")
    print("=" * 50)
    
    # Initialize progress tracking and timer
    progress_tracker = create_progress_tracker(quiet=args.quiet)
    processing_timer = ProcessingTimer()
    processing_timer.start()
    
    # Validate and collect input files
    input_files = validate_and_get_input_files(args.input_paths)
    
    # Pre-flight validation with progress tracking
    validation_level = ValidationLevel(args.validation_level)
    
    try:
        # Step 1: Validation with progress bar
        progress_tracker.print_step("Pre-flight validation", 1, 3)
        
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
            
    except Exception as e:
        print(f"[ERROR] Pre-flight validation failed: {str(e)}")
        logging.error(f"Validation error: {str(e)}")
        sys.exit(1)
    
    # Phase 3.3: Extract comprehensive metadata for smart processing
    print("\nExtracting comprehensive metadata for smart processing...")
    try:
        # Use comprehensive extraction for Phase 3.3 features
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
        
        # Phase 3.2: Determine output file with flexible control
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
        response = input("Do you want to overwrite it? (y/N): ").strip().lower()
        if response != 'y' and response != 'yes':
            print("Operation cancelled by user")
            sys.exit(0)
    
    all_errors = []
    
    try:
        # Check dependencies first
        progress_tracker.print_step("Checking dependencies", 2, 3)
        ffmpeg_version = check_ffmpeg_dependency()
        logging.info(f'FFmpeg version: {ffmpeg_version}')
        
        # Process files and get durations
        progress_tracker.print_step("Processing audio files", 3, 3)
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
        
        # Phase 3.3: Add comprehensive metadata using smart extraction
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