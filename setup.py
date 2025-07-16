#!/usr/bin/env python3
"""
Setup script for AudiobookMakerPy.

This setup.py is provided for backward compatibility.
The project is primarily configured via pyproject.toml.
"""

from setuptools import setup, find_packages
import os

# Read the contents of your README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="audiobookmaker",
    version="2.0.0",
    author="AudiobookMakerPy Project",
    author_email="contact@audiobookmaker.py",
    description="Convert audio files to M4B audiobook format with smart metadata extraction",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/audiobookmaker/AudiobookMakerPy",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Sound/Audio :: Conversion",
        "Topic :: System :: Archiving :: Backup",
    ],
    python_requires=">=3.7",
    install_requires=[
        # Core dependencies are external tools (FFmpeg only)
        # Python dependencies are optional for enhanced features
    ],
    extras_require={
        "enhanced": [
            "mutagen>=1.45.0",  # Enhanced metadata support
            "pydub>=0.25.0",    # Alternative audio processing
        ],
        "dev": [
            "pytest>=6.0.0",
            "pytest-cov>=2.10.0",
            "black>=21.0.0",
            "isort>=5.0.0",
            "flake8>=3.8.0",
            "mypy>=0.812",
        ],
    },
    entry_points={
        "console_scripts": [
            "audiobookmaker=audiobookmaker.cli:main",
        ],
    },
    keywords="audiobook m4b audio conversion metadata chapters",
    project_urls={
        "Bug Reports": "https://github.com/audiobookmaker/AudiobookMakerPy/issues",
        "Source": "https://github.com/audiobookmaker/AudiobookMakerPy",
    },
)