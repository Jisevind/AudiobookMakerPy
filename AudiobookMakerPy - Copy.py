import sys
import os
import subprocess
import tempfile
import logging
import shutil
import re
from datetime import datetime

tempdir = None

# Get current date and time
now = datetime.now()

# Convert date and time to string
dt_string = now.strftime("%Y-%m-%d_%H-%M-%S")

# Set up logging to a file
logging.basicConfig(filename=f'logfile_{dt_string}.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def atoi(text):
    # Converts a digit string to an integer, otherwise returns the original string
    return int(text) if text.isdigit() else text

def natural_keys(text):
    # Splits the input text at each digit and applies atoi function to each part for natural sorting
    return [atoi(c) for c in re.split(r'(\d+)', text)]

def get_audio_duration(input_file):
    logging.info(f'Getting duration for {input_file}')
    ffprobe_command = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
    try:
        output = subprocess.check_output(ffprobe_command).decode('utf-8').strip()
        return int(float(output) * 1000)  # convert duration from seconds to milliseconds
    except subprocess.CalledProcessError as e:
        logging.error(f'Error occurred while getting duration for {input_file}: {str(e)}')
        return None

def get_audio_properties(input_file):
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
        return None

def ms_to_timestamp(ms):
    # convert milliseconds to timestamp format (HH:MM:SS.mmm)
    seconds, ms = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{ms:03}"
    
def convert_to_aac(input_file, output_file, bitrate):
    # Log the start of the conversion process
    logging.info(f'Converting {input_file} to AAC')
    
    # Prepare the command for ffmpeg to convert the input file to AAC format
    ffmpeg_command = ['ffmpeg', '-i', input_file, '-vn', '-acodec', 'libfdk_aac', '-b:a', f'{bitrate}k', '-ar', '44100', '-ac', '2', output_file]
    
    try:
        # Run the ffmpeg command
        subprocess.run(ffmpeg_command, check=True)

        # If the original file was .m4b, rename the output file to .m4a
        if output_file.lower().endswith('.m4b'):
            new_output_file = output_file.replace('.m4b', '.m4a')
            os.rename(output_file, new_output_file)
            return new_output_file

    except subprocess.CalledProcessError as e:
        # Log the error if there's an issue with the conversion process
        logging.error(f'Error occurred while converting {input_file} to AAC: {str(e)}')
        
        # Check if the output file was created
        if os.path.exists(output_file):
            # If it was created, remove it because the conversion process was not successful
            os.remove(output_file)
        
        # Raise an exception to stop the script due to the error
        raise Exception("Aborting script.")

    return output_file

def create_metadata_file(tempdir, input_files, durations):
    logging.info('Creating metadata file')
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
        
        # Don't raise an exception, just log the error and continue
        logging.info('Continuing script execution despite error.')

def concatenate_audio_files(input_files, output_file):
    global tempdir

    # Log the start of the concatenation process
    logging.info(f'Concatenating {len(input_files)} files')

    durations = []  # List to store the duration of each audio file
    audio_properties = []  # List to store the properties of each audio file
    
    # Loop through each input file
    for f in input_files:
        # Get the duration and properties of the current audio file
        duration = get_audio_duration(f)
        properties = get_audio_properties(f)

        # If the duration or properties could not be retrieved, log an error and skip this file
        if duration is None or properties is None:
            logging.error(f'Skipping {f} due to error')
            continue

        # Append the duration and properties to their respective lists
        durations.append(duration)
        audio_properties.append(properties)

    # Create a temporary directory to store the converted audio files
    tempdir = tempfile.mkdtemp()

    try:
        # Loop through each input file
        for i, input_file in enumerate(input_files):
            # Define the path of the converted file
            converted_file = os.path.join(tempdir, os.path.splitext(os.path.basename(input_file))[0] + '_converted.m4a')
            # Convert the current audio file to AAC format and update the list of input files
            converted_file = convert_to_aac(input_file, converted_file, audio_properties[i]['bit_rate'] // 1000)
            input_files[i] = converted_file

        # Create a metadata file with chapters based on the durations of the audio files
        metadata_file = create_metadata_file(tempdir, input_files, durations)

        # Prepare the command for MP4Box to concatenate the audio files and add chapters
        mp4box_concat_command = ['MP4Box', '-force-cat', '-chap', metadata_file] + [arg for f in input_files for arg in ['-cat', f]] + [output_file]
        # Run the MP4Box command
        subprocess.run(mp4box_concat_command, check=True)

    except Exception as e:
        # Log the error and clean up the temporary directory if an error occurs
        logging.error(f'An error occurred: {str(e)}')
        shutil.rmtree(tempdir)
        # Exit the script due to the error
        sys.exit(1)

    # Clean up the temporary directory after the concatenation process is complete
    # shutil.rmtree(tempdir)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python AudiobookMakerPy.py <input_path> [<input_path2> <input_path3> ...]")
        logging.error("Invalid number of input paths")
        sys.exit(1)

    input_paths = sys.argv[1:]
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
    folder_path = os.path.dirname(input_files[0])
    output_name = os.path.basename(folder_path) + '.m4b'
    output_file = os.path.join(folder_path, output_name)

    concatenate_audio_files(input_files, output_file)
    copy_metadata(input_files[0], output_file)

    # Now remove the temporary directory
    shutil.rmtree(tempdir)