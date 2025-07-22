"""
Output Settings tab for configuring audiobook metadata and output options.
"""

import os
from typing import Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QComboBox, QSpinBox, QPushButton, QFileDialog,
    QLabel, QTextEdit
)
from PyQt6.QtCore import Qt


class OutputSettingsTab(QWidget):
    """Tab for configuring output settings."""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Metadata group
        metadata_group = QGroupBox("Metadata")
        metadata_layout = QFormLayout(metadata_group)
        
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Leave empty for auto-detection")
        metadata_layout.addRow("Title:", self.title_edit)
        
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText("Leave empty for auto-detection")
        metadata_layout.addRow("Author:", self.author_edit)
        
        self.year_edit = QLineEdit()
        self.year_edit.setPlaceholderText("e.g., 2023")
        metadata_layout.addRow("Year:", self.year_edit)
        
        layout.addWidget(metadata_group)
        
        # Output Path group
        output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout(output_group)
        
        # Output directory
        dir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Leave empty to use input directory")
        dir_layout.addWidget(QLabel("Output Directory:"))
        dir_layout.addWidget(self.output_dir_edit)
        
        self.browse_dir_btn = QPushButton("Browse...")
        self.browse_dir_btn.clicked.connect(self.browse_output_directory)
        dir_layout.addWidget(self.browse_dir_btn)
        
        output_layout.addLayout(dir_layout)
        
        # Custom filename
        filename_layout = QHBoxLayout()
        self.output_name_edit = QLineEdit()
        self.output_name_edit.setPlaceholderText("Leave empty for template-based naming")
        filename_layout.addWidget(QLabel("Custom Filename:"))
        filename_layout.addWidget(self.output_name_edit)
        
        output_layout.addLayout(filename_layout)
        
        # Filename template
        template_layout = QVBoxLayout()
        template_layout.addWidget(QLabel("Filename Template:"))
        self.template_edit = QLineEdit("{title}")
        template_layout.addWidget(self.template_edit)
        
        template_help = QLabel("Available variables: {title}, {author}, {album}, {year}")
        template_help.setStyleSheet("color: gray; font-size: 10px;")
        template_layout.addWidget(template_help)
        
        output_layout.addLayout(template_layout)
        
        layout.addWidget(output_group)
        
        # Audio Quality group
        quality_group = QGroupBox("Audio Quality")
        quality_layout = QFormLayout(quality_group)
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Low (64k)", "Medium (128k)", "High (256k)", "Very High (320k)", "Custom"])
        self.quality_combo.setCurrentText("Medium (128k)")
        self.quality_combo.currentTextChanged.connect(self.on_quality_changed)
        quality_layout.addRow("Quality Preset:", self.quality_combo)
        
        self.custom_bitrate_edit = QLineEdit()
        self.custom_bitrate_edit.setPlaceholderText("e.g., 192k")
        self.custom_bitrate_edit.setEnabled(False)
        quality_layout.addRow("Custom Bitrate:", self.custom_bitrate_edit)
        
        layout.addWidget(quality_group)
        
        # Advanced Options group (optional)
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QFormLayout(advanced_group)
        
        self.cores_spin = QSpinBox()
        self.cores_spin.setMinimum(1)
        self.cores_spin.setMaximum(16)
        self.cores_spin.setValue(os.cpu_count() or 4)
        self.cores_spin.setSpecialValueText("Auto")
        advanced_layout.addRow("CPU Cores:", self.cores_spin)
        
        layout.addWidget(advanced_group)
        
        layout.addStretch()
        
    def browse_output_directory(self):
        """Browse for output directory."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory"
        )
        if directory:
            self.output_dir_edit.setText(directory)
            
    def on_quality_changed(self, quality_text: str):
        """Handle quality preset change."""
        is_custom = quality_text == "Custom"
        self.custom_bitrate_edit.setEnabled(is_custom)
        if is_custom:
            self.custom_bitrate_edit.setFocus()
            
    def get_bitrate(self) -> str:
        """Get the selected bitrate."""
        quality_text = self.quality_combo.currentText()
        if quality_text == "Custom":
            custom_bitrate = self.custom_bitrate_edit.text().strip()
            return custom_bitrate if custom_bitrate else "128k"
        elif "64k" in quality_text:
            return "64k"
        elif "128k" in quality_text:
            return "128k"
        elif "256k" in quality_text:
            return "256k"
        elif "320k" in quality_text:
            return "320k"
        else:
            return "128k"
            
    def get_settings(self) -> Dict[str, Any]:
        """Get all output settings."""
        settings = {
            'title': self.title_edit.text().strip() or None,
            'author': self.author_edit.text().strip() or None,
            'year': self.year_edit.text().strip() or None,
            'output_dir': self.output_dir_edit.text().strip() or None,
            'output_name': self.output_name_edit.text().strip() or None,
            'template': self.template_edit.text().strip() or "{title}",
            'bitrate': self.get_bitrate(),
            'cores': self.cores_spin.value() if self.cores_spin.value() > 1 else None
        }
        return settings
        
    def set_settings(self, settings: Dict[str, Any]):
        """Set settings from dictionary."""
        if 'title' in settings and settings['title']:
            self.title_edit.setText(settings['title'])
        if 'author' in settings and settings['author']:
            self.author_edit.setText(settings['author'])
        if 'year' in settings and settings['year']:
            self.year_edit.setText(str(settings['year']))
        if 'output_dir' in settings and settings['output_dir']:
            self.output_dir_edit.setText(settings['output_dir'])
        if 'output_name' in settings and settings['output_name']:
            self.output_name_edit.setText(settings['output_name'])
        if 'template' in settings and settings['template']:
            self.template_edit.setText(settings['template'])
        if 'cores' in settings and settings['cores']:
            self.cores_spin.setValue(settings['cores'])