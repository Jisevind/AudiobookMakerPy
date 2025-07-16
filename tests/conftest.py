"""
Pytest configuration and fixtures for AudiobookMakerPy tests.
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "test_data"


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_audio_files(temp_dir):
    """Create sample audio files for testing."""
    # Create sample MP3 files (placeholder - in real tests you'd use actual audio files)
    files = []
    for i in range(3):
        filename = f"chapter_{i+1:02d}.mp3"
        filepath = os.path.join(temp_dir, filename)
        
        # Create a minimal MP3 file (this is just a placeholder)
        with open(filepath, 'wb') as f:
            # Write a minimal MP3 header (this won't be a valid MP3 but serves for testing)
            f.write(b'ID3\x03\x00\x00\x00\x00\x00\x00' + b'\x00' * 100)
        
        files.append(filepath)
    
    return files


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing."""
    return {
        'title': 'Test Audiobook',
        'author': 'Test Author',
        'album': 'Test Album',
        'year': '2024',
        'chapter_titles': ['Chapter 1', 'Chapter 2', 'Chapter 3']
    }


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """Mock FFmpeg dependency for testing."""
    def mock_check_output(cmd, **kwargs):
        if 'ffprobe' in cmd:
            return b'120.5'  # Mock duration
        elif 'ffmpeg' in cmd and '-version' in cmd:
            return b'ffmpeg version 4.4.0'
        return b''
    
    def mock_run(cmd, **kwargs):
        # Mock subprocess.run for FFmpeg commands
        class MockResult:
            returncode = 0
            stdout = "ffmpeg version 4.4.0"
            stderr = ""
        return MockResult()
    
    import subprocess
    monkeypatch.setattr(subprocess, 'check_output', mock_check_output)
    monkeypatch.setattr(subprocess, 'run', mock_run)


@pytest.fixture
def mock_mutagen(monkeypatch):
    """Mock mutagen dependency for testing."""
    class MockMP4:
        def __init__(self, filepath):
            self.filepath = filepath
            self.tags = {}
        
        def __setitem__(self, key, value):
            self.tags[key] = value
        
        def save(self):
            pass
    
    class MockMP4Cover:
        FORMAT_JPEG = 0
        FORMAT_PNG = 1
        
        def __init__(self, data, format):
            self.data = data
            self.format = format
    
    import sys
    from unittest.mock import MagicMock
    
    mock_mutagen = MagicMock()
    mock_mutagen.mp4.MP4 = MockMP4
    mock_mutagen.mp4.MP4Cover = MockMP4Cover
    
    sys.modules['mutagen'] = mock_mutagen
    sys.modules['mutagen.mp4'] = mock_mutagen.mp4


@pytest.fixture
def mock_pydub(monkeypatch):
    """Mock pydub dependency for testing."""
    class MockAudioSegment:
        def __init__(self, data=None):
            self.data = data
        
        @classmethod
        def from_file(cls, filepath):
            return cls()
        
        def export(self, filepath, format=None, **kwargs):
            # Create a dummy file
            with open(filepath, 'wb') as f:
                f.write(b'dummy audio data')
        
        def __len__(self):
            return 120000  # 2 minutes in milliseconds
    
    import sys
    from unittest.mock import MagicMock
    
    mock_pydub = MagicMock()
    mock_pydub.AudioSegment = MockAudioSegment
    
    sys.modules['pydub'] = mock_pydub


@pytest.fixture
def isolated_environment(temp_dir, monkeypatch):
    """Create an isolated environment for testing."""
    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    
    # Mock home directory
    monkeypatch.setenv('HOME', temp_dir)
    
    yield temp_dir
    
    # Restore original directory
    os.chdir(original_cwd)


# Test configuration
pytest_plugins = []