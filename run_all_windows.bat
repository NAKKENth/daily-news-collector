@echo off
cd /d "%~dp0"
py -3 collector.py --scope all
pause
