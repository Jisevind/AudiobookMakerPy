"""
Tests for the AudiobookProcessor class.
"""

import pytest
import os
from unittest.mock import Mock, patch

from audiobookmaker.core.processor import AudiobookProcessor, ProcessingResult
from audiobookmaker.utils.validation import ValidationLevel
from audiobookmaker.exceptions import AudiobookMakerError


class TestAudiobookProcessor:
    """Test cases for AudiobookProcessor."""
    
    def test_init_default_values(self):
        """Test processor initialization with default values."""
        processor = AudiobookProcessor()
        
        assert processor.bitrate == "128k"
        assert processor.cores == os.cpu_count() or 4
        assert processor.validation_level == ValidationLevel.NORMAL
        assert processor.resume_mode == "auto"
        assert processor.quiet == False
        assert processor.gui_mode == False
        assert processor.json_mode == False
    
    def test_init_custom_values(self):
        """Test processor initialization with custom values."""
        processor = AudiobookProcessor(
            bitrate="192k",
            cores=8,
            validation_level=ValidationLevel.STRICT,
            resume_mode="never",
            quiet=True,
            gui_mode=True,
            json_mode=True
        )
        
        assert processor.bitrate == "192k"
        assert processor.cores == 8
        assert processor.validation_level == ValidationLevel.STRICT
        assert processor.resume_mode == "never"
        assert processor.quiet == True
        assert processor.gui_mode == True
        assert processor.json_mode == True
    
    @patch('audiobookmaker.core.processor.AudioConverter')
    def test_dependency_check(self, mock_converter):
        """Test dependency checking during initialization."""
        # Mock successful dependency check
        mock_converter_instance = Mock()
        mock_converter.return_value = mock_converter_instance
        
        processor = AudiobookProcessor()
        
        # Verify dependency check was called
        mock_converter_instance.check_ffmpeg_dependency.assert_called_once()
    
    def test_validate_and_get_input_files_directory(self, temp_dir, sample_audio_files):
        """Test input file validation with directory input."""
        processor = AudiobookProcessor(quiet=True)
        
        # Create test files in temp directory
        for i, filepath in enumerate(sample_audio_files):
            # Files are already created by fixture
            pass
        
        input_files = processor._validate_and_get_input_files([temp_dir])
        
        assert len(input_files) == 3
        assert all(filepath.endswith('.mp3') for filepath in input_files)
        assert all(os.path.exists(filepath) for filepath in input_files)
    
    def test_validate_and_get_input_files_individual(self, sample_audio_files):
        """Test input file validation with individual files."""
        processor = AudiobookProcessor(quiet=True)
        
        input_files = processor._validate_and_get_input_files(sample_audio_files)
        
        assert len(input_files) == 3
        assert input_files == sorted(sample_audio_files)
    
    def test_validate_and_get_input_files_nonexistent(self):
        """Test validation with non-existent file."""
        processor = AudiobookProcessor(quiet=True)
        
        with pytest.raises(Exception):  # Should raise ValidationError
            processor._validate_and_get_input_files(['/nonexistent/path'])
    
    def test_extract_metadata_default(self, sample_audio_files):
        """Test metadata extraction with default settings."""
        processor = AudiobookProcessor(quiet=True)
        
        with patch.object(processor.metadata_extractor, 'extract_comprehensive_metadata') as mock_extract:
            mock_extract.return_value = {
                'title': 'Test Book',
                'author': 'Test Author',
                'chapter_titles': ['Chapter 1', 'Chapter 2', 'Chapter 3']
            }
            
            metadata = processor._extract_metadata(
                sample_audio_files, None, None, 'auto'
            )
            
            assert metadata['title'] == 'Test Book'
            assert metadata['author'] == 'Test Author'
            assert len(metadata['chapter_titles']) == 3
    
    def test_extract_metadata_custom_values(self, sample_audio_files):
        """Test metadata extraction with custom title and author."""
        processor = AudiobookProcessor(quiet=True)
        
        with patch.object(processor.metadata_extractor, 'extract_comprehensive_metadata') as mock_extract:
            mock_extract.return_value = {
                'title': 'Original Title',
                'author': 'Original Author',
                'chapter_titles': ['Chapter 1', 'Chapter 2', 'Chapter 3']
            }
            
            metadata = processor._extract_metadata(
                sample_audio_files, 'Custom Title', 'Custom Author', 'auto'
            )
            
            assert metadata['title'] == 'Custom Title'
            assert metadata['author'] == 'Custom Author'
    
    def test_extract_metadata_generic_chapters(self, sample_audio_files):
        """Test metadata extraction with generic chapter titles."""
        processor = AudiobookProcessor(quiet=True)
        
        with patch.object(processor.metadata_extractor, 'extract_comprehensive_metadata') as mock_extract:
            mock_extract.return_value = {
                'title': 'Test Book',
                'author': 'Test Author',
                'chapter_titles': ['Smart Chapter 1', 'Smart Chapter 2', 'Smart Chapter 3']
            }
            
            metadata = processor._extract_metadata(
                sample_audio_files, None, None, 'generic'
            )
            
            # Should override with generic titles
            assert metadata['chapter_titles'] == ['Chapter 1', 'Chapter 2', 'Chapter 3']
    
    def test_determine_output_path_explicit(self, sample_audio_files):
        """Test output path determination with explicit path."""
        processor = AudiobookProcessor(quiet=True)
        
        output_path = processor._determine_output_path(
            sample_audio_files, 
            '/custom/path/book.m4b',
            None, None, '{title}',
            {'title': 'Test Book'}
        )
        
        assert output_path == '/custom/path/book.m4b'
    
    def test_determine_output_path_template(self, sample_audio_files, temp_dir):
        """Test output path determination with template."""
        processor = AudiobookProcessor(quiet=True)
        
        # Move sample files to temp_dir so directory detection works
        for i, old_path in enumerate(sample_audio_files):
            new_path = os.path.join(temp_dir, f'chapter_{i+1:02d}.mp3')
            os.rename(old_path, new_path)
            sample_audio_files[i] = new_path
        
        output_path = processor._determine_output_path(
            sample_audio_files,
            None, None, None, 
            '{author} - {title}',
            {'title': 'Test Book', 'author': 'Test Author'}
        )
        
        expected_filename = 'Test Author - Test Book.m4b'
        assert output_path.endswith(expected_filename)


class TestProcessingResult:
    """Test cases for ProcessingResult."""
    
    def test_processing_result_success(self):
        """Test successful processing result."""
        result = ProcessingResult(
            success=True,
            output_file='/path/to/output.m4b',
            total_hours=2,
            total_minutes=30,
            errors=[]
        )
        
        assert result.success == True
        assert result.output_file == '/path/to/output.m4b'
        assert result.total_hours == 2
        assert result.total_minutes == 30
        assert result.errors == []
        assert result.error_message is None
    
    def test_processing_result_failure(self):
        """Test failed processing result."""
        result = ProcessingResult(
            success=False,
            error_message="Processing failed",
            errors=["Error 1", "Error 2"]
        )
        
        assert result.success == False
        assert result.error_message == "Processing failed"
        assert len(result.errors) == 2
        assert result.output_file is None
    
    def test_processing_result_default_errors(self):
        """Test that errors list is initialized properly."""
        result = ProcessingResult(success=True)
        
        assert result.errors == []
        assert isinstance(result.errors, list)