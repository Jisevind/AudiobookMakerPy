"""
Custom exception hierarchy for AudiobookMakerPy.

This module defines a comprehensive hierarchy of application-specific exceptions
that provide clear error classification and context for robust error handling.
"""


class AudiobookMakerError(Exception):
    """Base exception for all application-specific errors."""
    
    def __init__(self, message, error_code=None, suggestion=None):
        self.error_code = error_code
        self.suggestion = suggestion
        super().__init__(message)
    
    def get_user_message(self):
        """Get a user-friendly error message with suggestions."""
        message = str(self)
        if self.suggestion:
            message += f"\n\nSuggestion: {self.suggestion}"
        if self.error_code:
            message += f"\nError Code: {self.error_code}"
        return message


class DependencyError(AudiobookMakerError):
    """Raised when required external dependencies are not found or invalid."""
    
    def __init__(self, dependency_name, message=None, version_found=None, version_required=None):
        self.dependency_name = dependency_name
        self.version_found = version_found
        self.version_required = version_required
        
        if not message:
            message = f"Required dependency '{dependency_name}' is not available"
            if version_found and version_required:
                message += f" (found: {version_found}, required: {version_required})"
        
        suggestion = self._get_dependency_suggestion(dependency_name)
        super().__init__(message, error_code="DEP001", suggestion=suggestion)
    
    def _get_dependency_suggestion(self, dependency_name):
        """Provide specific installation suggestions for different dependencies."""
        suggestions = {
            "ffmpeg": "Install FFmpeg from https://ffmpeg.org/ and ensure it's in your system PATH",
            "pydub": "Install with: pip install pydub",
            "mutagen": "Install with: pip install mutagen",
        }
        return suggestions.get(dependency_name.lower(), f"Please install {dependency_name}")


class FileProcessingError(AudiobookMakerError):
    """Base class for errors that occur during file processing."""
    
    def __init__(self, message, filename, operation=None):
        self.filename = filename
        self.operation = operation
        
        full_message = message
        if filename:
            full_message += f" (file: {filename})"
        if operation:
            full_message += f" (operation: {operation})"
        
        super().__init__(full_message, error_code="FILE001")


class ConversionError(FileProcessingError):
    """Raised when audio file conversion fails."""
    
    def __init__(self, message, filename, source_format=None, target_format=None):
        self.source_format = source_format
        self.target_format = target_format
        
        format_info = ""
        if source_format and target_format:
            format_info = f" ({source_format} -> {target_format})"
        
        suggestion = "Check if the file is corrupted or try a different bitrate/format"
        super().__init__(f"Conversion failed: {message}{format_info}", filename, "conversion")
        self.suggestion = suggestion
        self.error_code = "CONV001"


class MetadataError(FileProcessingError):
    """Raised when metadata operations fail."""
    
    def __init__(self, message, filename, metadata_type=None):
        self.metadata_type = metadata_type
        
        suggestion = "Check file permissions and ensure the file is not corrupted"
        if metadata_type:
            message = f"{metadata_type} metadata error: {message}"
        
        super().__init__(f"Metadata operation failed: {message}", filename, "metadata")
        self.suggestion = suggestion
        self.error_code = "META001"


class ValidationError(AudiobookMakerError):
    """Raised when input validation fails."""
    
    def __init__(self, message, validation_type, value=None):
        self.validation_type = validation_type
        self.value = value
        
        full_message = f"Validation failed ({validation_type}): {message}"
        if value is not None:
            full_message += f" (value: {value})"
        
        suggestion = self._get_validation_suggestion(validation_type)
        super().__init__(full_message, error_code="VAL001", suggestion=suggestion)
    
    def _get_validation_suggestion(self, validation_type):
        """Provide specific suggestions for different validation failures."""
        suggestions = {
            "file_format": "Ensure the file has a supported audio format extension (.mp3, .wav, .m4a, .flac, .ogg, .aac, .m4b)",
            "file_access": "Check file permissions and ensure the file is not in use by another application",
            "file_corruption": "The file may be corrupted. Try re-downloading or using a different source",
            "path": "Ensure the path exists and you have appropriate permissions",
            "bitrate": "Use a valid bitrate value (e.g., 128k, 256k, 320k)",
            "cores": "Specify a positive integer for CPU cores (1-16 recommended)",
        }
        return suggestions.get(validation_type, "Please check the input and try again")


class ResourceError(AudiobookMakerError):
    """Raised when system resource constraints are encountered."""
    
    def __init__(self, message, resource_type, required=None, available=None):
        self.resource_type = resource_type
        self.required = required
        self.available = available
        
        full_message = f"Resource constraint ({resource_type}): {message}"
        if required and available:
            full_message += f" (required: {required}, available: {available})"
        
        suggestion = self._get_resource_suggestion(resource_type)
        super().__init__(full_message, error_code="RES001", suggestion=suggestion)
    
    def _get_resource_suggestion(self, resource_type):
        """Provide specific suggestions for different resource constraints."""
        suggestions = {
            "disk_space": "Free up disk space or specify a different output location",
            "memory": "Close other applications or reduce the number of parallel processes",
            "file_handles": "Too many files open simultaneously. Try processing in smaller batches",
            "cpu": "Reduce the number of CPU cores used for processing",
        }
        return suggestions.get(resource_type, f"Insufficient {resource_type} available")


class ConfigurationError(AudiobookMakerError):
    """Raised when configuration is invalid or missing."""
    
    def __init__(self, message, config_key=None, config_value=None):
        self.config_key = config_key
        self.config_value = config_value
        
        full_message = f"Configuration error: {message}"
        if config_key:
            full_message += f" (key: {config_key})"
        if config_value is not None:
            full_message += f" (value: {config_value})"
        
        suggestion = "Check your configuration settings and ensure all required values are provided"
        super().__init__(full_message, error_code="CFG001", suggestion=suggestion)


class ProcessingError(AudiobookMakerError):
    """Raised when general processing operations fail."""
    
    def __init__(self, message, operation, recoverable=True):
        self.operation = operation
        self.recoverable = recoverable
        
        full_message = f"Processing error ({operation}): {message}"
        suggestion = "Try again with different settings or check the logs for more details"
        if not recoverable:
            suggestion = "This error cannot be automatically recovered. Manual intervention required"
        
        super().__init__(full_message, error_code="PROC001", suggestion=suggestion)


class ConcatenationError(FileProcessingError):
    """Raised when audio concatenation fails."""
    
    def __init__(self, message, files_processed=0, total_files=0):
        self.files_processed = files_processed
        self.total_files = total_files
        
        full_message = f"Concatenation failed: {message}"
        if total_files > 0:
            full_message += f" ({files_processed}/{total_files} files processed)"
        
        suggestion = "Check that all temporary files were created successfully and try again"
        super().__init__(full_message, None, "concatenation")
        self.suggestion = suggestion
        self.error_code = "CONCAT001"


class InterruptedError(AudiobookMakerError):
    """Raised when processing is interrupted by user or system."""
    
    def __init__(self, message, stage=None, recoverable=True):
        self.stage = stage
        self.recoverable = recoverable
        
        full_message = f"Processing interrupted: {message}"
        if stage:
            full_message += f" (stage: {stage})"
        
        suggestion = "You can resume processing from where it was interrupted" if recoverable else "Processing must be restarted"
        super().__init__(full_message, error_code="INT001", suggestion=suggestion)


# Error classification helpers
def classify_error(exception):
    """Classify errors for appropriate handling strategies."""
    if isinstance(exception, (DependencyError, ConfigurationError)):
        return "fatal"  # Cannot continue without fixing
    elif isinstance(exception, FileProcessingError):
        return "recoverable"  # Can skip and continue
    elif isinstance(exception, ResourceError):
        return "retry"  # May succeed with different settings
    elif isinstance(exception, ValidationError):
        return "user_error"  # User needs to fix input
    else:
        return "unknown"


def get_error_summary(errors):
    """Generate a summary of multiple errors for reporting."""
    if not errors:
        return "No errors occurred."
    
    summary = f"Processing completed with {len(errors)} error(s):\n\n"
    
    # Group errors by type
    error_groups = {}
    for error in errors:
        error_type = type(error).__name__
        if error_type not in error_groups:
            error_groups[error_type] = []
        error_groups[error_type].append(error)
    
    # Generate summary for each group
    for error_type, error_list in error_groups.items():
        summary += f"{error_type} ({len(error_list)} occurrence(s)):\n"
        for i, error in enumerate(error_list[:3], 1):  # Show first 3 errors
            summary += f"  {i}. {str(error)}\n"
        if len(error_list) > 3:
            summary += f"  ... and {len(error_list) - 3} more\n"
        summary += "\n"
    
    return summary.strip()