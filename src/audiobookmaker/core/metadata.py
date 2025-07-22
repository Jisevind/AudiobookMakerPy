"""
Metadata extraction and writing functionality.
"""

import os
import subprocess
import logging
import json
import re
from typing import Dict, List, Any, Optional, Tuple

from ..exceptions import MetadataError


def _get_subprocess_startupinfo():
    """Get startupinfo to hide console windows on Windows."""
    startupinfo = None
    creationflags = 0
    if os.name == 'nt':  # Windows
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        # Additional flag to prevent console window creation
        creationflags = subprocess.CREATE_NO_WINDOW
    return startupinfo, creationflags


class MetadataExtractor:
    """Handles metadata extraction from audio files."""
    
    def __init__(self):
        """Initialize the metadata extractor."""
        pass
    
    def extract_comprehensive_metadata(self, input_files: List[str]) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from input files.
        
        Args:
            input_files: List of input file paths
            
        Returns:
            Dict containing comprehensive metadata
        """
        if not input_files:
            return {}
        
        # Use first file for main metadata
        first_file = input_files[0]
        metadata = self._extract_metadata_from_source(first_file)
        
        # Generate chapter titles from filenames
        chapter_titles = []
        for file_path in input_files:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            # Clean up the filename for chapter titles
            cleaned = re.sub(r'^\d+\s*[-:.)]\s*', '', base_name)
            cleaned = re.sub(r'^(Chapter|Track|Part)\s*\d+\s*[-:.)]\s*', '', cleaned, flags=re.IGNORECASE)
            if not cleaned.strip():
                cleaned = base_name
            chapter_titles.append(cleaned.strip())
        
        return {
            'title': metadata.get('title', os.path.basename(os.path.dirname(first_file))),
            'author': metadata.get('artist', 'Unknown Author'),
            'album': metadata.get('album', os.path.basename(os.path.dirname(first_file))),
            'year': metadata.get('date', ''),
            'chapter_titles': chapter_titles,
            'source_metadata': metadata
        }
    
    def _extract_metadata_from_source(self, input_file: str) -> Dict[str, Any]:
        """
        Extract metadata from source audio file using FFprobe.
        
        Args:
            input_file: Path to input audio file
            
        Returns:
            Dict containing metadata
        """
        try:
            ffprobe_command = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                '-show_format', input_file
            ]
            startupinfo, creationflags = _get_subprocess_startupinfo()
            result = subprocess.run(
                ffprobe_command, 
                capture_output=True, 
                text=True, 
                check=True,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            
            data = json.loads(result.stdout)
            format_tags = data.get('format', {}).get('tags', {})
            
            # Normalize tag names (different formats use different case)
            normalized = {}
            for key, value in format_tags.items():
                key_lower = key.lower()
                if key_lower in ['title', 'album', 'artist', 'album_artist', 'albumartist', 
                               'date', 'year', 'genre', 'comment', 'description']:
                    normalized[key_lower.replace('albumartist', 'album_artist')] = value
                    
            return normalized
            
        except Exception as e:
            logging.warning(f'Could not extract metadata from {input_file}: {str(e)}')
            return {}
    
    def extract_chapter_name_from_filename(self, filename: str) -> str:
        """
        Extract a smart chapter name from the filename.
        
        Args:
            filename: The input filename
            
        Returns:
            str: A cleaned chapter name
        """
        # Remove file extension and path
        base_name = os.path.splitext(os.path.basename(filename))[0]
        
        # Remove common prefixes like track numbers
        # Remove patterns like "01 - ", "Chapter 1 - ", "Track 01: ", etc.
        cleaned = re.sub(r'^\d+\s*[-:.)]\s*', '', base_name)
        cleaned = re.sub(r'^(Chapter|Track|Part)\s*\d+\s*[-:.)]\s*', '', cleaned, flags=re.IGNORECASE)
        
        # If nothing left after cleaning, use original
        if not cleaned.strip():
            cleaned = base_name
        
        return cleaned.strip()


class MetadataWriter:
    """Handles metadata writing to audiobook files."""
    
    def __init__(self):
        """Initialize the metadata writer."""
        # Check for mutagen availability
        try:
            from mutagen.mp4 import MP4, MP4Cover
            self.mutagen_available = True
        except ImportError:
            self.mutagen_available = False
            logging.warning("Mutagen not available - enhanced metadata features will be limited")
    
    def add_metadata_to_audiobook(self, output_file: str, input_files: List[str], 
                                 durations: List[int], metadata: Optional[Dict[str, Any]] = None,
                                 cover_art_path: Optional[str] = None, 
                                 chapter_titles: Optional[List[str]] = None):
        """
        Add enhanced metadata to the M4B audiobook file using mutagen.
        
        Args:
            output_file: Path to the output M4B file
            input_files: List of input file paths
            durations: List of durations in milliseconds
            metadata: Comprehensive metadata from smart extraction
            cover_art_path: Path to cover art image file
            chapter_titles: Smart chapter titles from extraction
            
        Raises:
            MetadataError: If metadata processing fails
        """
        try:
            logging.info(f'Adding enhanced metadata to {output_file}')
            
            # Check if mutagen is available
            if not self.mutagen_available:
                logging.warning("Mutagen not available - skipping enhanced metadata")
                return
            
            from mutagen.mp4 import MP4, MP4Cover
            
            # Open the M4B file with mutagen
            audiofile = MP4(output_file)
            
            # Add basic metadata
            self._add_basic_metadata(audiofile, metadata, input_files)
            
            # Add cover art if provided
            if cover_art_path:
                self._add_cover_art(audiofile, cover_art_path)
            
            # Add chapter information
            if chapter_titles:
                chapters = self._create_smart_chapters_for_mutagen(input_files, durations, chapter_titles)
            else:
                chapters = self._create_chapters_for_mutagen(input_files, durations)
            
            self._add_chapters_to_file(audiofile, chapters)
            
            # Save the metadata
            audiofile.save()
            
            # Log success
            chapter_count = len(chapters)
            features_added = []
            if cover_art_path:
                features_added.append("cover art")
            if chapter_titles:
                features_added.append("smart chapter titles")
            if metadata and metadata.get('source_metadata'):
                features_added.append("inherited metadata")
                
            features_str = f" with {', '.join(features_added)}" if features_added else ""
            logging.info(f'Successfully added enhanced metadata and {chapter_count} chapters{features_str} to {output_file}')
            
        except Exception as e:
            logging.error(f'Error adding enhanced metadata to {output_file}: {str(e)}')
            raise MetadataError(f"Adding enhanced metadata failed: {str(e)}", output_file) from e
    
    def _add_basic_metadata(self, audiofile, metadata: Optional[Dict[str, Any]], input_files: List[str]):
        """Add basic metadata to the audiobook file."""
        if metadata:
            audiofile['\xa9nam'] = metadata.get('title', 'Audiobook')
            audiofile['\xa9alb'] = metadata.get('album', metadata.get('title', 'Audiobook'))
            audiofile['\xa9ART'] = metadata.get('author', 'Unknown Author')
            audiofile['aART'] = metadata.get('author', 'Unknown Author')  # Album artist
            
            if metadata.get('year'):
                audiofile['\xa9day'] = metadata['year']
                
            # Preserve additional metadata from source files
            source_metadata = metadata.get('source_metadata', {})
            
            # Copy genre if available
            for genre_tag in ['\xa9gen', 'TCON', 'GENRE']:
                if genre_tag in source_metadata:
                    audiofile['\xa9gen'] = str(source_metadata[genre_tag][0]) if isinstance(source_metadata[genre_tag], list) else str(source_metadata[genre_tag])
                    break
                    
            # Copy comment/description if available  
            for comment_tag in ['\xa9cmt', 'COMM::eng', 'COMMENT']:
                if comment_tag in source_metadata:
                    comment_value = source_metadata[comment_tag]
                    if isinstance(comment_value, list) and comment_value:
                        audiofile['\xa9cmt'] = str(comment_value[0])
                    elif comment_value:
                        audiofile['\xa9cmt'] = str(comment_value)
                    break
        else:
            # Fallback to legacy metadata extraction
            extractor = MetadataExtractor()
            first_file_metadata = extractor._extract_metadata_from_source(input_files[0])
            
            audiofile['\xa9nam'] = first_file_metadata.get('album', os.path.basename(os.path.dirname(input_files[0])))
            audiofile['\xa9alb'] = first_file_metadata.get('album', audiofile['\xa9nam'])
            audiofile['\xa9ART'] = first_file_metadata.get('artist', 'Unknown Author')
            audiofile['aART'] = first_file_metadata.get('album_artist', audiofile['\xa9ART'])
            
            if first_file_metadata.get('date'):
                audiofile['\xa9day'] = first_file_metadata['date']
            if first_file_metadata.get('genre'):
                audiofile['\xa9gen'] = first_file_metadata['genre']
            if first_file_metadata.get('comment'):
                audiofile['\xa9cmt'] = first_file_metadata['comment']
        
        # Set as audiobook
        audiofile['stik'] = [2]  # Audiobook media type
    
    def _add_cover_art(self, audiofile, cover_art_path: str):
        """Add cover art to the audiobook file."""
        try:
            from mutagen.mp4 import MP4Cover
            
            with open(cover_art_path, 'rb') as cover_file:
                cover_data = cover_file.read()
                
            # Determine cover format
            cover_ext = os.path.splitext(cover_art_path)[1].lower()
            if cover_ext in ['.jpg', '.jpeg']:
                cover_format = MP4Cover.FORMAT_JPEG
            elif cover_ext == '.png':
                cover_format = MP4Cover.FORMAT_PNG
            else:
                raise MetadataError(f"Unsupported cover art format: {cover_ext}", cover_art_path)
            
            # Create MP4Cover object and add to file
            cover = MP4Cover(cover_data, cover_format)
            audiofile['covr'] = [cover]
            logging.info(f'Added cover art from {cover_art_path} ({len(cover_data)} bytes)')
            
        except Exception as e:
            logging.warning(f'Failed to add cover art: {e}')
            # Continue without cover art rather than failing
    
    def _create_chapters_for_mutagen(self, input_files: List[str], durations: List[int]) -> List[Tuple[int, str]]:
        """
        Create chapter data for mutagen metadata handling.
        
        Args:
            input_files: List of input file paths
            durations: List of durations in milliseconds
            
        Returns:
            List of tuples (start_time_ms, title) for each chapter
        """
        chapters = []
        start_time = 0
        
        extractor = MetadataExtractor()
        
        for i, (input_file, duration) in enumerate(zip(input_files, durations)):
            # Extract smart chapter name from filename
            chapter_name = extractor.extract_chapter_name_from_filename(input_file)
            
            # Fallback to generic name if extraction fails
            if not chapter_name or len(chapter_name) < 2:
                chapter_name = f"Chapter {i + 1}"
            
            chapters.append((start_time, chapter_name))
            start_time += duration
        
        logging.info(f'Created {len(chapters)} chapters for metadata')
        return chapters
    
    def _create_smart_chapters_for_mutagen(self, input_files: List[str], durations: List[int], 
                                          chapter_titles: List[str]) -> List[Dict[str, Any]]:
        """
        Create chapter information using smart extracted titles.
        
        Args:
            input_files: List of input file paths
            durations: List of durations in milliseconds
            chapter_titles: Smart extracted chapter titles
            
        Returns:
            List of chapter information for mutagen
        """
        if len(input_files) != len(durations) or len(input_files) != len(chapter_titles):
            raise ValueError("Mismatch between number of files, durations, and chapter titles")
        
        chapters = []
        current_time = 0
        
        for i, (input_file, duration, title) in enumerate(zip(input_files, durations, chapter_titles)):
            chapter = {
                'start_time': current_time,
                'title': title
            }
            chapters.append(chapter)
            current_time += duration
            
            logging.debug(f'Smart chapter {i+1}: "{title}" at {current_time}ms')
        
        logging.info(f'Created {len(chapters)} smart chapters with intelligent titles')
        return chapters
    
    def _add_chapters_to_file(self, audiofile, chapters: List[Any]):
        """
        Add chapter markers to the M4B file using mutagen.
        
        Args:
            audiofile: Mutagen MP4 file object
            chapters: List of chapter information
        """
        if not chapters:
            return
            
        try:
            # Store chapter information for compatibility with audiobook players
            chapter_titles = []
            
            # Handle different chapter formats
            for chapter in chapters:
                if isinstance(chapter, tuple):
                    # Format: (start_time_ms, title)
                    _, title = chapter
                    chapter_titles.append(title)
                elif isinstance(chapter, dict):
                    # Format: {'start_time': ms, 'title': str}
                    chapter_titles.append(chapter['title'])
                else:
                    chapter_titles.append(str(chapter))
            
            # Add chapter titles (this works with most audiobook players)
            if chapter_titles:
                # Store as description/summary with chapter info
                chapter_summary = f"Audiobook with {len(chapters)} chapters:\n" + "\n".join(
                    f"{i+1}. {title}" for i, title in enumerate(chapter_titles)
                )
                audiofile['desc'] = chapter_summary
                
                # Set track number to indicate chapters
                audiofile['trkn'] = [(len(chapters), len(chapters))]
                
                logging.info(f'Added {len(chapters)} chapters to metadata')
                
        except Exception as e:
            logging.warning(f'Could not add chapters to file: {str(e)}')
            # Continue without chapters rather than failing completely