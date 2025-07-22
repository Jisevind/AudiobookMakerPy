# Changelog

All notable changes to AudiobookMakerPy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2025-01-22

### Added
- **PyQt6 GUI Interface**: Complete graphical user interface with tabbed design
  - Drag-and-drop file management with natural sorting
  - Real-time processing logs with FFmpeg command visibility
  - Cover art preview and management
  - Quality presets and metadata controls
  - Smart chapter title generation options
- **Executable Building**: PyInstaller configuration for standalone executables
  - Windows executable with custom icon integration
  - Linux executable support
  - Automated build scripts with dependency checking
- **Icon Integration**: Custom application icon throughout the interface
  - Window title bar and taskbar icons
  - Enhanced About dialog with branding
  - Cross-platform icon loading with fallback paths
- **Enhanced Processing**: 
  - Console window hiding for Windows compatibility
  - Module-level worker functions for PyInstaller compatibility
  - Multiprocessing spawn method for cross-platform support
  - Command capture and logging interception for GUI feedback

### Changed
- **Core Modules**: Updated converter, concatenator, and metadata modules with subprocess improvements
- **Multiprocessing**: Enhanced compatibility with PyInstaller executables
- **Dependencies**: Added PyQt6 and PyInstaller to requirements

### Fixed
- **Windows Compatibility**: Resolved console window flashing issues
- **Multiprocessing Issues**: Fixed PyInstaller worker process spawning
- **GUI Responsiveness**: Non-blocking audio processing with threading

## [2.0.0] - 2025-07-16

### Added
- **Major Architecture Refactor**: Complete restructuring into modular package
- **New Package Structure**: Organized into `src/audiobookmaker/` with proper modules
- **Modern Python Packaging**: Added `pyproject.toml` and proper package configuration
- **Enhanced API**: Programmatic access via `AudiobookProcessor` class
- **Comprehensive Documentation**: Complete API documentation and usage guides
- **Test Structure**: Organized test framework with proper test discovery
- **Development Tools**: Black, isort, mypy, and pytest configuration

### Changed
- **BREAKING**: Moved from single script to proper Python package
- **BREAKING**: CLI now requires `audiobookmaker` command instead of `python AudiobookMakerPy.py`
- **BREAKING**: Import paths changed for programmatic usage
- **Improved Error Handling**: Better error classification and user messages
- **Enhanced Logging**: More detailed logging with proper levels
- **Better Resource Management**: Improved memory and CPU management

### Fixed
- **Memory Efficiency**: Better memory usage during processing
- **Error Recovery**: Improved error handling and recovery mechanisms
- **Resume Functionality**: More reliable resume detection and processing
- **Validation Logic**: Better audio file validation and error reporting

### Removed
- **Legacy Dependencies**: Cleaned up outdated code and approaches

## [1.x.x] - Previous Versions

### Features from Previous Versions
- Audio file conversion to M4B format
- Smart metadata extraction
- Chapter generation from filenames
- Resume functionality for interrupted processing
- Parallel processing with multiple CPU cores
- Cover art embedding
- Multiple audio format support (MP3, WAV, M4A, FLAC, OGG, AAC)
- Validation system with multiple levels
- Progress tracking and reporting
- Resource monitoring and management
- Intelligent caching system
- Batch processing capabilities

### Dependencies
- FFmpeg (external dependency for audio processing and concatenation)
- Python 3.7+ (runtime)
- Optional: mutagen, pydub (enhanced features)

## Migration Guide (1.x → 2.0)

### For CLI Users

**Old usage:**
```bash
python AudiobookMakerPy.py /path/to/files/
```

**New usage:**
```bash
# Command line interface
audiobookmaker /path/to/files/

# Graphical interface (v2.1.0+)
python src/audiobookmaker/gui.py
# or use the executable
./dist/AudiobookMaker-GUI
```

### For Programmatic Users

**Old usage:**
```python
# Import from main script
from AudiobookMakerPy import process_audiobook
```

**New usage:**
```python
# Import from package
from audiobookmaker import AudiobookProcessor

processor = AudiobookProcessor()
result = processor.process_audiobook(["/path/to/files/"])
```

### Installation

**Old installation:**
```bash
# Manual script usage
python AudiobookMakerPy.py
```

**New installation:**
```bash
# Package installation
pip install .

# Development installation
pip install -e .[dev]
```

## Upgrade Notes

### Configuration
- Configuration files remain compatible
- Environment variables unchanged
- Log file format unchanged

### Dependencies
- External dependencies (FFmpeg only) unchanged
- Python dependencies now optional (mutagen, pydub)
- Minimum Python version: 3.7

### Breaking Changes
1. **CLI Command**: Use `audiobookmaker` instead of `python AudiobookMakerPy.py`
2. **Import Paths**: All imports now use `audiobookmaker` package
3. **API Changes**: New class-based API for programmatic usage
4. **Package Structure**: Files moved to `src/audiobookmaker/` structure

### Compatibility
- Audio file processing logic unchanged
- Resume functionality preserved
- Metadata extraction behavior preserved
- Output format and quality identical

## Future Roadmap

### Planned Features
- Plugin system for custom processors
- Web interface for remote processing
- Advanced metadata editing
- Batch processing optimization
- Cloud storage integration

### Improvements
- Performance optimization
- Better error reporting
- Enhanced progress tracking
- Memory usage optimization
- Cross-platform compatibility improvements

## Contributing

We welcome contributions! Please see our contributing guidelines for:
- Code style requirements
- Testing procedures
- Documentation standards
- Pull request process

## Support

For issues and questions:
- GitHub Issues: [Report bugs and request features](https://github.com/audiobookmaker/AudiobookMakerPy/issues)
- Documentation: [Read the docs](docs/)
- Troubleshooting: [Common issues and solutions](docs/TROUBLESHOOTING.md)
