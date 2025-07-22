"""
Processing tab for showing progress and logs during audiobook creation.
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QProgressBar, QTextEdit,
    QPushButton, QLabel, QGroupBox, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class ProcessingTab(QWidget):
    """Tab for displaying processing progress and logs."""
    
    start_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.is_processing = False
        self.is_paused = False
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("Start Processing")
        self.start_btn.clicked.connect(self.on_start_clicked)
        button_layout.addWidget(self.start_btn)
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.on_pause_clicked)
        self.pause_btn.setEnabled(False)
        button_layout.addWidget(self.pause_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Log output group
        log_group = QGroupBox("Processing Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        # Use monospace font for log readability
        log_font = QFont("Consolas", 10)
        log_font.setFamily("Consolas, Monaco, 'Courier New', monospace")
        self.log_text.setFont(log_font)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #555;
            }
        """)
        log_layout.addWidget(self.log_text)
        
        # Log controls
        log_button_layout = QHBoxLayout()
        
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        log_button_layout.addWidget(self.clear_log_btn)
        
        self.save_log_btn = QPushButton("Save Log...")
        self.save_log_btn.clicked.connect(self.save_log)
        log_button_layout.addWidget(self.save_log_btn)
        
        log_button_layout.addStretch()
        
        log_layout.addLayout(log_button_layout)
        
        layout.addWidget(log_group)
        
        # Initial log message
        self.add_log_message("Ready to start processing. Configure your settings and click 'Start Processing'.")
        
    def on_start_clicked(self):
        """Handle start button click."""
        if not self.is_processing:
            self.start_requested.emit()
        elif self.is_paused:
            # Resume functionality (if implemented in the future)
            self.pause_requested.emit()
            
    def on_pause_clicked(self):
        """Handle pause button click."""
        self.pause_requested.emit()
        
    def on_cancel_clicked(self):
        """Handle cancel button click."""
        self.cancel_requested.emit()
        
    def set_processing_state(self, is_processing: bool):
        """Set the processing state and update UI accordingly."""
        self.is_processing = is_processing
        
        if is_processing:
            self.start_btn.setText("Processing...")
            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)  # Future feature
            self.cancel_btn.setEnabled(True)
            self.add_log_message("=== Processing Started ===")
        else:
            self.start_btn.setText("Start Processing")
            self.start_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
            self.is_paused = False
            
            if hasattr(self, '_processing_completed') and self._processing_completed:
                self.add_log_message("=== Processing Completed ===")
            else:
                self.add_log_message("=== Processing Stopped ===")
                
    def update_progress(self, message: str, percentage: int):
        """Update progress and add to log."""
        if percentage >= 0:
            # Normal progress update with percentage
            self.add_log_message(f"[{percentage}%] {message}")
        else:
            # Just a status message without percentage update
            self.add_log_message(message, "info")
        
    def add_log_message(self, message: str, message_type: str = "info"):
        """Add a message to the log."""
        import datetime
        
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Color coding based on message type
        color = "#ffffff"  # default white
        if message_type == "error":
            color = "#ff6b6b"
        elif message_type == "warning":
            color = "#ffd93d"
        elif message_type == "success":
            color = "#6bcf7f"
        elif "===" in message:
            color = "#4ecdc4"
            
        formatted_message = f'<span style="color: #888">[{timestamp}]</span> <span style="color: {color}">{message}</span>'
        
        self.log_text.append(formatted_message)
        
        # Auto-scroll to bottom
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
        
    def add_command(self, command: str):
        """Add an FFmpeg command to the log."""
        import datetime
        
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Format FFmpeg command with syntax highlighting
        formatted_command = f'<span style="color: #888">[{timestamp}]</span> <span style="color: #ffd93d; font-family: monospace;">$ {command}</span>'
        
        self.log_text.append(formatted_command)
        
        # Auto-scroll to bottom
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
        
    def clear_log(self):
        """Clear the log text."""
        self.log_text.clear()
        self.add_log_message("Log cleared.")
        
    def save_log(self):
        """Save the log to a file."""
        from PyQt6.QtWidgets import QFileDialog
        import datetime
        
        default_filename = f"audiobookmaker_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Log File",
            default_filename,
            "Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                # Get plain text version of the log
                plain_text = self.log_text.toPlainText()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(plain_text)
                self.add_log_message(f"Log saved to: {file_path}", "success")
            except Exception as e:
                self.add_log_message(f"Failed to save log: {str(e)}", "error")
                
    def mark_processing_completed(self):
        """Mark processing as completed successfully."""
        self._processing_completed = True