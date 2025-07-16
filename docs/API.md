# AudiobookMakerPy API Documentation

## Overview

AudiobookMakerPy provides a Python API for programmatic audiobook creation. This document covers the core classes and functions for developers.

## Core Classes

### AudiobookProcessor

The main class for processing audiobooks.

```python
from audiobookmaker import AudiobookProcessor
from audiobookmaker.utils import ValidationLevel

processor = AudiobookProcessor(
    bitrate="128k",
    cores=4,
    validation_level=ValidationLevel.NORMAL,
    resume_mode="auto"
)

result = processor.process_audiobook(
    input_paths=["/path/to/audio/files/"],
    output_path="/path/to/output.m4b",
    title="My Audiobook",
    author="Author Name"
)
```

#### Parameters

- `bitrate` (str): Audio bitrate (default: "128k")
- `cores` (int): Number of CPU cores to use
- `validation_level` (ValidationLevel): Validation strictness
- `resume_mode` (str): Resume behavior ("auto", "never", "force")
- `progress_tracker`: Optional progress tracking instance
- `quiet` (bool): Reduce output verbosity
- `gui_mode` (bool): GUI mode behavior
- `json_mode` (bool): JSON output mode

#### Methods

##### `process_audiobook()`

Main processing method.

```python
def process_audiobook(
    self,
    input_paths: List[str],
    output_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_name: Optional[str] = None,
    template: str = "{title}",
    title: Optional[str] = None,
    author: Optional[str] = None,
    cover_art_path: Optional[str] = None,
    chapter_titles_mode: str = "auto"
) -> ProcessingResult
```

**Parameters:**
- `input_paths`: List of input file/directory paths
- `output_path`: Explicit output file path
- `output_dir`: Output directory
- `output_name`: Custom output filename
- `template`: Filename template using metadata variables
- `title`: Custom title
- `author`: Custom author
- `cover_art_path`: Path to cover art image
- `chapter_titles_mode`: Chapter title generation mode

**Returns:**
- `ProcessingResult`: Results of the processing operation

### ProcessingResult

Result object returned by `process_audiobook()`.

```python
@dataclass
class ProcessingResult:
    success: bool
    output_file: Optional[str] = None
    total_hours: int = 0
    total_minutes: int = 0
    errors: List[str] = None
    error_message: Optional[str] = None
```

## Utility Classes

### MetadataExtractor

Extracts metadata from audio files.

```python
from audiobookmaker.core.metadata import MetadataExtractor

extractor = MetadataExtractor()
metadata = extractor.extract_comprehensive_metadata(input_files)
```

### AudioConverter

Handles audio file conversion.

```python
from audiobookmaker.core.converter import AudioConverter

converter = AudioConverter(bitrate="128k", cores=4)
durations, errors = converter.process_audio_files(
    input_files, output_file, bitrate, cores
)
```

### ValidationLevel

Enumeration for validation levels.

```python
from audiobookmaker.utils import ValidationLevel

# Available levels
ValidationLevel.LAX
ValidationLevel.NORMAL
ValidationLevel.STRICT
ValidationLevel.PARANOID
```

## Example Usage

### Basic Audiobook Creation

```python
from audiobookmaker import AudiobookProcessor

# Create processor
processor = AudiobookProcessor(
    bitrate="192k",
    cores=8,
    quiet=False
)

# Process audiobook
result = processor.process_audiobook(
    input_paths=["/path/to/audio/files/"],
    title="My Great Audiobook",
    author="Author Name",
    cover_art_path="/path/to/cover.jpg"
)

# Check result
if result.success:
    print(f"Audiobook created: {result.output_file}")
    print(f"Duration: {result.total_hours}h {result.total_minutes}m")
else:
    print(f"Processing failed: {result.error_message}")
```

### Advanced Processing with Custom Settings

```python
from audiobookmaker import AudiobookProcessor
from audiobookmaker.utils import ValidationLevel, create_progress_tracker

# Create progress tracker
progress_tracker = create_progress_tracker(quiet=False)

# Create processor with advanced settings
processor = AudiobookProcessor(
    bitrate="256k",
    cores=16,
    validation_level=ValidationLevel.STRICT,
    resume_mode="force",
    progress_tracker=progress_tracker
)

# Process with custom template
result = processor.process_audiobook(
    input_paths=["/path/to/series1/", "/path/to/series2/"],
    output_dir="/path/to/audiobooks/",
    template="{author} - {title} ({year})",
    chapter_titles_mode="auto"
)
```

### Error Handling

```python
from audiobookmaker import AudiobookProcessor
from audiobookmaker.exceptions import AudiobookMakerError, DependencyError

try:
    processor = AudiobookProcessor()
    result = processor.process_audiobook(
        input_paths=["/path/to/files/"]
    )
    
    if not result.success:
        print(f"Processing failed: {result.error_message}")
        if result.errors:
            print("Detailed errors:")
            for error in result.errors:
                print(f"  - {error}")
                
except DependencyError as e:
    print(f"Dependency error: {e.get_user_message()}")
except AudiobookMakerError as e:
    print(f"Application error: {e.get_user_message()}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Exception Classes

### AudiobookMakerError

Base exception class for all application errors.

```python
class AudiobookMakerError(Exception):
    def get_user_message(self) -> str:
        """Get user-friendly error message"""
```

### DependencyError

Raised when required dependencies are missing.

```python
class DependencyError(AudiobookMakerError):
    def __init__(self, dependency_name: str, details: str):
        self.dependency_name = dependency_name
        self.details = details
```

### ConversionError

Raised when audio conversion fails.

```python
class ConversionError(AudiobookMakerError):
    def __init__(self, message: str, file_path: str, 
                 source_format: str = None, target_format: str = None):
        self.file_path = file_path
        self.source_format = source_format
        self.target_format = target_format
```

## Utility Functions

### File Utilities

```python
from audiobookmaker.utils.file_utils import (
    get_audio_duration,
    natural_keys,
    cleanup_temp_files,
    is_audio_file
)

# Get audio duration in milliseconds
duration = get_audio_duration("/path/to/audio.mp3")

# Natural sorting
files = sorted(file_list, key=natural_keys)

# Check if file is audio
if is_audio_file("/path/to/file.mp3"):
    # Process audio file
    pass
```

### Validation

```python
from audiobookmaker.utils.validation import (
    validate_audio_files,
    ValidationLevel
)

# Validate audio files
valid_files, report = validate_audio_files(
    input_files, 
    ValidationLevel.NORMAL
)
```

## Configuration

### Environment Variables

- `AUDIOBOOKMAKER_CACHE_DIR`: Custom cache directory
- `AUDIOBOOKMAKER_LOG_LEVEL`: Log level (DEBUG, INFO, WARNING, ERROR)
- `AUDIOBOOKMAKER_MAX_CORES`: Maximum CPU cores to use

### Configuration File

Create `~/.audiobookmaker_config.json`:

```json
{
    "default_bitrate": "128k",
    "default_cores": 4,
    "validation_level": "normal",
    "resume_mode": "auto",
    "cache_max_age_days": 30
}
```

## Best Practices

1. **Error Handling**: Always wrap processing in try-catch blocks
2. **Resource Management**: Use appropriate core counts for your system
3. **Validation**: Use appropriate validation levels for your use case
4. **Progress Tracking**: Implement progress tracking for long operations
5. **Memory Management**: Monitor memory usage for large batches

## Performance Tips

1. **Parallel Processing**: Use multiple cores for large batches
2. **Resume Functionality**: Enable resume for long-running operations
3. **Validation Levels**: Use appropriate validation levels
4. **Bitrate Selection**: Balance quality vs. file size
5. **Cache Management**: Clean up old cache files periodically