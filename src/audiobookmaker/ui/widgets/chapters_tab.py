"""
Chapters tab for configuring chapter title generation.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox, QComboBox,
    QLabel, QTextEdit
)


class ChaptersTab(QWidget):
    """Tab for configuring chapter settings."""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Info label
        info_label = QLabel("Configure how chapter titles are generated from your audio files.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Chapter source group
        source_group = QGroupBox("Chapter Title Source")
        source_layout = QFormLayout(source_group)
        
        self.chapter_mode_combo = QComboBox()
        self.chapter_mode_combo.addItem("Auto (Smart extraction)", "auto")
        self.chapter_mode_combo.addItem("Use filenames as titles", "filename")
        self.chapter_mode_combo.addItem("Generic titles (Chapter 1, Chapter 2, etc.)", "generic")
        self.chapter_mode_combo.currentTextChanged.connect(self.on_mode_changed)
        
        source_layout.addRow("Chapter Source:", self.chapter_mode_combo)
        
        layout.addWidget(source_group)
        
        # Description group
        desc_group = QGroupBox("Mode Description")
        desc_layout = QVBoxLayout(desc_group)
        
        self.description_text = QTextEdit()
        self.description_text.setReadOnly(True)
        self.description_text.setMaximumHeight(150)
        desc_layout.addWidget(self.description_text)
        
        layout.addWidget(desc_group)
        
        # Examples group
        examples_group = QGroupBox("Examples")
        examples_layout = QVBoxLayout(examples_group)
        
        self.examples_text = QTextEdit()
        self.examples_text.setReadOnly(True)
        self.examples_text.setMaximumHeight(200)
        examples_layout.addWidget(self.examples_text)
        
        layout.addWidget(examples_group)
        
        layout.addStretch()
        
        # Set initial description
        self.on_mode_changed("Auto (Smart extraction)")
        
    def on_mode_changed(self, mode_text: str):
        """Update description when mode changes."""
        if "Auto" in mode_text:
            description = """
<b>Auto (Smart extraction)</b><br><br>
Automatically extracts meaningful chapter titles from filenames using intelligent parsing.
This mode attempts to:
<ul>
<li>Remove common prefixes like track numbers, "Chapter", etc.</li>
<li>Clean up formatting and spacing</li>
<li>Preserve meaningful parts of the filename</li>
<li>Handle various naming conventions automatically</li>
</ul>
This is the recommended mode for most audiobooks.
            """.strip()
            
            examples = """
<b>Example transformations:</b><br><br>
<tt>01 - Opening Credits & Introduction.mp3</tt> → <b>Opening Credits & Introduction</b><br>
<tt>02 - Chapter 1.mp3</tt> → <b>Chapter 1</b><br>
<tt>03-The Book of Blood.mp3</tt> → <b>The Book of Blood</b><br>
<tt>1.Intro Volume 1.m4a</tt> → <b>Intro Volume 1</b><br>
<tt>Chapter_05_The_Final_Battle.wav</tt> → <b>The Final Battle</b>
            """.strip()
            
        elif "filename" in mode_text:
            description = """
<b>Use filenames as titles</b><br><br>
Uses the original filename (without extension) as the chapter title.
This mode:
<ul>
<li>Preserves the exact filename structure</li>
<li>Removes only the file extension</li>
<li>Does not perform any cleanup or formatting</li>
<li>Useful when your filenames are already well-formatted</li>
</ul>
            """.strip()
            
            examples = """
<b>Example transformations:</b><br><br>
<tt>01 - Opening Credits & Introduction.mp3</tt> → <b>01 - Opening Credits & Introduction</b><br>
<tt>02 - Chapter 1.mp3</tt> → <b>02 - Chapter 1</b><br>
<tt>03-The Book of Blood.mp3</tt> → <b>03-The Book of Blood</b><br>
<tt>1.Intro Volume 1.m4a</tt> → <b>1.Intro Volume 1</b><br>
<tt>Chapter_05_The_Final_Battle.wav</tt> → <b>Chapter_05_The_Final_Battle</b>
            """.strip()
            
        else:  # generic
            description = """
<b>Generic titles</b><br><br>
Generates simple, numbered chapter titles regardless of the original filenames.
This mode:
<ul>
<li>Creates titles in the format "Chapter 1", "Chapter 2", etc.</li>
<li>Ignores all filename information</li>
<li>Provides consistent, clean chapter names</li>
<li>Useful when filenames are not descriptive or are poorly formatted</li>
</ul>
            """.strip()
            
            examples = """
<b>Example transformations:</b><br><br>
<tt>01 - Opening Credits & Introduction.mp3</tt> → <b>Chapter 1</b><br>
<tt>02 - Chapter 1.mp3</tt> → <b>Chapter 2</b><br>
<tt>03-The Book of Blood.mp3</tt> → <b>Chapter 3</b><br>
<tt>1.Intro Volume 1.m4a</tt> → <b>Chapter 4</b><br>
<tt>Chapter_05_The_Final_Battle.wav</tt> → <b>Chapter 5</b>
            """.strip()
            
        self.description_text.setHtml(description)
        self.examples_text.setHtml(examples)
        
    def get_chapter_mode(self) -> str:
        """Get the selected chapter mode."""
        return self.chapter_mode_combo.currentData()
        
    def set_chapter_mode(self, mode: str):
        """Set the chapter mode."""
        for i in range(self.chapter_mode_combo.count()):
            if self.chapter_mode_combo.itemData(i) == mode:
                self.chapter_mode_combo.setCurrentIndex(i)
                break