"""
Cover Art tab for selecting and previewing audiobook cover art.
"""

import os
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent


class CoverPreviewLabel(QLabel):
    """Label widget that supports drag and drop for cover art."""
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 5px;
                background-color: #f9f9f9;
                min-height: 300px;
                font-size: 14px;
                color: #666;
            }
            QLabel:hover {
                background-color: #f0f0f0;
            }
        """)
        self.setText("Drop cover art image here\nor use the Browse button\n\nSupported formats: JPEG, PNG")
        self.cover_path: Optional[str] = None
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                file_path = urls[0].toLocalFile()
                if self.is_supported_image(file_path):
                    event.accept()
                    return
        event.ignore()
        
    def dragMoveEvent(self, event):
        """Handle drag move event."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
            
    def dropEvent(self, event: QDropEvent):
        """Handle drop event."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                file_path = urls[0].toLocalFile()
                if self.is_supported_image(file_path):
                    self.load_cover_image(file_path)
                    event.accept()
                    return
        event.ignore()
        
    def is_supported_image(self, file_path: str) -> bool:
        """Check if the file is a supported image format."""
        return file_path.lower().endswith(('.jpg', '.jpeg', '.png'))
        
    def load_cover_image(self, file_path: str):
        """Load and display cover image."""
        if not os.path.isfile(file_path):
            QMessageBox.warning(self.parent(), "Error", f"File not found: {file_path}")
            return
            
        if not self.is_supported_image(file_path):
            QMessageBox.warning(
                self.parent(), 
                "Unsupported Format", 
                "Only JPEG and PNG images are supported for cover art."
            )
            return
            
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QMessageBox.warning(self.parent(), "Error", "Failed to load image.")
            return
            
        # Scale image to fit while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(
            300, 300,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.setPixmap(scaled_pixmap)
        self.cover_path = file_path
        
    def clear_cover(self):
        """Clear the current cover art."""
        self.clear()
        self.setText("Drop cover art image here\nor use the Browse button\n\nSupported formats: JPEG, PNG")
        self.cover_path = None
        
    def get_cover_path(self) -> Optional[str]:
        """Get the path to the current cover art."""
        return self.cover_path


class CoverArtTab(QWidget):
    """Tab for managing cover art."""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Info label
        info_label = QLabel("Select cover art for your audiobook. This will be embedded in the final M4B file.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Cover art group
        cover_group = QGroupBox("Cover Art Preview")
        cover_layout = QVBoxLayout(cover_group)
        
        # Preview area
        self.cover_preview = CoverPreviewLabel()
        self.cover_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cover_layout.addWidget(self.cover_preview)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_cover_art)
        button_layout.addWidget(self.browse_btn)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_cover_art)
        button_layout.addWidget(self.clear_btn)
        
        button_layout.addStretch()
        
        cover_layout.addLayout(button_layout)
        
        # File info
        self.file_info_label = QLabel("")
        self.file_info_label.setStyleSheet("color: #666; font-size: 11px;")
        cover_layout.addWidget(self.file_info_label)
        
        layout.addWidget(cover_group)
        
        # Tips
        tips_group = QGroupBox("Tips")
        tips_layout = QVBoxLayout(tips_group)
        
        tips_text = QLabel("""
• Use high-resolution images (at least 600x600 pixels) for best quality
• Square images work best for audiobook covers
• JPEG and PNG formats are supported
• The cover art will be embedded in the final audiobook file
• You can drag and drop an image directly onto the preview area
        """.strip())
        tips_text.setWordWrap(True)
        tips_text.setStyleSheet("color: #666;")
        tips_layout.addWidget(tips_text)
        
        layout.addWidget(tips_group)
        
        layout.addStretch()
        
    def browse_cover_art(self):
        """Browse for cover art image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Cover Art",
            "",
            "Image Files (*.jpg *.jpeg *.png);;All Files (*)"
        )
        if file_path:
            self.cover_preview.load_cover_image(file_path)
            self.update_file_info()
            
    def clear_cover_art(self):
        """Clear the current cover art."""
        self.cover_preview.clear_cover()
        self.update_file_info()
        
    def update_file_info(self):
        """Update the file info label."""
        cover_path = self.cover_preview.get_cover_path()
        if cover_path:
            file_name = os.path.basename(cover_path)
            file_size = os.path.getsize(cover_path)
            
            # Format file size
            if file_size < 1024:
                size_str = f"{file_size} bytes"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
                
            # Get image dimensions
            pixmap = QPixmap(cover_path)
            if not pixmap.isNull():
                width = pixmap.width()
                height = pixmap.height()
                self.file_info_label.setText(f"{file_name} • {width}×{height} • {size_str}")
            else:
                self.file_info_label.setText(f"{file_name} • {size_str}")
        else:
            self.file_info_label.setText("")
            
    def get_cover_path(self) -> Optional[str]:
        """Get the path to the selected cover art."""
        return self.cover_preview.get_cover_path()
        
    def set_cover_path(self, file_path: Optional[str]):
        """Set the cover art path."""
        if file_path and os.path.isfile(file_path):
            self.cover_preview.load_cover_image(file_path)
            self.update_file_info()
        else:
            self.clear_cover_art()