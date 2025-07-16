"""
AudiobookMakerPy - Convert audio files to M4B audiobook format

A comprehensive tool for converting audio files into audiobook format with
smart metadata extraction, chapter generation, and resume functionality.
"""

__version__ = "2.0.0"
__author__ = "AudiobookMakerPy Project"
__email__ = "contact@audiobookmaker.py"

from .core.processor import AudiobookProcessor
from .core.metadata import MetadataExtractor
from .exceptions import AudiobookMakerError

__all__ = [
    "AudiobookProcessor",
    "MetadataExtractor", 
    "AudiobookMakerError",
    "__version__"
]