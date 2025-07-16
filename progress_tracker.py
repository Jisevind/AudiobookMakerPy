"""
Progress tracking module for AudiobookMakerPy.
"""

import time
import sys
from typing import Optional, List, Callable, Any, Dict
from contextlib import contextmanager
import logging

# Try to import tqdm, gracefully handle if not available
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


class ProgressTracker:
    """
    Comprehensive progress tracking system for audiobook processing.
    
    Implements Gemini's approach: focus on high-level progress (per-file)
    rather than low-level FFmpeg parsing for reliability and simplicity.
    """
    
    def __init__(self, use_progress_bars: bool = True, quiet: bool = False):
        """
        Initialize progress tracker.
        
        Args:
            use_progress_bars: Whether to use visual progress bars (requires tqdm)
            quiet: Suppress most output except errors
        """
        self.use_progress_bars = use_progress_bars and TQDM_AVAILABLE and not quiet
        self.quiet = quiet
        self.logger = logging.getLogger(__name__)
        
        if use_progress_bars and not TQDM_AVAILABLE:
            self.logger.warning("tqdm not available - falling back to basic progress indicators")
            self.use_progress_bars = False
    
    @contextmanager
    def validation_progress(self, total_files: int):
        """
        Context manager for validation progress tracking.
        
        Args:
            total_files: Total number of files to validate
        """
        if self.use_progress_bars:
            with tqdm(
                total=total_files,
                desc="Validating files",
                unit="file",
                colour="blue",
                leave=False
            ) as pbar:
                yield ProgressUpdate(pbar, self.quiet)
        else:
            if not self.quiet:
                print(f"Validating {total_files} files...")
            yield ProgressUpdate(None, self.quiet, total_files)
    
    @contextmanager
    def conversion_progress(self, total_files: int):
        """
        Context manager for file conversion progress tracking.
        
        This is the main progress bar users will see during processing.
        
        Args:
            total_files: Total number of files to convert
        """
        if self.use_progress_bars:
            with tqdm(
                total=total_files,
                desc="Converting chapters",
                unit="file",
                colour="green"
            ) as pbar:
                yield ProgressUpdate(pbar, self.quiet)
        else:
            if not self.quiet:
                print(f"Converting {total_files} files...")
            yield ProgressUpdate(None, self.quiet, total_files)
    
    @contextmanager
    def operation_progress(self, description: str, show_spinner: bool = False):
        """
        Context manager for simple operation progress (concatenation, metadata).
        
        Args:
            description: Description of the operation
            show_spinner: Whether to show a spinner for indeterminate progress
        """
        if self.use_progress_bars and show_spinner:
            # Indeterminate progress bar for operations without clear steps
            try:
                with tqdm(
                    desc=description,
                    unit="",
                    leave=False,
                    total=None,  # Explicitly set total to None for indeterminate progress
                    bar_format="{desc}: {elapsed}"
                ) as pbar:
                    yield SimpleProgress(pbar, self.quiet)
            except Exception as e:
                # Fallback if tqdm has issues with indeterminate progress
                if not self.quiet:
                    print(f"{description}...")
                yield SimpleProgress(None, self.quiet)
        else:
            if not self.quiet:
                print(f"{description}...")
            yield SimpleProgress(None, self.quiet)
    
    def print_step(self, message: str, step: Optional[int] = None, total_steps: Optional[int] = None):
        """
        Print a processing step message.
        
        Args:
            message: The message to print
            step: Current step number (optional)
            total_steps: Total number of steps (optional)
        """
        if self.quiet:
            return
        
        if step is not None and total_steps is not None:
            print(f"[{step}/{total_steps}] {message}")
        else:
            print(f"• {message}")
    
    def print_summary(self, 
                     total_files: int, 
                     successful_files: int, 
                     failed_files: int, 
                     duration_seconds: float):
        """
        Print a processing summary.
        
        Args:
            total_files: Total files processed
            successful_files: Number of successful conversions
            failed_files: Number of failed conversions
            duration_seconds: Total processing time
        """
        if self.quiet and failed_files == 0:
            return
        
        print("\n" + "=" * 50)
        print("PROCESSING SUMMARY")
        print("=" * 50)
        print(f"Total files: {total_files}")
        print(f"Successful: {successful_files}")
        if failed_files > 0:
            print(f"Failed: {failed_files}")
        print(f"Processing time: {self._format_duration(duration_seconds)}")
        
        if failed_files == 0:
            print("* All files processed successfully!")
        else:
            print(f"! {failed_files} files failed to process")
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in a human-readable way."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.1f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}h {minutes}m {secs:.1f}s"


class ProgressUpdate:
    """
    Helper class for updating progress during operations.
    
    Abstracts whether we're using tqdm progress bars or simple text output.
    """
    
    def __init__(self, pbar: Optional[Any], quiet: bool, total: Optional[int] = None):
        self.pbar = pbar
        self.quiet = quiet
        self.total = total
        self.current = 0
    
    def update(self, increment: int = 1, description: Optional[str] = None):
        """
        Update progress by incrementing the counter.
        
        Args:
            increment: Amount to increment (default: 1)
            description: Optional description for this update
        """
        self.current += increment
        
        if self.pbar:
            if description:
                self.pbar.set_postfix_str(description)
            self.pbar.update(increment)
        elif not self.quiet and self.total:
            # Fallback: print progress every 10% or every 5 files, whichever is more frequent
            print_interval = max(1, min(self.total // 10, 5))
            if self.current % print_interval == 0 or self.current == self.total:
                percentage = (self.current / self.total) * 100
                print(f"Progress: {self.current}/{self.total} ({percentage:.1f}%)")
    
    def set_description(self, description: str):
        """Update the progress description."""
        if self.pbar:
            self.pbar.set_description(description)
        elif not self.quiet:
            print(f"Status: {description}")
    
    def set_postfix(self, **kwargs):
        """Set postfix information (e.g., current file name)."""
        if self.pbar:
            self.pbar.set_postfix(**kwargs)


class SimpleProgress:
    """
    Simple progress indicator for operations without clear steps.
    """
    
    def __init__(self, pbar: Optional[Any], quiet: bool):
        self.pbar = pbar
        self.quiet = quiet
        self.start_time = time.time()
    
    def update_status(self, status: str):
        """Update the status message."""
        if self.pbar is not None:
            elapsed = time.time() - self.start_time
            try:
                self.pbar.set_description(f"{status} (elapsed: {elapsed:.1f}s)")
            except TypeError:
                # Fallback if tqdm has issues with the progress bar
                if not self.quiet:
                    print(f"  {status}")
        elif not self.quiet:
            print(f"  {status}")
    
    def complete(self, final_message: Optional[str] = None):
        """Mark the operation as complete."""
        if self.pbar is not None:
            try:
                if final_message:
                    self.pbar.set_description(final_message)
                self.pbar.close()
            except TypeError:
                # Fallback if tqdm has issues with the progress bar
                if not self.quiet and final_message:
                    print(f"  * {final_message}")
        elif not self.quiet and final_message:
            print(f"  * {final_message}")


class ProcessingTimer:
    """Simple timer for measuring processing duration."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
    
    def start(self):
        """Start the timer."""
        self.start_time = time.time()
    
    def stop(self):
        """Stop the timer and return duration."""
        self.end_time = time.time()
        return self.get_duration()
    
    def get_duration(self) -> float:
        """Get the current duration in seconds."""
        if self.start_time is None:
            return 0.0
        end_time = self.end_time or time.time()
        return end_time - self.start_time


# Convenience functions for common progress scenarios
def create_progress_tracker(quiet: bool = False, disable_bars: bool = False) -> ProgressTracker:
    """
    Create a progress tracker with appropriate settings.
    
    Args:
        quiet: Suppress most output
        disable_bars: Disable progress bars even if tqdm is available
    
    Returns:
        Configured ProgressTracker instance
    """
    return ProgressTracker(use_progress_bars=not disable_bars, quiet=quiet)


def format_file_status(filename: str, status: str, max_width: int = 50) -> str:
    """
    Format a filename for display in progress indicators.
    
    Args:
        filename: The filename to format
        status: Status string (e.g., "OK", "FAIL", "SKIP")
        max_width: Maximum width for the filename display
    
    Returns:
        Formatted string for display
    """
    import os
    basename = os.path.basename(filename)
    
    if len(basename) <= max_width:
        return f"[{status}] {basename}"
    else:
        # Truncate filename if too long
        truncated = basename[:max_width-3] + "..."
        return f"[{status}] {truncated}"


def is_tqdm_available() -> bool:
    """Check if tqdm is available for progress bars."""
    return TQDM_AVAILABLE


# Example usage and testing
if __name__ == "__main__":
    import time
    from concurrent.futures import ProcessPoolExecutor
    
    def simulate_file_processing(file_index: int) -> str:
        """Simulate processing a file."""
        time.sleep(0.5)  # Simulate work
        if file_index == 7:  # Simulate a failure
            raise Exception(f"Failed to process file {file_index}")
        return f"file_{file_index}.mp3"
    
    # Test the progress tracking system
    files = list(range(10))
    tracker = create_progress_tracker()
    timer = ProcessingTimer()
    timer.start()
    
    # Step 1: Validation
    with tracker.validation_progress(len(files)) as progress:
        for i, file_idx in enumerate(files):
            time.sleep(0.1)  # Simulate validation work
            progress.update(1, f"file_{file_idx}.mp3")
    
    # Step 2: Conversion
    successful = 0
    failed = 0
    
    with tracker.conversion_progress(len(files)) as progress:
        with ProcessPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(simulate_file_processing, f) for f in files]
            
            for i, future in enumerate(futures):
                try:
                    result = future.result()
                    successful += 1
                    progress.update(1, f"+ {result}")
                except Exception as e:
                    failed += 1
                    progress.update(1, f"- file_{i}.mp3")
    
    # Step 3: Final operations
    with tracker.operation_progress("Concatenating files", show_spinner=True) as progress:
        time.sleep(1)  # Simulate concatenation
        progress.update_status("Writing metadata")
        time.sleep(0.5)  # Simulate metadata writing
        progress.complete("Concatenation complete")
    
    # Summary
    duration = timer.stop()
    tracker.print_summary(len(files), successful, failed, duration)