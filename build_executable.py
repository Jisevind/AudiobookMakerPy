#!/usr/bin/env python3
"""
Build script for creating AudiobookMaker GUI executable.

This script uses PyInstaller to create a standalone executable
that includes all dependencies.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def check_dependencies():
    """Check if required build dependencies are installed."""
    try:
        import PyInstaller
        print(f"✅ PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("❌ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"], check=True)
        print("✅ PyInstaller installed")

    # Check other dependencies
    missing = []
    try:
        import PyQt6
        print(f"✅ PyQt6 found")
    except ImportError:
        missing.append("PyQt6")

    try:
        import mutagen
        print(f"✅ mutagen found")
    except ImportError:
        missing.append("mutagen")

    try:
        import pydub
        print(f"✅ pydub found")
    except ImportError:
        missing.append("pydub")

    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("Installing missing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install"] + missing, check=True)
        print("✅ All dependencies installed")


def clean_build_directories():
    """Clean previous build artifacts."""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"🧹 Cleaning {dir_name}/")
            shutil.rmtree(dir_name)
    
    # Clean .pyc files
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.pyc'):
                os.remove(os.path.join(root, file))


def build_executable():
    """Build the executable using PyInstaller."""
    print("🔨 Building AudiobookMaker GUI executable...")
    
    # Run PyInstaller with the spec file
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "audiobookmaker-gui.spec"]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Build completed successfully!")
        
        # Check if executable was created
        exe_path = Path("dist/AudiobookMaker-GUI")
        if os.name == 'nt':  # Windows
            exe_path = Path("dist/AudiobookMaker-GUI.exe")
            
        if exe_path.exists():
            print(f"📦 Executable created: {exe_path}")
            print(f"📏 Size: {exe_path.stat().st_size / (1024*1024):.1f} MB")
        else:
            print("⚠️  Executable not found in expected location")
            
    except subprocess.CalledProcessError as e:
        print("❌ Build failed!")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False
    
    return True


def main():
    """Main build process."""
    print("🚀 AudiobookMaker GUI Executable Builder")
    print("=" * 50)
    
    # Check we're in the right directory
    if not os.path.exists("src/audiobookmaker/gui.py"):
        print("❌ This script must be run from the project root directory")
        sys.exit(1)
    
    try:
        # Step 1: Check dependencies
        print("\n📋 Checking dependencies...")
        check_dependencies()
        
        # Step 2: Clean build directories
        print("\n🧹 Cleaning build directories...")
        clean_build_directories()
        
        # Step 3: Build executable
        print("\n🔨 Building executable...")
        if build_executable():
            print("\n🎉 Build completed successfully!")
            print("\nYour executable is ready in the 'dist/' directory.")
            print("\n📝 Note: Make sure FFmpeg is installed on the target system")
            print("   or place ffmpeg.exe in the same directory as the executable.")
        else:
            print("\n💥 Build failed. Check the error messages above.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Build cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()