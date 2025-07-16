"""
Command-line interface for AudiobookMakerPy.
"""

import argparse
import sys
import os
import logging
from datetime import datetime

from .core.processor import AudiobookProcessor
from .utils.validation import ValidationLevel
from .utils.progress_tracker import create_progress_tracker, ProcessingTimer
from .exceptions import AudiobookMakerError, DependencyError


def setup_logging(quiet=False):
    """
    Sets up the logging configuration for the application.
    
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


def get_safe_cpu_default():
    """Returns a safe default for CPU cores."""
    return min(4, os.cpu_count() or 2)


def parse_arguments():
    """
    Parses and validates command line arguments for the application.
    
    Returns:
        argparse.Namespace: Parsed command line arguments.
    """
    max_cpu_cores = os.cpu_count() or 4
    
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
        default=max_cpu_cores,
        help=f'Number of CPU cores to use for parallel processing. '
             f'Default: {max_cpu_cores} '
             f'(configurable via ~/.audiobookmaker_config.json, '
             f'safe default: {get_safe_cpu_default()} cores)'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Reduce output verbosity'
    )
    
    parser.add_argument(
        '--gui',
        action='store_true',
        help='GUI mode: show progress but auto-overwrite files without prompts'
    )
    
    parser.add_argument(
        '--json-output',
        action='store_true', 
        help='Output structured JSON for progress and logging (for sidecar integration)'
    )
    
    parser.add_argument(
        '--validation-level', '--val',
        choices=['lax', 'normal', 'strict', 'paranoid'],
        default='normal',
        help='Validation strictness level (default: normal)'
    )
    
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
    
    parser.add_argument(
        '--resume',
        choices=['auto', 'never', 'force'],
        default='auto',
        help='Resume behavior: auto (resume if possible), never (always start fresh), force (fail if cannot resume)'
    )
    
    parser.add_argument(
        '--clear-cache', '--clear',
        action='store_true',
        help='Clear cached conversion results before processing (equivalent to --resume never)'
    )
    
    parser.add_argument(
        '--version', '-v',
        action='version',
        version='AudiobookMakerPy 2.0.0'
    )
    
    args = parser.parse_args()
    
    # Process arguments
    if args.clear_cache:
        args.resume = 'never'
        logging.info("Cache clearing requested: setting resume mode to 'never'")
    
    quality_presets = {
        'low': '96k',
        'medium': '128k', 
        'high': '192k'
    }
    
    # Apply quality preset to bitrate if not using custom
    if args.quality != 'custom':
        args.bitrate = quality_presets[args.quality]
    
    # Validate cover art if provided
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


def emit_progress(current, total, stage, speed=None, eta=None, json_mode=False):
    """Emit progress information."""
    if json_mode:
        import json
        progress_data = {
            "type": "progress",
            "current": current,
            "total": total,
            "stage": stage,
            "speed": speed,
            "eta": eta
        }
        print(json.dumps(progress_data))
    else:
        print(f"{stage}...")


def emit_log(level, message, json_mode=False):
    """Emit log information."""
    if json_mode:
        import json
        log_data = {
            "type": "log",
            "level": level,
            "message": message
        }
        print(json.dumps(log_data))
    else:
        print(message)


def main():
    """Main entry point for the CLI application."""
    try:
        # Parse command line arguments
        args = parse_arguments()
        
        # Setup logging
        setup_logging(quiet=args.quiet)
        
        # JSON mode for sidecar integration
        json_mode = args.json_output
        
        if not json_mode:
            print("=" * 50)
        else:
            emit_log("info", "AudiobookMakerPy 2.0.0", json_mode)
        
        # Initialize progress tracking and timer
        progress_quiet = args.quiet and not args.gui
        progress_tracker = create_progress_tracker(quiet=progress_quiet)
        processing_timer = ProcessingTimer()
        processing_timer.start()
        
        # Create processor instance
        processor = AudiobookProcessor(
            bitrate=args.bitrate,
            cores=args.cores,
            validation_level=ValidationLevel(args.validation_level),
            resume_mode=args.resume,
            progress_tracker=progress_tracker,
            quiet=args.quiet,
            gui_mode=args.gui,
            json_mode=json_mode
        )
        
        # Process the audiobook
        result = processor.process_audiobook(
            input_paths=args.input_paths,
            output_path=args.output,
            output_dir=args.output_dir,
            output_name=args.output_name,
            template=args.template,
            title=args.title,
            author=args.author,
            cover_art_path=args.cover,
            chapter_titles_mode=args.chapter_titles
        )
        
        # Display results
        processing_duration = processing_timer.stop()
        
        if result.success:
            if not args.quiet:
                print(f"\nAudiobook created successfully!")
                print(f"   - Output: {result.output_file}")
                print(f"   - Duration: {result.total_hours}h {result.total_minutes}m")
                print(f"   - Processing time: {processing_duration:.1f}s")
            
            if result.errors:
                print(f"\nWarnings encountered:")
                for error in result.errors:
                    print(f"   - {error}")
            
            sys.exit(0)
        else:
            print(f"\nProcessing failed: {result.error_message}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(0)
    except DependencyError as e:
        print(f"\nDependency Error: {e.get_user_message()}")
        sys.exit(1)
    except AudiobookMakerError as e:
        print(f"\nError: {e.get_user_message()}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        logging.error(f'Unexpected error: {str(e)}')
        sys.exit(1)


if __name__ == '__main__':
    main()