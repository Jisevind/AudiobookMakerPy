# Plan: Evolving AudiobookMakerPy with a Hybrid Approach

## 1. Executive Summary

This document outlines a strategic plan to refactor the `AudiobookMakerPy` project. The current implementation is a functional, monolithic script that depends on two external command-line tools: `ffmpeg` and `MP4Box`.

The proposed **hybrid approach** will modernize the codebase by integrating powerful Python libraries to simplify the code, remove one of the external dependencies, and provide greater control over metadata.

The core of this plan is to:
1.  **Retain `ffmpeg`** as the core audio conversion engine due to its unmatched power and format support.
2.  **Integrate `pydub`** as a high-level wrapper around `ffmpeg`. This will replace complex `subprocess` calls with a simple, Pythonic API, making the audio manipulation code cleaner and easier to maintain.
3.  **Integrate `mutagen`** to handle all metadata operations. This will replace the `MP4Box` dependency and the manual creation of chapter files, allowing for powerful, in-memory manipulation of chapters, cover art, and other tags.

This evolution will be executed in phases to ensure a smooth transition with clear, incremental benefits at each stage.

---

## 2. Project Dependencies

This plan introduces two new Python dependencies. A `requirements.txt` file should be created to manage them:

```
# requirements.txt
pydub
mutagen
```

The `README.md` file must be updated to instruct users to install these packages using `pip install -r requirements.txt`, while still mentioning the need for a system-level `ffmpeg` installation.

---

## 3. Phased Implementation Plan

### **Phase 1: Integrate Pydub & Refactor Audio Processing**

*Goal: Replace direct `subprocess` calls to `ffmpeg` with `pydub` for cleaner code and easier audio manipulation.*

1.  **Refactor Audio Property Functions:**
    *   The `get_audio_duration` and `get_audio_properties` functions can be simplified or replaced. `pydub`'s `AudioSegment` object provides this information directly when a file is loaded.
    *   **Action:** Create a new function `load_audio_segment(file_path)` that returns a `pydub.AudioSegment` object. This object will contain duration (`len(segment)`), channels (`segment.channels`), frame rate (`segment.frame_rate`), etc.

2.  **Refactor Conversion Logic:**
    *   The `convert_to_aac` function will be replaced.
    *   **Action:** Use `pydub`'s `export()` method. The logic will look something like this:
        ```python
        from pydub import AudioSegment
        
        def convert_file_for_concatenation(input_file, output_format="ipod"):
            audio = AudioSegment.from_file(input_file)
            # Export to a temporary file in a consistent format for concatenation
            temp_file = "some_temp_file.m4a"
            audio.export(temp_file, format=output_format, bitrate="128k") # M4B is ipod format
            return temp_file, len(audio) # Return path and duration in ms
        ```

3.  **Update Main Processing Loop:**
    *   The `ProcessPoolExecutor` will now call the new `convert_file_for_concatenation` function for each input file.
    *   This loop will collect the paths to the temporary converted files and their durations, which will be needed for concatenation and chapter creation.

### **Phase 2: Concatenation Strategy**

*Goal: Combine the individually converted audio files into a single audiobook file.*

1.  **Implement Concatenation with Pydub:**
    *   `pydub` allows for simple concatenation by "adding" `AudioSegment` objects together.
    *   **Action:**
        1.  Load all the temporary files created in Phase 1 into a list of `AudioSegment` objects.
        2.  Combine them in a loop:
            ```python
            from pydub import AudioSegment
            
            final_audio = AudioSegment.empty()
            for temp_file in temp_files:
                final_audio += AudioSegment.from_file(temp_file)
            ```
        3.  Export the `final_audio` object to the final output `.m4b` path.

### **Phase 3: Replace MP4Box with Mutagen for Metadata**

*Goal: Remove the `MP4Box` dependency and gain fine-grained control over metadata.*

1.  **Remove Old Metadata Code:**
    *   Delete the `create_metadata_file` function.
    *   Delete the `copy_metadata` function.
    *   Remove the `MP4Box` subprocess call.

2.  **Implement `mutagen` Metadata Function:**
    *   **Action:** Create a new function `add_metadata_to_book(output_file, file_durations, title="Audiobook", author="Author")`.
    *   This function will:
        1.  Open the final `.m4b` file using `mutagen.mp4.MP4()`.
        2.  Programmatically create and add chapter markers. The `file_durations` list collected in Phase 1 is crucial here. You will iterate through the durations, calculating the start time of each chapter.
        3.  Add other essential metadata like title, artist/author, and album.
        4.  (Future Enhancement) Add support for embedding cover art.
        5.  Save the changes to the file.

### **Phase 4: Finalizing the Workflow & User Experience**

*Goal: Tie all the new pieces together and improve the user-facing experience.*

1.  **Update the Main Function:**
    *   The main execution flow will be updated to orchestrate the new, phased approach:
        1.  Validate input files.
        2.  **Phase 1:** Convert all files in parallel, collecting temp file paths and durations.
        3.  **Phase 2:** Concatenate all temp files into a single `.m4b` file.
        4.  **Phase 3:** Use `mutagen` to add chapters and metadata to the new `.m4b` file.
        5.  Clean up all temporary files.

2.  **Add Dependency Checking:**
    *   **Action:** At the start of the script, add a function that checks if `ffmpeg` is accessible. This can be done by running `ffmpeg -version` in a subprocess and checking the return code. If it fails, exit with a user-friendly error message.

3.  **Update Documentation:**
    *   Update `README.md` to reflect the new `requirements.txt` and the simplified dependency list (only `ffmpeg` is required externally).
    *   Remove all mentions of `MP4Box`.

## 4. Success Metrics

*   The `MP4Box` dependency is fully removed from the project.
*   All `subprocess` calls related to `ffmpeg` are replaced by `p_ydub` API calls.
*   The script can successfully create an `.m4b` audiobook with accurate chapters and metadata.
*   The codebase is more modular and easier to read.
*   The project has a `requirements.txt` file, adopting standard Python dependency management.
