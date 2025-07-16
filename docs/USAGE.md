# AudiobookMakerPy Usage Guide

## Basic Usage

### Simple Conversion

Convert all audio files in a directory to an audiobook:

```bash
audiobookmaker /path/to/audio/files/
```

### Individual Files

Convert specific audio files:

```bash
audiobookmaker file1.mp3 file2.mp3 file3.mp3
```

### Multiple Directories

Process multiple directories:

```bash
audiobookmaker /path/to/book1/ /path/to/book2/
```

## Advanced Options

### Custom Output

```bash
# Custom output file
audiobookmaker /path/to/files/ --output /custom/path/my_audiobook.m4b

# Custom output directory
audiobookmaker /path/to/files/ --output-dir /custom/directory/

# Custom filename with metadata template
audiobookmaker /path/to/files/ --template "{author} - {title} ({year})"
```

### Audio Quality

```bash
# Predefined quality presets
audiobookmaker /path/to/files/ --quality high    # 192k bitrate
audiobookmaker /path/to/files/ --quality medium  # 128k bitrate (default)
audiobookmaker /path/to/files/ --quality low     # 96k bitrate

# Custom bitrate
audiobookmaker /path/to/files/ --quality custom --bitrate 256k
```

### Metadata Management

```bash
# Override title and author
audiobookmaker /path/to/files/ --title "My Book" --author "John Doe"

# Add cover art
audiobookmaker /path/to/files/ --cover /path/to/cover.jpg

# Chapter title modes
audiobookmaker /path/to/files/ --chapter-titles auto      # Smart extraction (default)
audiobookmaker /path/to/files/ --chapter-titles filename  # Use filenames
audiobookmaker /path/to/files/ --chapter-titles generic   # Chapter 1, 2, 3...
```

### Performance Tuning

```bash
# Specify number of CPU cores
audiobookmaker /path/to/files/ --cores 4

# Validation levels
audiobookmaker /path/to/files/ --validation-level strict
audiobookmaker /path/to/files/ --validation-level normal  # default
audiobookmaker /path/to/files/ --validation-level lax
```

### Resume Functionality

```bash
# Resume interrupted processing (default)
audiobookmaker /path/to/files/ --resume auto

# Always start fresh
audiobookmaker /path/to/files/ --resume never

# Force resume (fail if no resumable work)
audiobookmaker /path/to/files/ --resume force

# Clear cache and start fresh
audiobookmaker /path/to/files/ --clear-cache
```

### Output Control

```bash
# Quiet mode (minimal output)
audiobookmaker /path/to/files/ --quiet

# JSON output for integration
audiobookmaker /path/to/files/ --json-output

# GUI mode (progress but no prompts)
audiobookmaker /path/to/files/ --gui
```

## File Organization

### Recommended Directory Structure

```
My Audiobook/
├── 01 - Introduction.mp3
├── 02 - Chapter 1.mp3
├── 03 - Chapter 2.mp3
├── 04 - Chapter 3.mp3
└── 05 - Conclusion.mp3
```

### Supported Audio Formats

- MP3 (.mp3)
- WAV (.wav)
- M4A (.m4a)
- FLAC (.flac)
- OGG (.ogg)
- AAC (.aac)
- M4B (.m4b)

### File Naming Best Practices

1. **Use leading numbers for proper ordering**: `01 - Chapter.mp3`
2. **Include chapter information**: `Chapter 1 - The Beginning.mp3`
3. **Avoid special characters**: Use only letters, numbers, spaces, and hyphens
4. **Be consistent**: Use the same naming pattern throughout

## Metadata Template Variables

Available variables for the `--template` option:

- `{title}` - Book title
- `{author}` - Author name
- `{album}` - Album name
- `{year}` - Publication year

Example templates:
```bash
--template "{title}"                    # "My Book"
--template "{author} - {title}"         # "John Doe - My Book"
--template "{title} ({year})"           # "My Book (2023)"
--template "{author}/{title}"           # "John Doe/My Book"
```

## Examples

### Basic Audiobook Creation

```bash
# Create audiobook from directory
audiobookmaker ~/Downloads/MyBook/

# Result: MyBook.m4b in ~/Downloads/
```

### High-Quality Audiobook with Cover

```bash
audiobookmaker ~/Books/GreatNovel/ \
  --quality high \
  --cover ~/Books/GreatNovel/cover.jpg \
  --title "The Great Novel" \
  --author "Famous Author"
```

### Batch Processing with Custom Organization

```bash
audiobookmaker ~/Books/Series1/ ~/Books/Series2/ \
  --output-dir ~/Audiobooks/ \
  --template "{author} - {title}" \
  --quality medium \
  --cores 8
```

### Resume Interrupted Processing

```bash
# Start processing
audiobookmaker ~/Books/LongBook/ --cores 8

# If interrupted, resume with:
audiobookmaker ~/Books/LongBook/ --cores 8
# (automatically detects and resumes)
```

## Troubleshooting

### Common Issues

1. **FFmpeg not found**: Install FFmpeg and ensure it's in your PATH
2. **Permission errors**: Check file permissions and available disk space
3. **Memory issues**: Reduce `--cores` or use `--quality low`
4. **Invalid files**: Use `--validation-level strict` to identify problems

### Debug Information

```bash
# Enable verbose logging
audiobookmaker /path/to/files/ --validation-level paranoid

# Check log files
ls logfile_*.log
```

For more troubleshooting help, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).