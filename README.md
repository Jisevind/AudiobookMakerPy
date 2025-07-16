# AudiobookMakerPy

**A comprehensive Python package for converting audio files to M4B audiobook format with smart metadata extraction and chapter generation.**

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey.svg)](https://github.com/audiobookmaker/AudiobookMakerPy)
[![FFmpeg](https://img.shields.io/badge/requires-FFmpeg-red.svg)](https://ffmpeg.org/)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://pytest.org/)

## Overview

AudiobookMakerPy is a tool that converts multiple audio files into a single M4B audiobook with intelligent chapter detection, metadata extraction, and resume functionality. Perfect for creating audiobooks from podcast episodes, lecture recordings, or any collection of audio files.

## Key Features

- **Smart Processing**: Automatic file ordering with natural sorting
- **Intelligent Chapters**: Auto-generated chapter titles from filenames
- **Metadata Extraction**: Preserves and enhances audio metadata
- **Cover Art Support**: Embed JPEG/PNG cover art
- **Resume Functionality**: Intelligent caching and resume capabilities
- **Parallel Processing**: Multi-core audio conversion
- **Robust Error Handling**: Comprehensive error recovery and reporting
- **Progress Tracking**: Real-time progress monitoring
- **Multiple Quality Presets**: Low, medium, high, and custom bitrates
- **Comprehensive Validation**: Multi-level audio file validation

## Installation

### Requirements

**External Dependencies:**
- **FFmpeg** - Audio processing, conversion, and concatenation
- **Python 3.7+** - Runtime environment

### Quick Install

```bash
# Clone or download the project
cd AudiobookMakerPy

# Install the package
pip install -e .

# Or install with enhanced features
pip install -e .[enhanced]
```

### Dependency Installation

Use the provided script to install external dependencies:

```bash
# Unix/Linux/macOS
chmod +x scripts/install_deps.sh
./scripts/install_deps.sh

# Windows
# Download FFmpeg manually from https://ffmpeg.org/download.html
# Add to PATH environment variable
```

## Usage

### Command Line Interface

```bash
# Basic usage
audiobookmaker /path/to/audio/files/

# With custom settings
audiobookmaker /path/to/files/ --title "My Audiobook" --author "Author Name" --quality high

# Multiple directories
audiobookmaker /path/to/book1/ /path/to/book2/ --output-dir /audiobooks/

# With cover art
audiobookmaker /path/to/files/ --cover cover.jpg --bitrate 192k
```

### Advanced Options

```bash
# Custom output and metadata
audiobookmaker /path/to/files/ \
    --output-name "My Custom Audiobook" \
    --template "{author} - {title} ({year})" \
    --chapter-titles auto

# Performance tuning
audiobookmaker /path/to/files/ \
    --cores 8 \
    --quality high \
    --validation-level strict

# Resume interrupted processing
audiobookmaker /path/to/files/ --resume auto
audiobookmaker /path/to/files/ --resume force
audiobookmaker /path/to/files/ --clear-cache  # Start fresh
```

### Quality Presets

| Preset | Bitrate | Use Case |
|--------|---------|----------|
| `low` | 96k | Podcasts, voice-only content |
| `medium` | 128k | General audiobooks (default) |
| `high` | 192k | Music, high-quality content |
| `custom` | User-defined | Use with `--bitrate` |

### Programmatic Usage

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
    title="My Audiobook",
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

## Project Structure

```
AudiobookMakerPy/
├── src/audiobookmaker/          # Main package
│   ├── core/                    # Core functionality
│   │   ├── processor.py         # Main processing orchestrator
│   │   ├── converter.py         # Audio conversion
│   │   ├── concatenator.py      # Audio concatenation
│   │   └── metadata.py          # Metadata handling
│   ├── utils/                   # Utility functions
│   │   ├── validation.py        # Input validation
│   │   ├── progress_tracker.py  # Progress tracking
│   │   ├── resource_manager.py  # Resource management
│   │   └── file_utils.py        # File operations
│   ├── exceptions.py            # Custom exceptions
│   └── cli.py                   # Command-line interface
├── tests/                       # Test suite
├── docs/                        # Documentation
├── scripts/                     # Build and utility scripts
├── examples/                    # Usage examples
├── legacy/                      # Original script (reference)
└── testfiles/                   # Test data
```

## Supported Audio Formats

- **MP3** (.mp3) - Most common format
- **WAV** (.wav) - Uncompressed audio
- **M4A** (.m4a) - Apple's format
- **FLAC** (.flac) - Lossless compression
- **OGG** (.ogg) - Open source format
- **AAC** (.aac) - Advanced Audio Coding
- **M4B** (.m4b) - Audiobook format

## File Naming Best Practices

For optimal chapter detection and ordering:

```
✅ Good Examples:
├── 01 - Introduction.mp3
├── 02 - Chapter 1 - The Beginning.mp3
├── 03 - Chapter 2 - The Journey.mp3
├── 04 - Chapter 3 - The End.mp3
└── 05 - Conclusion.mp3

✅ Also Good:
├── Chapter 01 - Introduction.mp3
├── Chapter 02 - The Story Begins.mp3
├── Track 01 - Opening.mp3
└── Part 1 - First Section.mp3

❌ Avoid:
├── audio_file.mp3
├── untitled.mp3
└── random_name.mp3
```

## 🔧 Configuration

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--title`, `-t` | Audiobook title | Auto-detected |
| `--author`, `-a` | Author name | Auto-detected |
| `--output`, `-o` | Output file path | Auto-generated |
| `--bitrate`, `-b` | Audio bitrate | 128k |
| `--cores`, `-c` | CPU cores to use | All available |
| `--quality` | Quality preset | medium |
| `--validation-level` | Validation strictness | normal |
| `--resume` | Resume mode | auto |
| `--cover` | Cover art path | None |
| `--chapter-titles` | Chapter title mode | auto |

### Environment Variables

```bash
export AUDIOBOOKMAKER_CACHE_DIR="/custom/cache"
export AUDIOBOOKMAKER_LOG_LEVEL="DEBUG"
export AUDIOBOOKMAKER_MAX_CORES="4"
```

## Testing

```bash
# Run all tests
python -m pytest tests/

# Run with coverage
python -m pytest tests/ --cov=src/audiobookmaker

# Test specific functionality
python -m pytest tests/test_core/test_processor.py -v

# Test with sample files
audiobookmaker testfiles/book1mp3/ --output test_output.m4b
```

## Development

### Setup Development Environment

```bash
# Install in development mode
pip install -e .[dev]

# Run linting
python scripts/build.py lint

# Format code
python scripts/build.py format

# Run tests
python scripts/build.py test

# Build package
python scripts/build.py build
```

### Build Scripts

```bash
# Available build commands
python scripts/build.py clean      # Clean build artifacts
python scripts/build.py test       # Run test suite
python scripts/build.py lint       # Run linting
python scripts/build.py format     # Format code
python scripts/build.py build      # Build package
python scripts/build.py install-dev # Install in dev mode
python scripts/build.py release    # Create release
```

## Troubleshooting

### Common Issues

1. **FFmpeg not found**
   ```bash
   # Install FFmpeg
   sudo apt install ffmpeg  # Ubuntu/Debian
   brew install ffmpeg      # macOS
   # Windows: Download from https://ffmpeg.org/
   ```

2. **Permission errors**
   ```bash
   # Check file permissions
   ls -la /path/to/files/
   chmod 644 /path/to/files/*
   ```

3. **Memory issues**
   ```bash
   # Use fewer cores
   audiobookmaker /path/to/files/ --cores 2 --quality low
   ```

4. **Import errors**
   ```bash
   # Reinstall in development mode
   pip uninstall audiobookmaker
   pip install -e .
   ```

### Debug Mode

```bash
# Enable verbose logging
audiobookmaker /path/to/files/ --validation-level paranoid

# Check log files
ls -la logfile_*.log
```

For detailed troubleshooting, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Documentation

- **[Usage Guide](docs/USAGE.md)** - Comprehensive usage examples
- **[API Reference](docs/API.md)** - Developer documentation
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions
- **[Changelog](docs/CHANGELOG.md)** - Version history

## Migration from v1.x

### Command Changes

```bash
# Old (v1.x)
python AudiobookMakerPy.py /path/to/files/

# New (v2.x)
audiobookmaker /path/to/files/
```

### API Changes

```python
# Old (v1.x)
from AudiobookMakerPy import process_audiobook

# New (v2.x)
from audiobookmaker import AudiobookProcessor
processor = AudiobookProcessor()
result = processor.process_audiobook(["/path/to/files/"])
```

The legacy script is preserved in `legacy/` for reference.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **FFmpeg** - The backbone of audio processing and concatenation
- **Python Community** - For excellent libraries and tools

## Support

- **GitHub Issues**: [Report bugs and request features](https://github.com/audiobookmaker/AudiobookMakerPy/issues)
- **Documentation**: [Complete documentation](docs/)
- **Examples**: [Usage examples](examples/)

---

**AudiobookMakerPy** - Professional audiobook creation made simple.