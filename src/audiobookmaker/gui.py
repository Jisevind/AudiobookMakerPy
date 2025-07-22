#!/usr/bin/env python3
"""
GUI entry point for AudiobookMaker.

This module provides the main entry point for launching the PyQt6 GUI application.
"""

import sys
import os
import logging
import multiprocessing
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

# CRITICAL: Fix for PyInstaller multiprocessing issues
# This prevents worker processes from creating new GUI windows
if __name__ == '__main__':
    multiprocessing.freeze_support()
    # Ensure multiprocessing uses spawn method for PyInstaller compatibility
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        # Already set, ignore
        pass

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from audiobookmaker.ui.main_window import MainWindow, get_application_icon
except ImportError as e:
    print(f"Error importing UI components: {e}")
    print("Make sure PyQt6 is installed: pip install PyQt6")
    sys.exit(1)


def setup_logging():
    """Set up logging for the GUI application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            # Could add file handler here if needed
        ]
    )


def check_dependencies():
    """Check if required dependencies are available."""
    missing_deps = []
    
    # Check for PyQt6
    try:
        import PyQt6
    except ImportError:
        missing_deps.append("PyQt6")
    
    # Check for FFmpeg (this will be checked by the processor later)
    # We don't check it here to avoid import issues
    
    if missing_deps:
        error_msg = f"Missing required dependencies: {', '.join(missing_deps)}\n\n"
        error_msg += "Please install missing dependencies:\n"
        for dep in missing_deps:
            if dep == "PyQt6":
                error_msg += "  pip install PyQt6\n"
        
        print(error_msg)
        return False
    
    return True


def main():
    """Main entry point for the GUI application."""
    # Enable high DPI scaling for PyQt6
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    
    # Check dependencies first
    if not check_dependencies():
        return 1
    
    # Set up logging
    setup_logging()
    
    # Create the application
    app = QApplication(sys.argv)
    app.setApplicationName("AudiobookMaker")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("AudiobookMaker")
    
    # Let PyQt6 handle DPI scaling automatically
    # (PyInstaller executables handle this better than manual scaling)
    
    # Set application icon (if available)
    try:
        app_icon = get_application_icon()
        app.setWindowIcon(app_icon)
    except Exception as e:
        logging.warning(f"Could not set application icon: {e}")
    
    try:
        # Create and show the main window
        window = MainWindow()
        window.show()
        
        # Start the event loop
        return app.exec()
        
    except Exception as e:
        logging.error(f"Error starting GUI: {e}", exc_info=True)
        
        # Show error dialog if possible
        try:
            QMessageBox.critical(
                None,
                "Application Error",
                f"Failed to start AudiobookMaker GUI:\n\n{str(e)}\n\n"
                "Please check the console for more details."
            )
        except:
            print(f"Fatal error: {e}")
        
        return 1


if __name__ == "__main__":
    sys.exit(main())