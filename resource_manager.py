"""
Resource management module for AudiobookMakerPy.
"""

import os
import sys
import signal
import shutil
import tempfile
import logging
import threading
import time
import subprocess
from contextlib import contextmanager
from typing import Optional, Dict, Any, List, Union, Callable
from pathlib import Path

from exceptions import ResourceError, ProcessingError, AudiobookMakerError

# Try to import psutil for advanced monitoring, fallback to basic monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class ResourceMonitor:
    """Monitor and track system resource usage during processing."""
    
    def __init__(self, memory_limit_mb: Optional[int] = None, disk_space_margin_mb: int = 500):
        """
        Initialize resource monitor with configurable limits.
        
        Args:
            memory_limit_mb: Maximum memory usage in MB (None for auto-detection)
            disk_space_margin_mb: Safety margin for disk space checks in MB
        """
        self.disk_space_margin_mb = disk_space_margin_mb
        self.logger = logging.getLogger(__name__)
        self._monitoring = False
        self._monitor_thread = None
        self._peak_memory_mb = 0
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None
        self.memory_limit_mb = memory_limit_mb or self._get_safe_memory_limit()
        
        if not PSUTIL_AVAILABLE:
            self.logger.warning("psutil not available - using basic resource monitoring")
        
    def _get_safe_memory_limit(self) -> int:
        """Calculate a safe memory limit based on available system memory."""
        if PSUTIL_AVAILABLE:
            try:
                # Use 80% of available memory as a safe limit
                total_memory = psutil.virtual_memory().total
                safe_limit = int((total_memory * 0.8) / (1024 * 1024))  # Convert to MB
                self.logger.info(f"Auto-detected safe memory limit: {safe_limit}MB")
                return safe_limit
            except Exception as e:
                self.logger.warning(f"Could not detect system memory with psutil: {e}")
        
        # Fallback to conservative limit when psutil unavailable
        self.logger.info("Using conservative 2GB memory limit (psutil unavailable)")
        return 2048
    
    def get_current_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics."""
        if PSUTIL_AVAILABLE and self._process:
            try:
                memory_info = self._process.memory_info()
                memory_percent = self._process.memory_percent()
                
                rss_mb = memory_info.rss / (1024 * 1024)  # Resident set size in MB
                vms_mb = memory_info.vms / (1024 * 1024)  # Virtual memory size in MB
                
                # Update peak memory tracking
                self._peak_memory_mb = max(self._peak_memory_mb, rss_mb)
                
                return {
                    'rss_mb': rss_mb,
                    'vms_mb': vms_mb,
                    'percent': memory_percent,
                    'peak_mb': self._peak_memory_mb
                }
            except Exception as e:
                self.logger.warning(f"Could not get memory usage with psutil: {e}")
        
        # Fallback: basic monitoring without detailed memory stats
        # In production, you might want to implement platform-specific fallbacks
        return {
            'rss_mb': 0,  # Unknown without psutil
            'vms_mb': 0,  # Unknown without psutil
            'percent': 0,  # Unknown without psutil
            'peak_mb': self._peak_memory_mb,
            'monitoring_method': 'basic'
        }
    
    def check_memory_limit(self) -> None:
        """Check if memory usage exceeds configured limits."""
        memory_stats = self.get_current_memory_usage()
        rss_mb = memory_stats['rss_mb']
        
        # Skip memory checking if we don't have accurate data
        if not PSUTIL_AVAILABLE or rss_mb == 0:
            return
        
        if rss_mb > self.memory_limit_mb:
            raise ResourceError(
                f"Memory usage exceeded limit: {rss_mb:.1f}MB > {self.memory_limit_mb}MB",
                "memory",
                required=f"{rss_mb:.1f}MB",
                available=f"{self.memory_limit_mb}MB"
            )
        
        # Log warning at 90% of limit
        warning_threshold = self.memory_limit_mb * 0.9
        if rss_mb > warning_threshold:
            self.logger.warning(
                f"Memory usage approaching limit: {rss_mb:.1f}MB "
                f"(limit: {self.memory_limit_mb}MB)"
            )
    
    def get_disk_space(self, path: Union[str, Path]) -> Dict[str, int]:
        """Get disk space information for a given path."""
        try:
            path = Path(path)
            if not path.exists():
                path = path.parent
            
            stat = shutil.disk_usage(path)
            return {
                'total_mb': stat.total // (1024 * 1024),
                'used_mb': (stat.total - stat.free) // (1024 * 1024),
                'free_mb': stat.free // (1024 * 1024),
                'available_mb': stat.free // (1024 * 1024)
            }
        except Exception as e:
            self.logger.warning(f"Could not get disk space for {path}: {e}")
            return {'total_mb': 0, 'used_mb': 0, 'free_mb': 0, 'available_mb': 0}
    
    def check_disk_space(self, path: Union[str, Path], required_mb: int) -> None:
        """Check if sufficient disk space is available."""
        disk_stats = self.get_disk_space(path)
        available_mb = disk_stats['available_mb']
        
        total_required_mb = required_mb + self.disk_space_margin_mb
        
        if available_mb < total_required_mb:
            raise ResourceError(
                f"Insufficient disk space: {available_mb}MB available, "
                f"{total_required_mb}MB required (including {self.disk_space_margin_mb}MB margin)",
                "disk_space",
                required=f"{total_required_mb}MB",
                available=f"{available_mb}MB"
            )
        
        self.logger.info(
            f"Disk space check passed: {available_mb}MB available, "
            f"{total_required_mb}MB required"
        )
    
    def estimate_processing_requirements(self, input_files: List[str]) -> Dict[str, int]:
        """Estimate resource requirements for processing given files."""
        total_size_mb = 0
        estimated_memory_mb = 0
        
        for file_path in input_files:
            try:
                file_size_bytes = os.path.getsize(file_path)
                file_size_mb = file_size_bytes // (1024 * 1024)
                total_size_mb += file_size_mb
                
                # Estimate memory usage: conversion creates temporary files roughly same size
                # Plus some overhead for Python objects and buffers
                estimated_memory_mb += file_size_mb * 0.1  # 10% of file size for processing overhead
                
            except Exception as e:
                self.logger.warning(f"Could not estimate requirements for {file_path}: {e}")
        
        # Add base overhead for the application
        estimated_memory_mb += 100  # Base overhead
        
        # Temporary files will be roughly same size as input files (for converted formats)
        estimated_temp_space_mb = total_size_mb * 2  # Conservative estimate
        
        return {
            'input_size_mb': total_size_mb,
            'estimated_memory_mb': int(estimated_memory_mb),
            'estimated_temp_space_mb': estimated_temp_space_mb
        }
    
    def start_monitoring(self, check_interval: float = 5.0) -> None:
        """Start background resource monitoring."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(check_interval,),
            daemon=True
        )
        self._monitor_thread.start()
        self.logger.info("Started resource monitoring")
    
    def stop_monitoring(self) -> None:
        """Stop background resource monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)
        self.logger.info("Stopped resource monitoring")
    
    def _monitor_loop(self, check_interval: float) -> None:
        """Background monitoring loop."""
        while self._monitoring:
            try:
                self.check_memory_limit()
                time.sleep(check_interval)
            except ResourceError as e:
                self.logger.error(f"Resource limit exceeded: {e}")
                # In a real implementation, you might want to trigger cleanup or abort processing
                break
            except Exception as e:
                self.logger.warning(f"Error in resource monitoring: {e}")
                time.sleep(check_interval)
    
    def get_resource_summary(self) -> Dict[str, Any]:
        """Get a comprehensive resource usage summary."""
        memory_stats = self.get_current_memory_usage()
        
        return {
            'memory': memory_stats,
            'memory_limit_mb': self.memory_limit_mb,
            'monitoring_active': self._monitoring,
            'process_id': self._process.pid if self._process else None
        }


@contextmanager
def managed_temp_directory(prefix: str = "audiobookmaker_", cleanup_on_exit: bool = True):
    """
    Context manager for temporary directory with guaranteed cleanup.
    
    Implements Gemini's recommendation for guaranteed cleanup using try...finally.
    """
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        logging.info(f"Created temporary directory: {temp_dir}")
        yield temp_dir
    finally:
        if temp_dir and cleanup_on_exit and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logging.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logging.error(f"Failed to cleanup temporary directory {temp_dir}: {e}")


@contextmanager 
def managed_processing(
    input_files: List[str],
    temp_dir: Optional[str] = None,
    memory_limit_mb: Optional[int] = None,
    monitor_resources: bool = True
):
    """
    Context manager for the entire processing workflow with resource management.
    
    Combines resource monitoring, temp directory management, and cleanup.
    """
    resource_monitor = ResourceMonitor(memory_limit_mb=memory_limit_mb)
    temp_dir_created = False
    
    try:
        # Estimate resource requirements
        requirements = resource_monitor.estimate_processing_requirements(input_files)
        logging.info(f"Estimated requirements: {requirements}")
        
        # Create temp directory if not provided
        if temp_dir is None:
            temp_dir = tempfile.mkdtemp(prefix="audiobookmaker_")
            temp_dir_created = True
            logging.info(f"Created temporary directory: {temp_dir}")
        
        # Check disk space
        resource_monitor.check_disk_space(
            temp_dir, 
            requirements['estimated_temp_space_mb']
        )
        
        # Start resource monitoring
        if monitor_resources:
            resource_monitor.start_monitoring()
        
        yield {
            'temp_dir': temp_dir,
            'resource_monitor': resource_monitor,
            'requirements': requirements
        }
        
    finally:
        # Stop monitoring
        if monitor_resources:
            resource_monitor.stop_monitoring()
        
        # Cleanup temp directory if we created it
        if temp_dir_created and temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logging.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logging.error(f"Failed to cleanup temporary directory {temp_dir}: {e}")
        
        # Log final resource summary
        summary = resource_monitor.get_resource_summary()
        logging.info(f"Final resource usage: Memory peak {summary['memory']['peak_mb']:.1f}MB")


class SignalHandler:
    """Handle system signals for graceful shutdown."""
    
    def __init__(self):
        self.shutdown_requested = False
        self.cleanup_callbacks: List[Callable] = []
        self.logger = logging.getLogger(__name__)
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Windows-specific signals
        if sys.platform == "win32":
            signal.signal(signal.SIGBREAK, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        signal_names = {
            signal.SIGINT: "SIGINT (Ctrl+C)",
            signal.SIGTERM: "SIGTERM",
        }
        if sys.platform == "win32":
            signal_names[signal.SIGBREAK] = "SIGBREAK (Ctrl+Break)"
        
        signal_name = signal_names.get(signum, f"Signal {signum}")
        self.logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        
        self.shutdown_requested = True
        self._run_cleanup_callbacks()
    
    def add_cleanup_callback(self, callback: Callable) -> None:
        """Add a callback to run during shutdown."""
        self.cleanup_callbacks.append(callback)
    
    def _run_cleanup_callbacks(self) -> None:
        """Execute all registered cleanup callbacks."""
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"Error in cleanup callback: {e}")
    
    def check_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self.shutdown_requested


# Process timeout handling
class ProcessTimeoutManager:
    """Manage timeouts for external processes."""
    
    def __init__(self, default_timeout: int = 300):  # 5 minutes default
        self.default_timeout = default_timeout
        self.logger = logging.getLogger(__name__)
    
    @contextmanager
    def timeout_context(self, timeout: Optional[int] = None):
        """Context manager for process timeout handling."""
        actual_timeout = timeout or self.default_timeout
        
        try:
            yield actual_timeout
        except subprocess.TimeoutExpired as e:
            self.logger.error(f"Process timed out after {actual_timeout}s: {e}")
            raise ProcessingError(
                f"Process timed out after {actual_timeout} seconds",
                "process_timeout",
                recoverable=True
            ) from e
        except Exception as e:
            if "timeout" in str(e).lower():
                self.logger.error(f"Process timeout detected: {e}")
                raise ProcessingError(
                    f"Process operation timed out: {str(e)}",
                    "process_timeout",
                    recoverable=True
                ) from e
            raise


# Global instances for easy access
_signal_handler = SignalHandler()
_timeout_manager = ProcessTimeoutManager()

def get_signal_handler() -> SignalHandler:
    """Get the global signal handler instance."""
    return _signal_handler

def get_timeout_manager() -> ProcessTimeoutManager:
    """Get the global timeout manager instance."""
    return _timeout_manager