"""
Comprehensive input validation framework for AudiobookMakerPy.

This module implements a layered validation approach combining file system checks,
format validation, and content validation using pydub for efficient and reliable
audio file verification.
"""

import os
import mimetypes
from typing import List, Tuple, Dict, Optional, Union
from dataclasses import dataclass
from enum import Enum
import logging

# Import our custom exceptions
from ..exceptions import (
    ValidationError, FileProcessingError, ResourceError, 
    AudiobookMakerError, ConversionError
)

# Audio processing imports with fallback
try:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pydub import AudioSegment
        from pydub.exceptions import CouldntDecodeError
    PYDUB_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    PYDUB_AVAILABLE = False


class ValidationLevel(Enum):
    """Validation strictness levels."""
    LAX = "lax"           # Basic file existence and permission checks only
    NORMAL = "normal"     # File system + format + basic content validation  
    STRICT = "strict"     # Full validation including constraint checking
    PARANOID = "paranoid" # All validations + file signature verification


@dataclass
class ValidationResult:
    """Result of file validation with detailed information."""
    file_path: str
    is_valid: bool
    validation_level: ValidationLevel
    errors: List[AudiobookMakerError]
    warnings: List[str]
    file_info: Optional[Dict] = None
    
    @property
    def has_errors(self) -> bool:
        """Check if validation found any errors."""
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        """Check if validation found any warnings."""
        return len(self.warnings) > 0


@dataclass
class AudioFileInfo:
    """Detailed information about an audio file."""
    duration_ms: int
    sample_rate: int
    channels: int
    file_size: int
    format: str
    bitrate: Optional[int] = None
    codec: Optional[str] = None


class AudioFileValidator:
    """Comprehensive audio file validation with configurable strictness levels."""
    
    # Supported audio file extensions
    SUPPORTED_EXTENSIONS = {
        '.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.m4b',
        '.wma', '.opus', '.webm'  # Additional formats pydub might support
    }
    
    # Audio file MIME types
    AUDIO_MIME_TYPES = {
        'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 
        'audio/m4a', 'audio/flac', 'audio/ogg', 'audio/aac',
        'audio/x-ms-wma', 'audio/opus', 'audio/webm'
    }
    
    # File signatures for audio formats (magic numbers)
    FILE_SIGNATURES = {
        b'ID3': 'mp3',           # MP3 with ID3 tag
        b'\xff\xfb': 'mp3',      # MP3 frame header
        b'\xff\xf3': 'mp3',      # MP3 frame header
        b'\xff\xf2': 'mp3',      # MP3 frame header
        b'RIFF': 'wav',          # WAV file
        b'fLaC': 'flac',         # FLAC file
        b'OggS': 'ogg',          # OGG container
        b'\x00\x00\x00\x20ftypM4A': 'm4a',  # M4A file
        b'\x00\x00\x00\x20ftypM4B': 'm4b',  # M4B file
    }
    
    def __init__(self, validation_level: ValidationLevel = ValidationLevel.NORMAL):
        """Initialize validator with specified validation level."""
        self.validation_level = validation_level
        self.logger = logging.getLogger(__name__)
    
    def validate_file(self, file_path: str) -> ValidationResult:
        """Validate a single audio file using the configured validation level."""
        errors = []
        warnings = []
        file_info = None
        
        try:
            # Layer 1: File System Validation
            self._validate_file_system(file_path, errors, warnings)
            
            # If file system validation failed, stop here
            if errors and self.validation_level != ValidationLevel.LAX:
                return ValidationResult(
                    file_path=file_path,
                    is_valid=False,
                    validation_level=self.validation_level,
                    errors=errors,
                    warnings=warnings
                )
            
            # Layer 2: Format Validation (if not LAX mode)
            if self.validation_level != ValidationLevel.LAX:
                self._validate_format(file_path, errors, warnings)
            
            # Layer 3: Content Validation using pydub (if NORMAL or higher)
            if (self.validation_level in [ValidationLevel.NORMAL, ValidationLevel.STRICT, ValidationLevel.PARANOID] 
                and PYDUB_AVAILABLE):
                file_info = self._validate_content_with_pydub(file_path, errors, warnings)
            
            # Layer 4: Constraint Validation (if STRICT or higher)
            if self.validation_level in [ValidationLevel.STRICT, ValidationLevel.PARANOID]:
                self._validate_constraints(file_path, file_info, errors, warnings)
            
            # Layer 5: File Signature Validation (if PARANOID)
            if self.validation_level == ValidationLevel.PARANOID:
                self._validate_file_signature(file_path, errors, warnings)
            
            is_valid = len(errors) == 0
            
            return ValidationResult(
                file_path=file_path,
                is_valid=is_valid,
                validation_level=self.validation_level,
                errors=errors,
                warnings=warnings,
                file_info=file_info
            )
            
        except Exception as e:
            # Wrap unexpected validation errors
            unexpected_error = ValidationError(
                f"Unexpected validation error: {str(e)}", 
                "validation_framework"
            )
            errors.append(unexpected_error)
            
            return ValidationResult(
                file_path=file_path,
                is_valid=False,
                validation_level=self.validation_level,
                errors=errors,
                warnings=warnings
            )
    
    def validate_batch(self, file_paths: List[str], progress_callback=None) -> Tuple[List[ValidationResult], List[str]]:
        """
        Validate multiple files in batch for fail-fast feedback.
        
        Args:
            file_paths: List of file paths to validate
            progress_callback: Optional callback for progress updates (called with each file)
        
        Returns:
            Tuple of (all_results, valid_file_paths)
        """
        self.logger.info(f"Starting batch validation of {len(file_paths)} files (level: {self.validation_level.value})")
        
        results = []
        valid_files = []
        
        for i, file_path in enumerate(file_paths):
            result = self.validate_file(file_path)
            results.append(result)
            
            if result.is_valid:
                valid_files.append(file_path)
            else:
                self.logger.warning(f"Validation failed for {file_path}: {len(result.errors)} errors")
            
            # Call progress callback if provided
            if progress_callback:
                progress_callback(i + 1, file_path, result.is_valid)
        
        self.logger.info(f"Batch validation complete: {len(valid_files)}/{len(file_paths)} files valid")
        return results, valid_files
    
    def _validate_file_system(self, file_path: str, errors: List, warnings: List):
        """Layer 1: File system validation - existence, accessibility, permissions."""
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                errors.append(ValidationError(
                    f"File does not exist: {file_path}", 
                    "file_access", 
                    file_path
                ))
                return
            
            # Check if it's actually a file (not a directory)
            if not os.path.isfile(file_path):
                errors.append(ValidationError(
                    f"Path is not a file: {file_path}", 
                    "file_access", 
                    file_path
                ))
                return
            
            # Check read permissions
            if not os.access(file_path, os.R_OK):
                errors.append(ValidationError(
                    f"File is not readable: {file_path}", 
                    "file_access", 
                    file_path
                ))
                return
            
            # Check file size (warn if empty or suspiciously small)
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                errors.append(ValidationError(
                    f"File is empty: {file_path}", 
                    "file_corruption", 
                    file_path
                ))
            elif file_size < 1024:  # Less than 1KB
                warnings.append(f"File is very small ({file_size} bytes): {file_path}")
            
        except OSError as e:
            errors.append(ValidationError(
                f"File system error: {str(e)}", 
                "file_access", 
                file_path
            ))
    
    def _validate_format(self, file_path: str, errors: List, warnings: List):
        """Layer 2: Format validation - extension and MIME type checking."""
        try:
            # Check file extension
            _, ext = os.path.splitext(file_path.lower())
            if ext not in self.SUPPORTED_EXTENSIONS:
                errors.append(ValidationError(
                    f"Unsupported file extension '{ext}'. Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}", 
                    "file_format", 
                    ext
                ))
                return
            
            # Check MIME type (if available)
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type and mime_type not in self.AUDIO_MIME_TYPES:
                warnings.append(f"Unexpected MIME type '{mime_type}' for audio file: {file_path}")
            
        except Exception as e:
            warnings.append(f"Could not validate format for {file_path}: {str(e)}")
    
    def _validate_content_with_pydub(self, file_path: str, errors: List, warnings: List) -> Optional[AudioFileInfo]:
        """Layer 3: Content validation using pydub - the core validation as suggested by Gemini."""
        try:
            self.logger.debug(f"Loading audio file with pydub: {file_path}")
            
            # This is the key insight from Gemini: loading with pydub IS the validation
            audio_segment = AudioSegment.from_file(file_path)
            
            # Extract file information
            file_info = AudioFileInfo(
                duration_ms=len(audio_segment),
                sample_rate=audio_segment.frame_rate,
                channels=audio_segment.channels,
                file_size=os.path.getsize(file_path),
                format=os.path.splitext(file_path)[1].lower().lstrip('.'),
                # Bitrate calculation (approximate)
                bitrate=self._calculate_bitrate(audio_segment, file_path)
            )
            
            # Basic sanity checks
            if file_info.duration_ms <= 0:
                errors.append(ValidationError(
                    f"Audio file has no duration: {file_path}", 
                    "file_corruption", 
                    file_path
                ))
            elif file_info.duration_ms < 1000:  # Less than 1 second
                warnings.append(f"Audio file is very short ({file_info.duration_ms}ms): {file_path}")
            
            if file_info.sample_rate <= 0:
                errors.append(ValidationError(
                    f"Invalid sample rate ({file_info.sample_rate}): {file_path}", 
                    "file_corruption", 
                    file_path
                ))
            
            if file_info.channels <= 0:
                errors.append(ValidationError(
                    f"Invalid channel count ({file_info.channels}): {file_path}", 
                    "file_corruption", 
                    file_path
                ))
            
            return file_info
            
        except CouldntDecodeError as e:
            # This is the key exception pydub raises for invalid audio files
            errors.append(ConversionError(
                f"Could not decode audio file: {str(e)}", 
                file_path
            ))
            return None
        except Exception as e:
            # Handle other pydub-related errors
            errors.append(FileProcessingError(
                f"Error loading audio file: {str(e)}", 
                file_path, 
                "content_validation"
            ))
            return None
    
    def _validate_constraints(self, file_path: str, file_info: Optional[AudioFileInfo], 
                             errors: List, warnings: List):
        """Layer 4: Constraint validation - file size, duration, and format limits."""
        if not file_info:
            return
        
        try:
            # File size constraints (configurable limits)
            max_file_size = 500 * 1024 * 1024  # 500MB max per file
            if file_info.file_size > max_file_size:
                warnings.append(f"Large file size ({file_info.file_size // (1024*1024)}MB): {file_path}")
            
            # Duration constraints
            max_duration_hours = 24  # 24 hours max per file
            max_duration_ms = max_duration_hours * 60 * 60 * 1000
            if file_info.duration_ms > max_duration_ms:
                warnings.append(f"Very long duration ({file_info.duration_ms // (60*1000)}min): {file_path}")
            
            # Sample rate validation
            common_rates = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000, 192000]
            if file_info.sample_rate not in common_rates:
                warnings.append(f"Unusual sample rate ({file_info.sample_rate}Hz): {file_path}")
            
            # Channel validation
            if file_info.channels > 2:
                warnings.append(f"More than stereo ({file_info.channels} channels): {file_path}")
            
        except Exception as e:
            warnings.append(f"Could not validate constraints for {file_path}: {str(e)}")
    
    def _validate_file_signature(self, file_path: str, errors: List, warnings: List):
        """Layer 5: File signature validation - verify file format by magic numbers."""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(32)  # Read first 32 bytes
                
                # Check against known signatures
                signature_detected = False
                for signature, format_name in self.FILE_SIGNATURES.items():
                    if header.startswith(signature):
                        signature_detected = True
                        
                        # Verify signature matches extension
                        _, ext = os.path.splitext(file_path.lower())
                        expected_ext = f".{format_name}"
                        if ext != expected_ext:
                            warnings.append(
                                f"File signature suggests {format_name} but extension is {ext}: {file_path}"
                            )
                        break
                
                if not signature_detected:
                    warnings.append(f"Could not identify file format by signature: {file_path}")
                    
        except Exception as e:
            warnings.append(f"Could not read file signature for {file_path}: {str(e)}")
    
    def _calculate_bitrate(self, audio_segment, file_path: str) -> Optional[int]:
        """Calculate approximate bitrate from audio segment and file size."""
        try:
            duration_seconds = len(audio_segment) / 1000.0
            file_size_bits = os.path.getsize(file_path) * 8
            bitrate = int(file_size_bits / duration_seconds) if duration_seconds > 0 else None
            return bitrate
        except:
            return None


class ValidationSummary:
    """Generate comprehensive validation summaries and reports."""
    
    @staticmethod
    def generate_report(results: List[ValidationResult]) -> str:
        """Generate a comprehensive validation report."""
        if not results:
            return "No files to validate."
        
        total_files = len(results)
        valid_files = sum(1 for r in results if r.is_valid)
        invalid_files = total_files - valid_files
        
        report = []
        report.append("Validation Report")
        report.append("=" * 50)
        report.append(f"Total files: {total_files}")
        report.append(f"Valid files: {valid_files}")
        report.append(f"Invalid files: {invalid_files}")
        report.append("")
        
        if invalid_files > 0:
            report.append("Invalid Files:")
            report.append("-" * 20)
            for result in results:
                if not result.is_valid:
                    report.append(f"• {os.path.basename(result.file_path)}")
                    for error in result.errors:
                        report.append(f"  - {str(error)}")
            report.append("")
        
        # Collect warnings
        all_warnings = []
        for result in results:
            for warning in result.warnings:
                all_warnings.append(f"{os.path.basename(result.file_path)}: {warning}")
        
        if all_warnings:
            report.append("Warnings:")
            report.append("-" * 20)
            for warning in all_warnings[:10]:  # Show first 10 warnings
                report.append(f"• {warning}")
            if len(all_warnings) > 10:
                report.append(f"... and {len(all_warnings) - 10} more warnings")
        
        return "\n".join(report)
    
    @staticmethod
    def get_failed_files(results: List[ValidationResult]) -> List[Tuple[str, List[AudiobookMakerError]]]:
        """Get list of failed files with their errors."""
        failed = []
        for result in results:
            if not result.is_valid:
                failed.append((result.file_path, result.errors))
        return failed


# Convenience functions for common validation scenarios
def validate_audio_files(file_paths: List[str], validation_level: ValidationLevel = ValidationLevel.NORMAL, progress_callback=None) -> Tuple[List[str], str]:
    """
    Validate a list of audio files and return valid files with a report.
    
    Args:
        file_paths: List of file paths to validate
        validation_level: Validation strictness level
        progress_callback: Optional callback for progress updates
    
    Returns:
        Tuple of (valid_file_paths, validation_report)
    """
    validator = AudioFileValidator(validation_level)
    results, valid_files = validator.validate_batch(file_paths, progress_callback)
    report = ValidationSummary.generate_report(results)
    
    return valid_files, report


def quick_validate_file(file_path: str) -> bool:
    """Quick validation check for a single file."""
    validator = AudioFileValidator(ValidationLevel.LAX)
    result = validator.validate_file(file_path)
    return result.is_valid


def validate_with_pydub_preflight(file_paths: List[str]) -> Tuple[List[str], List[AudiobookMakerError]]:
    """
    Gemini's suggested pre-flight validation approach.
    
    Returns:
        Tuple of (valid_file_paths, all_errors)
    """
    validator = AudioFileValidator(ValidationLevel.NORMAL)
    results, valid_files = validator.validate_batch(file_paths)
    
    all_errors = []
    for result in results:
        all_errors.extend(result.errors)
    
    return valid_files, all_errors