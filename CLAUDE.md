# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Direct Python execution
python AudiobookMakerPy.py <input_path> [<input_path2> <input_path3> ...]

# Using the batch file (Windows drag-and-drop interface)
AudiobookMakerPy.bat
```

### Dependencies
This project requires external dependencies that must be installed separately:
- **Python 3.x** - Core runtime
- **FFmpeg** - Audio processing and metadata extraction
- **MP4Box (GPAC)** - Audio concatenation and chapter creation

No Python package dependencies are used - the script relies only on standard library modules.

## Code Architecture

### Core Components

**AudiobookMakerPy.py** - Single-file application with these key architectural elements:

1. **Custom Exception Hierarchy**
   - `ConversionError` - Audio conversion failures
   - `AudioDurationError` - Duration extraction failures  
   - `AudioPropertiesError` - Metadata extraction failures
   - `MetadataError` - Metadata copying failures

2. **Audio Processing Pipeline**
   - `get_audio_properties()` - Extracts codec, sample rate, channels, bitrate using ffprobe
   - `get_audio_duration()` - Gets file duration in milliseconds using ffprobe
   - `convert_to_aac()` - Converts audio files to AAC format using ffmpeg
   - Parallel processing using `ProcessPoolExecutor` with all available CPU cores

3. **Chapter Management**
   - `create_metadata_file()` - Generates chapter timestamps based on file durations
   - `ms_to_timestamp()` - Converts milliseconds to HH:MM:SS.mmm format
   - Chapter names auto-generated as "Chapter 1", "Chapter 2", etc.

4. **File Processing**
   - `natural_keys()` / `atoi()` - Natural sorting for proper file ordering
   - Supports: .mp3, .wav, .m4a, .flac, .ogg, .aac, .m4b extensions
   - Input validation for files and directories
   - Output naming based on parent directory name

5. **Metadata Operations**
   - `copy_metadata()` - Copies metadata from first input file to final output
   - Uses temporary files to avoid data corruption during metadata copying

### Processing Flow
1. Parse and validate input paths (files or directories)
2. Extract audio properties and durations from all input files
3. Convert all files to AAC format in parallel using all CPU cores
4. Create chapter metadata file with timestamps
5. Concatenate converted files using MP4Box with chapter information
6. Copy metadata from first input file to final output
7. Clean up temporary directory

### Output
- Creates `.m4b` audiobook file in same directory as input
- Generates timestamped log files: `logfile_YYYY-MM-DD_HH-MM-SS.log`
- Uses temporary directory for intermediate files (auto-cleaned)

## Test Files

The repository includes 4 sets of test audio files in the `testfiles/` directory:

1. **book1mp3/** - MP3 format test files
   - 01 - Opening Credits & Introduction.mp3
   - 02 - Chapter 1.mp3
   - 03 - Chapter 2.mp3
   - 04 - Chapter 3.mp3
   - 05 - Chapter 4.mp3

2. **book2mp3/** - MP3 format test files (different naming convention)
   - 01 Intro Volume 1.mp3
   - 02 The Book of Blood.mp3
   - 03 The Midnight Meat Train.mp3
   - 04 The Yattering and Jack.mp3

3. **book3aac/** - AAC format test files
   - 01-Intro Volume 1.aac
   - 02-The Book of Blood.aac
   - 03-The Midnight Meat Train.aac
   - 04-The Yattering and Jack.aac

4. **book4m4a/** - M4A format test files
   - 1.Intro Volume 1.m4a
   - 2.The Book of Blood.m4a
   - 3.The Midnight Meat Train.m4a
   - 4.The Yattering and Jack.m4a

These test files can be used to validate functionality across different audio formats and naming conventions.

## Test Cover Art

The repository includes test cover art images in the `testfiles/coverart/` directory:

- **9780062562982.bmp** - BMP format cover art
- **9780062562982.jpg** - JPEG format cover art  
- **9780063095588.bmp** - BMP format cover art
- **9780063095588.jpg** - JPEG format cover art
- **9780241995648.jpg** - JPEG format cover art
- **9780241995648.png** - PNG format cover art
- **9781529046076.jpg** - JPEG format cover art
- **9781529046076.png** - PNG format cover art

These cover art files can be used to test Phase 3.3 smart metadata extraction features, particularly the `--cover` argument for embedding cover art in audiobooks. The files include both supported formats (JPEG, PNG) and unsupported formats (BMP) for validation testing.