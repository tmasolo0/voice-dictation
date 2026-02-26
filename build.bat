@echo off
chcp 65001 >nul
setlocal

set PYTHON=python311\python.exe

echo ============================================
echo  Voice Dictation — Build
echo ============================================

:: Проверка Python
if not exist "%PYTHON%" (
    echo [ERROR] %PYTHON% не найден
    exit /b 1
)

:: Установка PyInstaller если нет
%PYTHON% -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] Установка PyInstaller...
    %PYTHON% -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Не удалось установить PyInstaller
        exit /b 1
    )
)

:: Генерация иконки если нет
if not exist "assets\icon.ico" (
    echo [INFO] Генерация иконки...
    %PYTHON% build\generate_icon.py
    if errorlevel 1 (
        echo [WARN] Иконка не создана, сборка продолжится без неё
    )
)

:: Сборка
echo [INFO] Запуск PyInstaller...
%PYTHON% -m PyInstaller VoiceDictation.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] Сборка не удалась
    exit /b 1
)

:: Создание папок для runtime-данных
if not exist "dist\VoiceDictation\models" mkdir "dist\VoiceDictation\models"
if not exist "dist\VoiceDictation\logs"   mkdir "dist\VoiceDictation\logs"

:: Fallback: копирование dictionary.txt и dictionaries/ если datas не подхватил
if not exist "dist\VoiceDictation\_internal\dictionary.txt" (
    if exist "dictionary.txt" (
        echo [INFO] Fallback: копирование dictionary.txt
        copy /Y "dictionary.txt" "dist\VoiceDictation\_internal\" >nul
    )
)

if not exist "dist\VoiceDictation\_internal\dictionaries" (
    if exist "dictionaries" (
        echo [INFO] Fallback: копирование dictionaries/
        xcopy /E /I /Y "dictionaries" "dist\VoiceDictation\_internal\dictionaries" >nul
    )
)

echo.
echo ============================================
echo  Сборка завершена!
echo  dist\VoiceDictation\VoiceDictation.exe
echo ============================================
pause
