# AudioBookMakerPy
This script is designed to concatenate multiple audio files and convert them into an AAC (Advanced Audio Coding) format, specifically the `.m4b` format, which is often used for audiobooks. It is built using Python and leverages the powerful FFmpeg and MP4Box tools for audio processing.

The script performs the following key tasks:

1. **Retrieve audio properties**: It extracts information about the audio codec, sample rate, number of channels, and bitrate of the input files.
2. **Audio file conversion**: It converts the input audio files to AAC format while preserving the original bitrate. The conversion is done with parallel processing to speed things up, it uses all available cores by default.
3. **Concatenation of audio files**: It concatenates the converted audio files in the order they are provided. It also adds chapter markers based on the individual files.
4. **Copy metadata**: It copies the metadata from the first input file.
5. **Error handling and logging**: It handles potential errors during the process and logs useful information for troubleshooting purposes.

## Requirements

To use this script, make sure to have FFmpeg, MP4Box, and Python installed in your environment. 

Download from here:

Python:

https://www.python.org/

FFmpeg:

https://ffmpeg.org/

MP4Box: 

https://gpac.wp.imt.fr/downloads/

## Usage

You can run the script from the command line as follows:

```shell
python mp4box_to_m4b.py <input_path> [<input_path2> <input_path3> ...]
```
Here, **'<input_path>'** is the path to the input audio file or directory containing audio files. You can specify multiple input paths. If a directory is specified, the script will process all audio files in that directory.

you can use the existing `AudioBookMakerPy.bat` batch file for a more user-friendly experience.

With `AudioBookMakerPy.bat`, you can simply drag and drop a folder or individual audio files onto the batch file icon. The batch file will trigger the Python script and process the audio files or the entire folder, depending on what you've dropped. Here are the steps:

1. Locate the `AudioBookMakerPy.bat` file in your system.
2. Drag and drop the folder or audio files that you want to process onto the `AudioBookMakerPy.bat` file. 

   - If you drop a folder, the script will process all supported audio files in the directory.
   - If you drop individual files, the script will process and concatenate those files in the order they were selected.

## Preparing Your Files

Before running the script, it's important to properly name your audio files. This will ensure they are processed in the correct order and the resulting audiobook file is structured correctly.

Here are some guidelines for naming your files:

1. **File Order**: Files are processed in alphanumeric order. This means a file named 'Chapter1.mp3' will be processed before 'Chapter2.mp3', 'Chapter10.mp3', etc. Make sure the filenames reflect the order you want them to appear in the final audiobook.

2. **Numbering**: When numbering files, it's recommended to use leading zeros for numbers less than 10 (and less than 100 for books with more than 99 chapters). For example, use 'Chapter01.mp3', 'Chapter02.mp3', ..., 'Chapter10.mp3', etc. This ensures the files are sorted correctly by the script.

3. **Special Cases**: If there are multiple parts or versions of the same chapter or section, you can denote this in the filename using parentheses. For example, 'Chapter01(1).mp3', 'Chapter01(2).mp3', etc. Please note that the script treats the parentheses and the number inside as a single part, so 'Chapter01(2).mp3' will come after 'Chapter01.mp3' and 'Chapter01(1).mp3'.

By properly naming your files, you can ensure the script processes them correctly and the final audiobook is structured as intended.

**Note:** 

- The `AudioBookMakerPy.bat` batch file should be located in the same directory as your Python script for this to work. It's already provided, so you don't need to create it.
- The batch file is configured as follows:

```shell
@echo off
pushd %~dp0
python AudiobookMakerPy.py %*
popd
pause
```

The script will output an **'.m4b'** file in the same directory as the first input file or directory. The output file will have the same name as the directory (or the name of the first file's directory if multiple files are provided). If any errors occur during the process, they will be logged in a file named **'logfile_<timestamp>.log'**.

## Note

* The script currently supports audio files with **'.mp3'**, **'.wav'**, **'.m4a'**, **'.flac'**, **'.ogg'**, and **'.aac'** extensions.
* The script handles errors gracefully and logs any issues during the processing of the files. Please check the log file for troubleshooting any issues.
* The script uses a temporary directory for intermediate files which is deleted at the end of the process. If the script is interrupted or an error occurs, you may need to manually delete this directory.
* The script assumes that FFmpeg, MP4Box and the necessary Python packages are installed and available in your system's PATH. Please ensure you have these installed and configured correctly.