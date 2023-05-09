@echo off
pushd %~dp0
python AudiobookMakerPy.py %*
popd
pause