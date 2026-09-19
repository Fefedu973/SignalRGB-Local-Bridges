@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Installer-client.ps1"
if errorlevel 1 pause
