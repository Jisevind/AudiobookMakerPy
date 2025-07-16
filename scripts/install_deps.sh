#!/bin/bash

# AudiobookMakerPy Dependency Installation Script
# This script installs required dependencies for AudiobookMakerPy

set -e

echo "=== AudiobookMakerPy Dependency Installation ==="
echo

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]]; then
    OS="windows"
fi

echo "Detected OS: $OS"
echo

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install FFmpeg
install_ffmpeg() {
    echo "Installing FFmpeg..."
    
    case $OS in
        "linux")
            if command_exists apt-get; then
                sudo apt-get update
                sudo apt-get install -y ffmpeg
            elif command_exists yum; then
                sudo yum install -y ffmpeg
            elif command_exists pacman; then
                sudo pacman -S --noconfirm ffmpeg
            elif command_exists dnf; then
                sudo dnf install -y ffmpeg
            else
                echo "Error: Unknown package manager. Please install FFmpeg manually."
                exit 1
            fi
            ;;
        "macos")
            if command_exists brew; then
                brew install ffmpeg
            elif command_exists port; then
                sudo port install ffmpeg
            else
                echo "Error: Please install Homebrew or MacPorts first."
                echo "Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                exit 1
            fi
            ;;
        "windows")
            echo "Error: Windows detected. Please install FFmpeg manually:"
            echo "1. Download FFmpeg from https://ffmpeg.org/download.html"
            echo "2. Extract to C:\\ffmpeg\\"
            echo "3. Add C:\\ffmpeg\\bin to your PATH"
            exit 1
            ;;
        *)
            echo "Error: Unknown OS. Please install FFmpeg manually."
            exit 1
            ;;
    esac
}

# MP4Box is no longer required - FFmpeg handles all audio operations
# This function is kept for backward compatibility but does nothing
install_mp4box() {
    echo "Note: MP4Box is no longer required - FFmpeg handles all audio operations"
    echo "Skipping MP4Box installation..."
}

# Function to install Python dependencies
install_python_deps() {
    echo "Installing Python dependencies..."
    
    # Check if pip is available
    if ! command_exists pip && ! command_exists pip3; then
        echo "Error: pip not found. Please install pip first."
        exit 1
    fi
    
    # Use pip3 if available, otherwise pip
    PIP_CMD="pip"
    if command_exists pip3; then
        PIP_CMD="pip3"
    fi
    
    # Install optional dependencies for enhanced features
    echo "Installing optional Python dependencies..."
    $PIP_CMD install mutagen pydub
    
    echo "Python dependencies installed successfully."
}

# Main installation process
main() {
    echo "Starting dependency installation..."
    echo
    
    # Check for existing installations
    echo "Checking existing installations..."
    
    if command_exists ffmpeg; then
        echo "✓ FFmpeg is already installed"
        ffmpeg -version | head -1
    else
        echo "✗ FFmpeg not found"
        install_ffmpeg
    fi
    
    echo
    
    # MP4Box is no longer required - skip check
    echo "Note: MP4Box is no longer required (FFmpeg handles all operations)"
    
    echo
    
    # Install Python dependencies
    install_python_deps
    
    echo
    echo "=== Installation Complete ==="
    echo
    echo "Verifying installations..."
    
    # Verify FFmpeg
    if command_exists ffmpeg; then
        echo "✓ FFmpeg: $(ffmpeg -version | head -1)"
    else
        echo "✗ FFmpeg: Not found"
    fi
    
    # MP4Box is no longer required
    echo "Note: MP4Box not required - FFmpeg handles all audio operations"
    
    # Verify Python dependencies
    if python3 -c "import mutagen" 2>/dev/null; then
        echo "✓ Mutagen: Available"
    else
        echo "✗ Mutagen: Not found"
    fi
    
    if python3 -c "import pydub" 2>/dev/null; then
        echo "✓ Pydub: Available"
    else
        echo "✗ Pydub: Not found"
    fi
    
    echo
    echo "Installation complete! You can now use AudiobookMakerPy."
    echo
    echo "Next steps:"
    echo "1. Install AudiobookMakerPy: pip install ."
    echo "2. Test installation: audiobookmaker --version"
    echo "3. See usage guide: audiobookmaker --help"
}

# Run main function
main "$@"