#!/usr/bin/env python3
"""
Build script for AudiobookMakerPy.

This script handles building, packaging, and distribution tasks.
"""

import os
import sys
import subprocess
import shutil
import argparse
from pathlib import Path


def run_command(cmd, cwd=None, check=True):
    """Run a command and handle errors."""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        if check:
            sys.exit(1)
        return e


def clean_build():
    """Clean build artifacts."""
    print("Cleaning build artifacts...")
    
    # Directories to clean
    clean_dirs = [
        "build",
        "dist",
        "src/audiobookmaker.egg-info",
        "*.egg-info",
        "__pycache__",
        ".pytest_cache",
        ".coverage",
        "htmlcov"
    ]
    
    for pattern in clean_dirs:
        for path in Path(".").glob(pattern):
            if path.is_dir():
                print(f"Removing directory: {path}")
                shutil.rmtree(path)
            elif path.is_file():
                print(f"Removing file: {path}")
                path.unlink()
    
    # Clean __pycache__ recursively
    for path in Path(".").rglob("__pycache__"):
        if path.is_dir():
            print(f"Removing __pycache__: {path}")
            shutil.rmtree(path)
    
    # Clean .pyc files
    for path in Path(".").rglob("*.pyc"):
        if path.is_file():
            print(f"Removing .pyc file: {path}")
            path.unlink()


def run_tests():
    """Run the test suite."""
    print("Running tests...")
    
    # Check if pytest is available
    try:
        result = run_command(["python", "-m", "pytest", "--version"], check=False)
        if result.returncode != 0:
            print("pytest not found, installing...")
            run_command(["python", "-m", "pip", "install", "pytest"])
    except FileNotFoundError:
        print("Python not found in PATH")
        sys.exit(1)
    
    # Run tests
    cmd = ["python", "-m", "pytest", "tests/", "-v"]
    
    # Add coverage if available
    try:
        run_command(["python", "-m", "pytest_cov", "--version"], check=False)
        cmd.extend(["--cov=src/audiobookmaker", "--cov-report=term-missing"])
    except:
        pass
    
    run_command(cmd)


def run_linting():
    """Run linting and formatting checks."""
    print("Running linting and formatting checks...")
    
    # Check if tools are available
    tools = ["black", "isort", "flake8"]
    missing_tools = []
    
    for tool in tools:
        try:
            run_command(["python", "-m", tool, "--version"], check=False)
        except:
            missing_tools.append(tool)
    
    if missing_tools:
        print(f"Installing missing tools: {missing_tools}")
        run_command(["python", "-m", "pip", "install"] + missing_tools)
    
    # Run black
    print("Running black...")
    run_command(["python", "-m", "black", "--check", "src/", "tests/"], check=False)
    
    # Run isort
    print("Running isort...")
    run_command(["python", "-m", "isort", "--check-only", "src/", "tests/"], check=False)
    
    # Run flake8
    print("Running flake8...")
    run_command(["python", "-m", "flake8", "src/", "tests/"], check=False)


def format_code():
    """Format code using black and isort."""
    print("Formatting code...")
    
    # Install tools if needed
    tools = ["black", "isort"]
    for tool in tools:
        try:
            run_command(["python", "-m", tool, "--version"], check=False)
        except:
            print(f"Installing {tool}...")
            run_command(["python", "-m", "pip", "install", tool])
    
    # Format with black
    run_command(["python", "-m", "black", "src/", "tests/"])
    
    # Sort imports with isort
    run_command(["python", "-m", "isort", "src/", "tests/"])


def build_package():
    """Build the package."""
    print("Building package...")
    
    # Clean first
    clean_build()
    
    # Install build tool if needed
    try:
        run_command(["python", "-m", "build", "--version"], check=False)
    except:
        print("Installing build tool...")
        run_command(["python", "-m", "pip", "install", "build"])
    
    # Build package
    run_command(["python", "-m", "build"])
    
    print("Package built successfully!")
    print("Built files:")
    for path in Path("dist").glob("*"):
        print(f"  {path}")


def install_dev():
    """Install package in development mode."""
    print("Installing in development mode...")
    
    # Install in editable mode with dev dependencies
    run_command(["python", "-m", "pip", "install", "-e", ".[dev]"])
    
    print("Development installation complete!")


def create_release():
    """Create a release package."""
    print("Creating release...")
    
    # Run full test suite
    run_tests()
    
    # Run linting
    run_linting()
    
    # Build package
    build_package()
    
    print("Release created successfully!")
    print("Next steps:")
    print("1. Test the built package: pip install dist/*.whl")
    print("2. Upload to PyPI: python -m twine upload dist/*")


def main():
    """Main build script."""
    parser = argparse.ArgumentParser(description="Build script for AudiobookMakerPy")
    parser.add_argument("action", choices=[
        "clean", "test", "lint", "format", "build", "install-dev", "release"
    ], help="Action to perform")
    
    args = parser.parse_args()
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir.parent)
    
    # Execute action
    if args.action == "clean":
        clean_build()
    elif args.action == "test":
        run_tests()
    elif args.action == "lint":
        run_linting()
    elif args.action == "format":
        format_code()
    elif args.action == "build":
        build_package()
    elif args.action == "install-dev":
        install_dev()
    elif args.action == "release":
        create_release()
    else:
        print(f"Unknown action: {args.action}")
        sys.exit(1)


if __name__ == "__main__":
    main()