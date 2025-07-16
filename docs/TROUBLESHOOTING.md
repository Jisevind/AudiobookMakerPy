# AudiobookMakerPy Troubleshooting Guide

## Common Issues and Solutions

### 1. FFmpeg Not Found

**Error Message:**
```
DependencyError: FFmpeg is not installed or not found in system PATH
```

**Solution:**

#### Windows
1. Download FFmpeg from https://ffmpeg.org/download.html
2. Extract to `C:\ffmpeg\`
3. Add `C:\ffmpeg\bin` to your PATH environment variable
4. Restart your command prompt

#### macOS
```bash
# Using Homebrew
brew install ffmpeg

# Using MacPorts
sudo port install ffmpeg
```

#### Linux
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg

# CentOS/RHEL
sudo yum install ffmpeg

# Arch Linux
sudo pacman -S ffmpeg
```

### 2. Permission Errors

**Error Message:**
```
PermissionError: [Errno 13] Permission denied
```

**Solutions:**

1. **Check file permissions:**
   ```bash
   ls -la /path/to/audio/files/
   ```

2. **Fix permissions:**
   ```bash
   chmod 644 /path/to/audio/files/*
   ```

3. **Check disk space:**
   ```bash
   df -h
   ```

4. **Run with appropriate permissions:**
   ```bash
   # Don't use sudo unless necessary
   audiobookmaker /path/to/files/
   ```

### 3. Memory Issues

**Error Message:**
```
MemoryError: Unable to allocate memory
```

**Solutions:**

1. **Reduce CPU cores:**
   ```bash
   audiobookmaker /path/to/files/ --cores 2
   ```

2. **Use lower quality:**
   ```bash
   audiobookmaker /path/to/files/ --quality low
   ```

3. **Process files in smaller batches:**
   ```bash
   # Process one directory at a time
   audiobookmaker /path/to/book1/
   audiobookmaker /path/to/book2/
   ```

4. **Monitor memory usage:**
   ```bash
   # Check available memory
   free -h  # Linux
   vm_stat  # macOS
   ```

### 4. Audio File Validation Errors

**Error Message:**
```
ValidationError: Invalid audio file format
```

**Solutions:**

1. **Check file format:**
   ```bash
   file /path/to/audio/file.mp3
   ```

2. **Use different validation level:**
   ```bash
   # More lenient validation
   audiobookmaker /path/to/files/ --validation-level lax
   
   # More strict validation
   audiobookmaker /path/to/files/ --validation-level strict
   ```

3. **Convert problematic files:**
   ```bash
   # Convert with FFmpeg
   ffmpeg -i problematic_file.mp3 -acodec copy fixed_file.mp3
   ```

### 5. Metadata Extraction Issues

**Error Message:**
```
MetadataError: Unable to extract metadata
```

**Solutions:**

1. **Install optional dependencies:**
   ```bash
   pip install mutagen pydub
   ```

2. **Provide metadata manually:**
   ```bash
   audiobookmaker /path/to/files/ --title "Book Title" --author "Author Name"
   ```

3. **Use generic chapter titles:**
   ```bash
   audiobookmaker /path/to/files/ --chapter-titles generic
   ```

### 6. Resume Functionality Issues

**Error Message:**
```
ProcessingError: Resume forced but no resumable work found
```

**Solutions:**

1. **Check resume mode:**
   ```bash
   # Auto resume (default)
   audiobookmaker /path/to/files/ --resume auto
   
   # Start fresh
   audiobookmaker /path/to/files/ --resume never
   ```

2. **Clear cache:**
   ```bash
   audiobookmaker /path/to/files/ --clear-cache
   ```

3. **Check temp directory:**
   ```bash
   # Check for temp files
   ls -la /tmp/audiobookmaker_*
   ```

### 7. Output File Issues

**Error Message:**
```
FileExistsError: Output file already exists
```

**Solutions:**

1. **Automatic overwrite:**
   ```bash
   audiobookmaker /path/to/files/ --gui  # Auto-overwrite
   ```

2. **Custom output location:**
   ```bash
   audiobookmaker /path/to/files/ --output /custom/path/book.m4b
   ```

3. **Remove existing file:**
   ```bash
   rm existing_audiobook.m4b
   ```

### 8. Chapter Detection Issues

**Problem:** Chapters not detected correctly

**Solutions:**

1. **Check filename format:**
   ```
   # Good formats
   01 - Chapter Title.mp3
   Chapter 1 - Title.mp3
   Track 01 Title.mp3
   
   # Problematic formats
   random_filename.mp3
   untitled.mp3
   ```

2. **Use different chapter mode:**
   ```bash
   # Use filenames as chapter titles
   audiobookmaker /path/to/files/ --chapter-titles filename
   
   # Use generic titles
   audiobookmaker /path/to/files/ --chapter-titles generic
   ```

3. **Rename files systematically:**
   ```bash
   # Rename files with proper numbering
   mv "Chapter One.mp3" "01 - Chapter One.mp3"
   mv "Chapter Two.mp3" "02 - Chapter Two.mp3"
   ```

### 9. Cover Art Issues

**Error Message:**
```
MetadataError: Unsupported cover art format
```

**Solutions:**

1. **Use supported formats:**
   ```bash
   # Convert to supported format
   convert cover.bmp cover.jpg
   
   # Supported formats: JPEG, PNG
   audiobookmaker /path/to/files/ --cover cover.jpg
   ```

2. **Check file size:**
   ```bash
   # Cover art should be under 10MB
   ls -lh cover.jpg
   ```

3. **Optimize image:**
   ```bash
   # Reduce image size
   convert cover.jpg -resize 1000x1000 -quality 85 cover_optimized.jpg
   ```

### 10. Performance Issues

**Problem:** Processing is very slow

**Solutions:**

1. **Increase CPU cores:**
   ```bash
   audiobookmaker /path/to/files/ --cores 8
   ```

2. **Use SSD storage:**
   - Process files on SSD rather than HDD
   - Use SSD for temporary directory

3. **Monitor system resources:**
   ```bash
   # Check CPU usage
   top
   htop
   
   # Check disk I/O
   iotop
   ```

4. **Optimize file organization:**
   ```bash
   # Keep files in same directory
   # Avoid network drives for processing
   ```

## Debug Information

### Enable Verbose Logging

```bash
# Maximum verbosity
audiobookmaker /path/to/files/ --validation-level paranoid

# Check log files
ls -la logfile_*.log
tail -f logfile_*.log
```

### Environment Information

```bash
# Check Python version
python --version

# Check available memory
free -h  # Linux
vm_stat  # macOS

# Check disk space
df -h

# Check FFmpeg version
ffmpeg -version
```

### Test with Sample Files

```bash
# Test with provided sample files
audiobookmaker testfiles/book1mp3/

# Test with single file
audiobookmaker testfiles/book1mp3/01*.mp3
```

## Getting Help

### Log Files

Always check the log files for detailed error information:
```bash
# Find recent log files
ls -lt logfile_*.log | head -5

# View latest log
tail -100 logfile_*.log
```

### System Information

When reporting issues, include:

1. **Operating System:** Windows/macOS/Linux version
2. **Python Version:** `python --version`
3. **FFmpeg Version:** `ffmpeg -version`
4. **Error Message:** Complete error message from log
5. **File Information:** Audio format, file sizes, directory structure
6. **Command Used:** Exact command that caused the issue

### Common Log Patterns

Look for these patterns in log files:

- `ERROR` - Critical errors
- `WARNING` - Non-fatal issues
- `Conversion failed` - Audio conversion problems
- `Permission denied` - File permission issues
- `Memory` - Memory-related problems
- `Dependency` - Missing dependencies

## Prevention

### Best Practices

1. **Regular Maintenance:**
   ```bash
   # Clean up old cache files
   audiobookmaker --clear-cache
   ```

2. **File Organization:**
   - Use consistent naming conventions
   - Keep files in local directories
   - Avoid special characters in filenames

3. **System Maintenance:**
   - Keep FFmpeg updated
   - Monitor disk space
   - Regular system updates

4. **Resource Management:**
   - Don't use all CPU cores
   - Monitor memory usage
   - Use appropriate quality settings

### Health Checks

```bash
# Test basic functionality
audiobookmaker testfiles/book1mp3/ --output test_output.m4b

# Validate audio files
audiobookmaker /path/to/files/ --validation-level strict --quiet

# Check dependencies
ffmpeg -version
python -c "import mutagen; print('Mutagen OK')"
```