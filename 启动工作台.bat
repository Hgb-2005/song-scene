@echo off
chcp 65001 >nul
pushd "%~dp0"
python app.py --open
if errorlevel 1 pause
popd
