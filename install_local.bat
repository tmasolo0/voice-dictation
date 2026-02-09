@echo off
cd /d "%~dp0"

set PYTHON=.\python311\python.exe

echo ========================================
echo Voice Dictation - Установка зависимостей
echo ========================================
echo.

%PYTHON% -m pip install PyQt6 pywin32 faster-whisper sounddevice numpy keyboard pyperclip pyautogui

echo.
echo ========================================
echo Готово!
echo ========================================
echo.
echo Запуск:
echo   - "Dictation.vbs" — без консоли (production)
echo   - "Dictation.bat" — с консолью (отладка)
echo.
echo При первом запуске модель скачается автоматически.
echo ========================================
pause
