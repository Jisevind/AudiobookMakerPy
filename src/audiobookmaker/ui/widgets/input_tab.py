"""
Input Files tab for selecting and managing audio files.
"""

import os
from typing import List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QFileDialog, QMessageBox, QLabel, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from ...utils.file_utils import natural_keys


class FileListWidget(QListWidget):
    """Custom list widget with drag and drop support."""
    
    files_dropped = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            super().dragEnterEvent(event)
            
    def dragMoveEvent(self, event):
        """Handle drag move event."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            super().dragMoveEvent(event)
            
    def dropEvent(self, event: QDropEvent):
        """Handle drop event."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            paths = [url.toLocalFile() for url in urls]
            self.files_dropped.emit(paths)
            event.accept()
        else:
            super().dropEvent(event)


class InputFilesTab(QWidget):
    """Tab for managing input audio files."""
    
    def __init__(self):
        super().__init__()
        self.audio_files: List[str] = []
        self.supported_extensions = ('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.m4b')
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Info label
        info_label = QLabel("Select audio files or directories to process. Files will be processed in the order shown.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Splitter for file list and buttons
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # File list
        self.file_list = FileListWidget()
        self.file_list.files_dropped.connect(self.handle_dropped_files)
        splitter.addWidget(self.file_list)
        
        # Button panel
        button_widget = QWidget()
        button_layout = QVBoxLayout(button_widget)
        
        self.add_files_btn = QPushButton("Add Files...")
        self.add_files_btn.clicked.connect(self.add_files_dialog)
        button_layout.addWidget(self.add_files_btn)
        
        self.add_dir_btn = QPushButton("Add Directory...")
        self.add_dir_btn.clicked.connect(self.add_directory_dialog)
        button_layout.addWidget(self.add_dir_btn)
        
        button_layout.addWidget(QLabel())  # Spacer
        
        self.move_up_btn = QPushButton("Move Up")
        self.move_up_btn.clicked.connect(self.move_up)
        button_layout.addWidget(self.move_up_btn)
        
        self.move_down_btn = QPushButton("Move Down")
        self.move_down_btn.clicked.connect(self.move_down)
        button_layout.addWidget(self.move_down_btn)
        
        button_layout.addWidget(QLabel())  # Spacer
        
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self.remove_selected)
        button_layout.addWidget(self.remove_btn)
        
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self.clear_all)
        button_layout.addWidget(self.clear_btn)
        
        button_layout.addStretch()
        
        splitter.addWidget(button_widget)
        splitter.setSizes([600, 150])
        
        # Status label
        self.status_label = QLabel("No files selected")
        layout.addWidget(self.status_label)
        
        # Connect selection change
        self.file_list.itemSelectionChanged.connect(self.update_buttons)
        self.update_buttons()
        
    def add_files_dialog(self):
        """Open dialog to select audio files."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Audio Files",
            "",
            "Audio Files (*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.m4b);;All Files (*)"
        )
        if files:
            self.add_files(files)
            
    def add_directory_dialog(self):
        """Open dialog to select directory."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Audio Directory"
        )
        if directory:
            self.add_directory(directory)
            
    def add_files(self, files: List[str]):
        """Add files to the list."""
        valid_files = []
        for file_path in files:
            if os.path.isfile(file_path) and file_path.lower().endswith(self.supported_extensions):
                if file_path not in self.audio_files:
                    valid_files.append(file_path)
                    
        if valid_files:
            # Sort new files naturally
            valid_files.sort(key=natural_keys)
            self.audio_files.extend(valid_files)
            self.refresh_file_list()
            
    def add_directory(self, directory: str):
        """Add all audio files from directory."""
        if not os.path.isdir(directory):
            return
            
        audio_files = []
        for file_name in os.listdir(directory):
            file_path = os.path.join(directory, file_name)
            if os.path.isfile(file_path) and file_name.lower().endswith(self.supported_extensions):
                if file_path not in self.audio_files:
                    audio_files.append(file_path)
                    
        if audio_files:
            # Sort files naturally
            audio_files.sort(key=natural_keys)
            self.audio_files.extend(audio_files)
            self.refresh_file_list()
        else:
            QMessageBox.information(self, "Info", f"No audio files found in: {directory}")
            
    def handle_dropped_files(self, paths: List[str]):
        """Handle files/directories dropped onto the list."""
        files_to_add = []
        dirs_to_process = []
        
        for path in paths:
            if os.path.isfile(path):
                files_to_add.append(path)
            elif os.path.isdir(path):
                dirs_to_process.append(path)
                
        # Add individual files
        if files_to_add:
            self.add_files(files_to_add)
            
        # Add directories
        for directory in dirs_to_process:
            self.add_directory(directory)
            
    def refresh_file_list(self):
        """Refresh the file list display."""
        self.file_list.clear()
        for file_path in self.audio_files:
            item = QListWidgetItem(os.path.basename(file_path))
            item.setToolTip(file_path)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            self.file_list.addItem(item)
            
        self.update_status()
        self.update_buttons()
        
    def move_up(self):
        """Move selected item up."""
        current_row = self.file_list.currentRow()
        if current_row > 0:
            # Swap in the list
            self.audio_files[current_row], self.audio_files[current_row - 1] = \
                self.audio_files[current_row - 1], self.audio_files[current_row]
            self.refresh_file_list()
            self.file_list.setCurrentRow(current_row - 1)
            
    def move_down(self):
        """Move selected item down."""
        current_row = self.file_list.currentRow()
        if 0 <= current_row < len(self.audio_files) - 1:
            # Swap in the list
            self.audio_files[current_row], self.audio_files[current_row + 1] = \
                self.audio_files[current_row + 1], self.audio_files[current_row]
            self.refresh_file_list()
            self.file_list.setCurrentRow(current_row + 1)
            
    def remove_selected(self):
        """Remove selected items."""
        current_row = self.file_list.currentRow()
        if current_row >= 0:
            del self.audio_files[current_row]
            self.refresh_file_list()
            
    def clear_all(self):
        """Clear all files."""
        if self.audio_files:
            reply = QMessageBox.question(
                self,
                "Confirm Clear",
                "Remove all files from the list?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.audio_files.clear()
                self.refresh_file_list()
                
    def update_buttons(self):
        """Update button states based on selection."""
        current_row = self.file_list.currentRow()
        has_selection = current_row >= 0
        has_files = len(self.audio_files) > 0
        
        self.move_up_btn.setEnabled(has_selection and current_row > 0)
        self.move_down_btn.setEnabled(has_selection and current_row < len(self.audio_files) - 1)
        self.remove_btn.setEnabled(has_selection)
        self.clear_btn.setEnabled(has_files)
        
    def update_status(self):
        """Update status label."""
        count = len(self.audio_files)
        if count == 0:
            self.status_label.setText("No files selected")
        elif count == 1:
            self.status_label.setText("1 file selected")
        else:
            self.status_label.setText(f"{count} files selected")
            
    def get_files(self) -> List[str]:
        """Get the list of selected files."""
        return self.audio_files.copy()