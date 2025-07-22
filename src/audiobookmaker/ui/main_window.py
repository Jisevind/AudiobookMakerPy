"""
Main window for the AudiobookMaker PyQt6 GUI.
"""

import os
import sys
from typing import List, Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QMenuBar, QToolBar, QStatusBar, QMessageBox, QProgressBar,
    QLabel, QPushButton, QFileDialog, QApplication
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QIcon, QAction

from .widgets.input_tab import InputFilesTab
from .widgets.output_tab import OutputSettingsTab
from .widgets.cover_tab import CoverArtTab
from .widgets.chapters_tab import ChaptersTab
from .widgets.processing_tab import ProcessingTab
from ..core.processor import AudiobookProcessor, ProcessingResult
from ..utils.progress_tracker import ProgressTracker


def get_application_icon():
    """Get the application icon path."""
    # Try multiple locations for the icon
    possible_paths = [
        # When running from source
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'assets', 'audiobook-maker-icon.ico'),
        # When running from built executable (PyInstaller temp folder)
        os.path.join(sys._MEIPASS, 'assets', 'audiobook-maker-icon.ico') if hasattr(sys, '_MEIPASS') else None,
        # When running from built executable (direct path)
        os.path.join(os.path.dirname(sys.executable), 'assets', 'audiobook-maker-icon.ico'),
        # Alternative path for executable
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'assets', 'audiobook-maker-icon.ico'),
    ]
    
    for path in possible_paths:
        if path and os.path.exists(path):
            return QIcon(path)
    
    # Return empty icon if not found
    return QIcon()


class ProcessingThread(QThread):
    """Thread for running audiobook processing without blocking UI."""
    
    progress_updated = pyqtSignal(str, int)  # message, percentage
    processing_finished = pyqtSignal(object)  # ProcessingResult
    error_occurred = pyqtSignal(str)
    command_executed = pyqtSignal(str)  # FFmpeg command
    
    def __init__(self, processor: AudiobookProcessor, **kwargs):
        super().__init__()
        self.processor = processor
        self.processing_args = kwargs
        self.is_cancelled = False
        
    def run(self):
        """Run the processing in background thread."""
        try:
            # Monkey-patch subprocess to capture FFmpeg commands
            import subprocess
            import logging
            
            original_run = subprocess.run
            original_popen = subprocess.Popen
            
            def patched_run(cmd, *args, **kwargs):
                if isinstance(cmd, list) and len(cmd) > 0 and cmd[0] == 'ffmpeg':
                    self.command_executed.emit(' '.join(cmd))
                return original_run(cmd, *args, **kwargs)
                
            def patched_popen(cmd, *args, **kwargs):
                if isinstance(cmd, list) and len(cmd) > 0 and cmd[0] == 'ffmpeg':
                    self.command_executed.emit(' '.join(cmd))
                return original_popen(cmd, *args, **kwargs)
            
            # Monkey-patch print to capture console output
            import builtins
            original_print = builtins.print
            def patched_print(*args, **kwargs):
                message = ' '.join(str(arg) for arg in args)
                # Filter out progress messages and send to GUI
                if any(keyword in message for keyword in [
                    'Resume detected', 'Skipping', 'Converting', 'Using temporary',
                    'Using', 'CPU cores', 'Estimated', 'Progress:', '[OK]', 
                    'Successfully', 'files processed'
                ]):
                    self.progress_updated.emit(message, -1)  # -1 means no percentage update
                return original_print(*args, **kwargs)
            
            # Create a custom log handler to capture log messages
            class GuiLogHandler(logging.Handler):
                def __init__(self, thread):
                    super().__init__()
                    self.thread = thread
                    
                def emit(self, record):
                    if record.levelno >= logging.INFO:
                        message = self.format(record)
                        # Filter relevant messages
                        if any(keyword in message for keyword in [
                            'dependency check', 'validation', 'Resume detected',
                            'Concatenating', 'resource usage', 'memory',
                            'Adding', 'metadata', 'chapters', 'Successfully'
                        ]):
                            self.thread.progress_updated.emit(message, -1)
            
            # Add our custom handler to the root logger
            gui_handler = GuiLogHandler(self)
            gui_handler.setLevel(logging.INFO)
            logging.getLogger().addHandler(gui_handler)
            
            subprocess.run = patched_run
            subprocess.Popen = patched_popen
            builtins.print = patched_print
            
            try:
                result = self.processor.process_audiobook(**self.processing_args)
                if not self.is_cancelled:
                    self.processing_finished.emit(result)
            finally:
                # Restore original functions
                subprocess.run = original_run
                subprocess.Popen = original_popen
                builtins.print = original_print
                logging.getLogger().removeHandler(gui_handler)
                
        except Exception as e:
            if not self.is_cancelled:
                self.error_occurred.emit(str(e))
    
    def cancel(self):
        """Cancel the processing."""
        self.is_cancelled = True
        self.terminate()


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.processing_thread: Optional[ProcessingThread] = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("AudiobookMaker")
        # Set reasonable default window size
        self.setGeometry(100, 100, 1000, 700)
        self.setMinimumSize(800, 600)
        
        # Set window icon
        app_icon = get_application_icon()
        self.setWindowIcon(app_icon)
        # Also set application icon for all windows
        QApplication.instance().setWindowIcon(app_icon)
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create toolbar
        self.create_toolbar()
        
        # Create central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.input_tab = InputFilesTab()
        self.output_tab = OutputSettingsTab()
        self.cover_tab = CoverArtTab()
        self.chapters_tab = ChaptersTab()
        self.processing_tab = ProcessingTab()
        
        # Add tabs to widget
        self.tab_widget.addTab(self.input_tab, "Input Files")
        self.tab_widget.addTab(self.output_tab, "Output Settings")
        self.tab_widget.addTab(self.cover_tab, "Cover Art")
        self.tab_widget.addTab(self.chapters_tab, "Chapters")
        self.tab_widget.addTab(self.processing_tab, "Processing")
        
        # Connect signals
        self.processing_tab.start_requested.connect(self.start_processing)
        self.processing_tab.cancel_requested.connect(self.cancel_processing)
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
    def create_menu_bar(self):
        """Create the menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        open_action = QAction("&Open Files...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_files)
        file_menu.addAction(open_action)
        
        open_dir_action = QAction("Open &Directory...", self)
        open_dir_action.setShortcut("Ctrl+D")
        open_dir_action.triggered.connect(self.open_directory)
        file_menu.addAction(open_dir_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def create_toolbar(self):
        """Create the toolbar."""
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        add_files_action = QAction("Add Files", self)
        add_files_action.triggered.connect(self.open_files)
        toolbar.addAction(add_files_action)
        
        add_dir_action = QAction("Add Directory", self)
        add_dir_action.triggered.connect(self.open_directory)
        toolbar.addAction(add_dir_action)
        
        toolbar.addSeparator()
        
        start_action = QAction("Start Processing", self)
        start_action.triggered.connect(self.start_processing)
        toolbar.addAction(start_action)
        
    def open_files(self):
        """Open file dialog to select audio files."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Audio Files",
            "",
            "Audio Files (*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.m4b);;All Files (*)"
        )
        if files:
            self.input_tab.add_files(files)
            self.status_bar.showMessage(f"Added {len(files)} files")
            
    def open_directory(self):
        """Open dialog to select a directory."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Audio Directory"
        )
        if directory:
            self.input_tab.add_directory(directory)
            self.status_bar.showMessage(f"Added directory: {os.path.basename(directory)}")
            
    def start_processing(self):
        """Start audiobook processing."""
        # Validate inputs
        input_files = self.input_tab.get_files()
        if not input_files:
            QMessageBox.warning(self, "Warning", "No input files selected.")
            return
            
        # Get settings from tabs
        output_settings = self.output_tab.get_settings()
        cover_art_path = self.cover_tab.get_cover_path()
        chapter_mode = self.chapters_tab.get_chapter_mode()
        
        # Create processor with GUI mode enabled
        processor = AudiobookProcessor(
            bitrate=output_settings.get('bitrate', '128k'),
            gui_mode=True,
            quiet=True
        )
        
        # Prepare processing arguments
        processing_args = {
            'input_paths': input_files,
            'output_dir': output_settings.get('output_dir'),
            'output_name': output_settings.get('output_name'),
            'template': output_settings.get('template', '{title}'),
            'title': output_settings.get('title'),
            'author': output_settings.get('author'),
            'cover_art_path': cover_art_path,
            'chapter_titles_mode': chapter_mode
        }
        
        # Start processing in background thread
        self.processing_thread = ProcessingThread(processor, **processing_args)
        self.processing_thread.progress_updated.connect(self.processing_tab.update_progress)
        self.processing_thread.processing_finished.connect(self.on_processing_finished)
        self.processing_thread.error_occurred.connect(self.on_processing_error)
        self.processing_thread.command_executed.connect(self.processing_tab.add_command)
        
        self.processing_thread.start()
        
        # Update UI state
        self.processing_tab.set_processing_state(True)
        self.status_bar.showMessage("Processing audiobook...")
        self.tab_widget.setCurrentWidget(self.processing_tab)
        
    def cancel_processing(self):
        """Cancel ongoing processing."""
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.cancel()
            self.processing_thread.wait()
            self.processing_tab.set_processing_state(False)
            self.status_bar.showMessage("Processing cancelled")
            
    def on_processing_finished(self, result: ProcessingResult):
        """Handle processing completion."""
        self.processing_tab.set_processing_state(False)
        
        if result.success:
            self.status_bar.showMessage("Processing completed successfully")
            QMessageBox.information(
                self,
                "Success",
                f"Audiobook created successfully!\n\nOutput: {result.output_file}\n"
                f"Duration: {result.total_hours}h {result.total_minutes}m"
            )
        else:
            self.status_bar.showMessage("Processing failed")
            error_msg = result.error_message or "Unknown error occurred"
            if result.errors:
                error_msg += "\n\nErrors:\n" + "\n".join(result.errors[:5])
            QMessageBox.critical(self, "Error", error_msg)
            
    def on_processing_error(self, error_message: str):
        """Handle processing error."""
        self.processing_tab.set_processing_state(False)
        self.status_bar.showMessage("Processing error")
        QMessageBox.critical(self, "Error", f"Processing failed:\n{error_message}")
        
    def show_about(self):
        """Show about dialog."""
        about_dialog = QMessageBox(self)
        about_dialog.setWindowTitle("About AudiobookMaker")
        about_dialog.setWindowIcon(get_application_icon())
        about_dialog.setIconPixmap(get_application_icon().pixmap(64, 64))
        about_dialog.setTextFormat(Qt.TextFormat.RichText)
        about_dialog.setText(
            "<h3>AudiobookMaker GUI</h3>"
            "<p>Convert audio files to audiobook format with chapter support.</p>"
            "<p>Built with PyQt6 and FFmpeg</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Multi-format audio support</li>"
            "<li>Automatic chapter detection</li>"
            "<li>Cover art embedding</li>"
            "<li>Metadata preservation</li>"
            "</ul>"
        )
        about_dialog.exec()
        
    def closeEvent(self, event):
        """Handle window close event."""
        if self.processing_thread and self.processing_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Processing is in progress. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.processing_thread.cancel()
                self.processing_thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()