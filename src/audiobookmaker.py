#!/usr/bin/env python3
"""
AudiobookMakerPy - Main entry point script.

This script provides the main entry point for the AudiobookMakerPy application.
It can be used as a standalone script or installed as a package.
"""

import sys
import os

# Add the src directory to the Python path for development use
if __name__ == '__main__':
    # Get the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Add src directory to Python path if not already there
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

# Import and run the CLI
from audiobookmaker.cli import main

if __name__ == '__main__':
    main()