# Custom exceptions
class ConversionError(Exception):
    """Raised when there is a problem with audio file conversion."""
    pass

class AudioDurationError(Exception):
    """Raised when there is a problem getting the duration of an audio file."""
    pass

class AudioPropertiesError(Exception):
    """Raised when there is a problem getting the properties of an audio file."""
    pass

class MetadataError(Exception):
    """Raised when there is a problem with copying metadata from one file to another."""
    pass

# Standard library imports
import sys
import os
import subprocess
import tempfile
import logging
import shutil
import re
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor

# Global variables
max_cpu_cores = os.cpu_count()  # Number of cores to use for parallel processing, use all available cores by default
tempdir = None

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
        raise AudioDurationError(f"Getting duration of {input_file} failed.") from e

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
        raise AudioPropertiesError(f"Getting properties of {input_file} failed.") from e

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
        raise ConversionError(f"Conversion of {input_file} failed.") from e

    return output_file

def create_metadata_file(tempdir, input_files, durations):
    """
    Creates a metadata file for chapters based on the durations of the input audio files.

    The function generates a metadata file containing chapter timestamps and names.
    For each input file, it computes the start and end times based on the duration of the audio file,
    and then writes this information to the metadata file in the format required by MP4Box for chapter information.

    Args:
        tempdir (str): The directory where the metadata file will be created.
        input_files (list of str): A list of paths of the input audio files.
        durations (list of int): A list of durations of the input audio files in milliseconds.

    Returns:
        str: The path of the created metadata file.
    """
    # Define the path of the metadata file
    metadata_file = os.path.join(tempdir, 'chapters.txt')

    # Open the metadata file in write mode
    with open(metadata_file, 'w') as f:
        # Initialize start time for first chapter
        start = 0
        # Loop through each input file and its corresponding duration
        for i, (_, duration) in enumerate(zip(input_files, durations)):
                        # Compute the end time for the current chapter
            end = start + duration
            # Write the chapter timestamp and name to the metadata file
            f.write(f'CHAPTER{i+1}={ms_to_timestamp(start)}\nCHAPTER{i+1}NAME=Chapter {i+1}\n')
            # Update the start time for the next chapter
            start = end

    # Return the path of the metadata file
    return metadata_file

def copy_metadata(input_file, output_file):
    """Copies metadata from the first input file to the output file.

    Args:
        input_file (str): Path to the first input audio file.
        output_file (str): Path to the output audio file.
        tempdir (str): Path to the temporary directory used for conversion.
    """
    # Log the start of the metadata copying process
    logging.info(f'Copying metadata from {input_file} to {output_file}')
    
    # Create a temporary file in the same directory as output_file
    output_dir = os.path.dirname(output_file)
    output_temp_file = os.path.join(output_dir, 'temp_' + os.path.basename(output_file))

    # Prepare the command for ffmpeg to copy the metadata
    ffmpeg_command = ['ffmpeg', '-i', output_file, '-i', input_file, '-map', '0', '-map_metadata', '1', '-c', 'copy', '-y', output_temp_file]
    
    try:
        # Run the ffmpeg command
        subprocess.run(ffmpeg_command, check=True)

        # Remove the original output file
        if os.path.exists(output_file):
            os.remove(output_file)

        # Rename the temp output file to the original output file
        os.rename(output_temp_file, output_file)

    except subprocess.CalledProcessError as e:
        # Log the error if there's an issue with the metadata copying process
        logging.error(f'Error occurred while copying metadata from {input_file} to {output_file}: {str(e)}')

        # Check if the temp output file was created
        if os.path.exists(output_temp_file):
            # If it was created, remove it because the metadata copying process was not successful
            os.remove(output_temp_file)
        
        # Raise an exception to stop the script due to the error
        raise MetadataError(f"Copying metadata from {input_file} to {output_file} failed.") from e

def process_audio_files(input_files, output_file):
    """Processes audio files, converts them to AAC, creates metadata, and concatenates the files.

    Args:
        input_files (list): List of paths to input audio files.
        output_file (str): Path to output audio file.

    Returns:
        str: Path to the temporary directory used for conversion.
    """
    global tempdir

    durations = []
    audio_properties = []
    
    for f in input_files:
        duration = get_audio_duration(f)
        properties = get_audio_properties(f)

        durations.append(duration)
        audio_properties.append(properties)

    tempdir = tempfile.mkdtemp()

    try:
        with ProcessPoolExecutor(max_workers=max_cpu_cores) as executor:
            # Log the start of the conversion process
            logging.info(f'Converting {len(input_files)} files to AAC')
            # Define a list of future tasks for conversion
            future_tasks = [executor.submit(convert_to_aac, input_file, os.path.join(tempdir, os.path.splitext(os.path.basename(input_file))[0] + '_converted.m4a'), properties['bit_rate'] // 1000)
                            for input_file, properties in zip(input_files, audio_properties)]
            # Update the input files with the results of the tasks
            input_files = [future.result() for future in future_tasks]

        logging.info('Creating metadata file')
        metadata_file = create_metadata_file(tempdir, input_files, durations)

        logging.info(f'Concatenating {len(input_files)} files')
        mp4box_concat_command = ['MP4Box', '-force-cat', '-chap', metadata_file] + [arg for f in input_files for arg in ['-cat', f]] + [output_file]
        subprocess.run(mp4box_concat_command, check=True)

    except ConversionError as e:
        logging.error(f'A conversion error occurred: {str(e)}')
        shutil.rmtree(tempdir)
        sys.exit(1)

def setup_logging():
    """
    Sets up the logging configuration for the application.

    This function initializes the logging module with basic configurations. It sets the logging level to INFO and 
    formats the log messages to include the timestamp, the level of the message, and the actual message. 

    It also generates a unique filename for the log file based on the current date and time to ensure that logs 
    from different runs of the application do not overwrite each other.
    """
    now = datetime.now()
    dt_string = now.strftime("%Y-%m-%d_%H-%M-%S")
    logging.basicConfig(filename=f'logfile_{dt_string}.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_arguments():
    """
    Parses and validates command line arguments for the application.

    This function expects at least one argument (excluding the script name itself), which should 
    be a path to an input file or directory. Multiple paths can be passed. If no arguments are 
    provided or the provided arguments are invalid, an error message is logged, usage instructions 
    are printed to the console, and the program exits with status code 1.

    Returns:
        list: The list of command line arguments (excluding the script name), which are the paths 
        to input files or directories.
    """
    if len(sys.argv) < 2:
        print("Usage: python AudiobookMakerPy.py <input_path> [<input_path2> <input_path3> ...]")
        logging.error("Invalid number of input paths")
        sys.exit(1)

    return sys.argv[1:]

def validate_and_get_input_files(input_paths):
    """
    Validates and retrieves all valid audio files from the provided input paths.

    This function takes as input a list of paths. Each path can either be a directory or a file.
    If it is a directory, the function retrieves all audio files (with extensions: '.mp3', '.wav', '.m4a', 
    '.flac', '.ogg', '.aac', '.m4b') in the directory. If it is a file, the function adds the file to the 
    list of input files, given it has a valid audio extension. The function then sorts the list of input 
    files using a natural key sorting algorithm.

    If a provided path is neither a directory nor a file, or does not have a valid audio extension, 
    the function prints an error message and the program exits with status code 1.

    Args:
        input_paths (list): A list of paths to directories or files.

    Returns:
        list: A sorted list of valid audio files from the provided paths.

    Raises:
        SystemExit: If a path is neither a directory nor a file, or if a file does not have a valid audio extension.
    """
    input_files = []
    for input_path in input_paths:
        if os.path.isdir(input_path):
            folder_path = input_path
            folder_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.m4b'))]
            input_files.extend(folder_files)
        elif os.path.isfile(input_path):
            input_files.append(input_path)
        else:
            print(f"Invalid input path: {input_path}")
            sys.exit(1)

    input_files.sort(key=natural_keys)
    return input_files

def get_output_file(input_files):
    """
    Generates the output file path based on the first file in the list of input files.

    This function constructs the output file path by taking the directory of the first file 
    in the list of input files and appending the base name of this directory with the '.m4b' 
    extension. This output file path is intended to be used for saving the audiobook file.

    Args:
        input_files (list): A list of file paths to the input audio files.

    Returns:
        str: The output file path for the audiobook.
    """
    folder_path = os.path.dirname(input_files[0])
    output_name = os.path.basename(folder_path) + '.m4b'
    return os.path.join(folder_path, output_name)

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
    setup_logging()

    input_paths = parse_arguments()
    input_files = validate_and_get_input_files(input_paths)
    output_file = get_output_file(input_files)

    process_audio_files(input_files, output_file)
    copy_metadata(input_files[0], output_file)

    cleanup_tempdir()

    logging.info('Audiobook creation complete.')