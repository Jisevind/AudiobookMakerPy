@echo off
echo Building AudiobookMaker GUI Executable...
echo.

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Run the build script
python build_executable.py

echo.
echo Build completed! Check the dist/ folder for your executable.
pause