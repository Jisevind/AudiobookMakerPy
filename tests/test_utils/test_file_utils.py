"""
Tests for file utility functions.
"""

import pytest
import os
import json
import tempfile
import subprocess
from unittest.mock import patch, Mock

from audiobookmaker.utils.file_utils import (
    natural_keys,
    get_audio_duration,
    create_predictable_temp_dir,
    validate_receipt_file,
    create_receipt_file,
    cleanup_old_cache_directories,
    cleanup_temp_files,
    get_safe_cpu_default,
    ms_to_timestamp,
    sanitize_filename,
    ensure_directory_exists,
    get_file_size_mb,
    is_audio_file,
    get_directory_size_mb
)


class TestNaturalKeys:
    """Test cases for natural_keys function."""
    
    def test_natural_keys_numbers(self):
        """Test natural sorting with numbers."""
        test_strings = ['file1.mp3', 'file10.mp3', 'file2.mp3', 'file20.mp3']
        sorted_strings = sorted(test_strings, key=natural_keys)
        
        expected = ['file1.mp3', 'file2.mp3', 'file10.mp3', 'file20.mp3']
        assert sorted_strings == expected
    
    def test_natural_keys_mixed(self):
        """Test natural sorting with mixed content."""
        test_strings = ['chapter2.mp3', 'chapter10.mp3', 'chapter1.mp3', 'intro.mp3']
        sorted_strings = sorted(test_strings, key=natural_keys)
        
        expected = ['chapter1.mp3', 'chapter2.mp3', 'chapter10.mp3', 'intro.mp3']
        assert sorted_strings == expected
    
    def test_natural_keys_no_numbers(self):
        """Test natural sorting with no numbers."""
        test_strings = ['zebra.mp3', 'apple.mp3', 'banana.mp3']
        sorted_strings = sorted(test_strings, key=natural_keys)
        
        expected = ['apple.mp3', 'banana.mp3', 'zebra.mp3']
        assert sorted_strings == expected


class TestGetAudioDuration:
    """Test cases for get_audio_duration function."""
    
    @patch('audiobookmaker.utils.file_utils.subprocess.check_output')
    def test_get_audio_duration_success(self, mock_check_output):
        """Test successful audio duration extraction."""
        mock_check_output.return_value = b'120.5\n'
        
        duration = get_audio_duration('/path/to/audio.mp3')
        
        assert duration == 120500  # 120.5 seconds in milliseconds
        mock_check_output.assert_called_once()
    
    @patch('audiobookmaker.utils.file_utils.subprocess.check_output')
    def test_get_audio_duration_failure(self, mock_check_output):
        """Test audio duration extraction failure."""
        mock_check_output.side_effect = subprocess.CalledProcessError(1, 'ffprobe')
        
        duration = get_audio_duration('/path/to/audio.mp3')
        
        assert duration == 0


class TestPredictableTempDir:
    """Test cases for create_predictable_temp_dir function."""
    
    def test_create_predictable_temp_dir_consistent(self):
        """Test that same inputs create same temp dir."""
        input_files = ['/path/to/file1.mp3', '/path/to/file2.mp3']
        output_file = '/output/audiobook.m4b'
        bitrate = '128k'
        
        temp_dir1 = create_predictable_temp_dir(input_files, output_file, bitrate)
        temp_dir2 = create_predictable_temp_dir(input_files, output_file, bitrate)
        
        assert temp_dir1 == temp_dir2
    
    def test_create_predictable_temp_dir_different_inputs(self):
        """Test that different inputs create different temp dirs."""
        input_files1 = ['/path/to/file1.mp3']
        input_files2 = ['/path/to/file2.mp3']
        output_file = '/output/audiobook.m4b'
        bitrate = '128k'
        
        temp_dir1 = create_predictable_temp_dir(input_files1, output_file, bitrate)
        temp_dir2 = create_predictable_temp_dir(input_files2, output_file, bitrate)
        
        assert temp_dir1 != temp_dir2
    
    def test_create_predictable_temp_dir_format(self):
        """Test temp dir format."""
        input_files = ['/path/to/file1.mp3']
        output_file = '/output/audiobook.m4b'
        bitrate = '128k'
        
        temp_dir = create_predictable_temp_dir(input_files, output_file, bitrate)
        
        assert 'audiobookmaker_' in temp_dir
        assert len(temp_dir.split('audiobookmaker_')[1]) == 12  # 12 char hash


class TestReceiptFile:
    """Test cases for receipt file functions."""
    
    def test_create_receipt_file(self, temp_dir):
        """Test receipt file creation."""
        input_file = os.path.join(temp_dir, 'test.mp3')
        
        # Create a dummy input file
        with open(input_file, 'w') as f:
            f.write('dummy content')
        
        create_receipt_file(input_file, temp_dir)
        
        # Check receipt file was created
        receipt_file = os.path.join(temp_dir, 'test.receipt')
        assert os.path.exists(receipt_file)
        
        # Check receipt file content
        with open(receipt_file, 'r') as f:
            receipt = json.load(f)
        
        assert receipt['source_file'] == input_file
        assert 'source_mtime' in receipt
        assert 'conversion_time' in receipt
    
    def test_validate_receipt_file_valid(self, temp_dir):
        """Test receipt file validation with valid receipt."""
        input_file = os.path.join(temp_dir, 'test.mp3')
        
        # Create input file
        with open(input_file, 'w') as f:
            f.write('dummy content')
        
        # Create receipt file
        create_receipt_file(input_file, temp_dir)
        
        # Validate receipt
        assert validate_receipt_file(input_file, temp_dir) == True
    
    def test_validate_receipt_file_missing(self, temp_dir):
        """Test receipt file validation with missing receipt."""
        input_file = os.path.join(temp_dir, 'test.mp3')
        
        # Create input file but no receipt
        with open(input_file, 'w') as f:
            f.write('dummy content')
        
        # Validate receipt
        assert validate_receipt_file(input_file, temp_dir) == False
    
    def test_validate_receipt_file_modified(self, temp_dir):
        """Test receipt file validation with modified source file."""
        input_file = os.path.join(temp_dir, 'test.mp3')
        
        # Create input file
        with open(input_file, 'w') as f:
            f.write('dummy content')
        
        # Create receipt file
        create_receipt_file(input_file, temp_dir)
        
        # Modify input file with significant time difference
        import time
        time.sleep(1.1)  # Ensure different mtime (more than 1 second)
        with open(input_file, 'w') as f:
            f.write('modified content')
        
        # Validate receipt should fail
        assert validate_receipt_file(input_file, temp_dir) == False


class TestUtilityFunctions:
    """Test cases for various utility functions."""
    
    def test_get_safe_cpu_default(self):
        """Test safe CPU default calculation."""
        cpu_default = get_safe_cpu_default()
        
        assert isinstance(cpu_default, int)
        assert cpu_default >= 1
        assert cpu_default <= 4
    
    def test_ms_to_timestamp(self):
        """Test millisecond to timestamp conversion."""
        test_cases = [
            (0, '00:00:00.000'),
            (1000, '00:00:01.000'),
            (60000, '00:01:00.000'),
            (3661500, '01:01:01.500'),
            (90075, '00:01:30.075')
        ]
        
        for ms, expected in test_cases:
            result = ms_to_timestamp(ms)
            assert result == expected
    
    def test_sanitize_filename(self):
        """Test filename sanitization."""
        test_cases = [
            ('normal_file.mp3', 'normal_file.mp3'),
            ('file<with>bad:chars.mp3', 'file_with_bad_chars.mp3'),
            ('file/with\\path|chars.mp3', 'file_with_path_chars.mp3'),
            ('file___with___multiple.mp3', 'file_with_multiple.mp3'),
            ('  _file_with_spaces_  ', 'file_with_spaces'),
        ]
        
        for input_name, expected in test_cases:
            result = sanitize_filename(input_name)
            assert result == expected
    
    def test_ensure_directory_exists(self, temp_dir):
        """Test directory creation."""
        test_dir = os.path.join(temp_dir, 'new_directory')
        
        assert not os.path.exists(test_dir)
        
        ensure_directory_exists(test_dir)
        
        assert os.path.exists(test_dir)
        assert os.path.isdir(test_dir)
    
    def test_get_file_size_mb(self, temp_dir):
        """Test file size calculation."""
        test_file = os.path.join(temp_dir, 'test.txt')
        
        # Create file with known size
        with open(test_file, 'w') as f:
            f.write('x' * 1024 * 1024)  # 1 MB
        
        size = get_file_size_mb(test_file)
        assert abs(size - 1.0) < 0.01  # Should be approximately 1 MB
    
    def test_get_file_size_mb_nonexistent(self):
        """Test file size calculation for nonexistent file."""
        size = get_file_size_mb('/nonexistent/file.txt')
        assert size == 0.0
    
    def test_is_audio_file(self):
        """Test audio file detection."""
        test_cases = [
            ('file.mp3', True),
            ('file.wav', True),
            ('file.m4a', True),
            ('file.flac', True),
            ('file.ogg', True),
            ('file.aac', True),
            ('file.m4b', True),
            ('file.MP3', True),  # Case insensitive
            ('file.txt', False),
            ('file.jpg', False),
            ('file', False),
        ]
        
        for filename, expected in test_cases:
            result = is_audio_file(filename)
            assert result == expected
    
    def test_get_directory_size_mb(self, temp_dir):
        """Test directory size calculation."""
        # Create some test files
        for i in range(3):
            test_file = os.path.join(temp_dir, f'test{i}.txt')
            with open(test_file, 'w') as f:
                f.write('x' * 1024 * 512)  # 0.5 MB each
        
        size = get_directory_size_mb(temp_dir)
        assert abs(size - 1.5) < 0.01  # Should be approximately 1.5 MB


class TestCleanupFunctions:
    """Test cases for cleanup functions."""
    
    @patch('audiobookmaker.utils.file_utils.glob.glob')
    @patch('audiobookmaker.utils.file_utils.os.path.getmtime')
    @patch('audiobookmaker.utils.file_utils.os.path.isdir')
    @patch('audiobookmaker.utils.file_utils.shutil.rmtree')
    def test_cleanup_old_cache_directories(self, mock_rmtree, mock_isdir, mock_getmtime, mock_glob):
        """Test cleanup of old cache directories."""
        # Mock old cache directories
        mock_glob.return_value = ['/tmp/audiobookmaker_abc123', '/tmp/audiobookmaker_def456']
        mock_isdir.return_value = True
        
        # Mock old modification times (older than 30 days)
        import time
        old_time = time.time() - (31 * 24 * 3600)  # 31 days ago
        mock_getmtime.return_value = old_time
        
        # Mock directory walking for size calculation
        with patch('audiobookmaker.utils.file_utils.os.walk') as mock_walk:
            mock_walk.return_value = [('/tmp/audiobookmaker_abc123', [], ['file1.txt', 'file2.txt'])]
            
            with patch('audiobookmaker.utils.file_utils.os.path.getsize') as mock_getsize:
                mock_getsize.return_value = 1024 * 1024  # 1 MB per file
                
                removed, freed_mb = cleanup_old_cache_directories(max_age_days=30)
                
                assert removed == 2
                assert freed_mb > 0
                assert mock_rmtree.call_count == 2
    
    @patch('audiobookmaker.utils.file_utils.shutil.rmtree')
    def test_cleanup_temp_files(self, mock_rmtree, temp_dir):
        """Test temp file cleanup."""
        cleanup_temp_files(temp_dir)
        
        mock_rmtree.assert_called_once_with(temp_dir)
    
    @patch('audiobookmaker.utils.file_utils.shutil.rmtree')
    def test_cleanup_temp_files_nonexistent(self, mock_rmtree):
        """Test temp file cleanup with nonexistent directory."""
        cleanup_temp_files('/nonexistent/directory')
        
        # Should not call rmtree for nonexistent directory
        mock_rmtree.assert_not_called()