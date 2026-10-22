@echo off
cd /d "%~dp0"
py -3 servidor_windows.py
if errorlevel 1 (
 echo Comprueba que Python esta instalado y que funciona el comando py.
 pause
)
