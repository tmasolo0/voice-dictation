@echo off
chcp 65001 >nul
setlocal

set PYTHON=python311\python.exe
set /p VERSION=<VERSION

:: Разбор аргументов: build.bat [installer]
set BUILD_INSTALLER=0
if /i "%~1"=="installer" set BUILD_INSTALLER=1

echo ============================================
echo  Voice Dictation v%VERSION% — Build
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

:: ===== PyInstaller =====
echo [INFO] Запуск PyInstaller...
%PYTHON% -m PyInstaller VoiceDictation.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] Сборка не удалась
    exit /b 1
)

:: Создание чистых папок для runtime-данных (убираем симлинки от dev-среды)
if exist "dist\VoiceDictation\models" rmdir /s /q "dist\VoiceDictation\models"
mkdir "dist\VoiceDictation\models"
if not exist "dist\VoiceDictation\logs" mkdir "dist\VoiceDictation\logs"

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
echo  EXE собран: dist\VoiceDictation\VoiceDictation.exe
echo ============================================

:: ===== Inno Setup installer (только с флагом "installer") =====
if %BUILD_INSTALLER%==0 goto :done

set ISCC=
where iscc >nul 2>nul
if not errorlevel 1 (
    set ISCC=iscc
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if defined ISCC (
    echo [INFO] Компиляция инсталлера...
    "%ISCC%" installer.iss
    if errorlevel 1 (
        echo [ERROR] Inno Setup: компиляция не удалась
        exit /b 1
    )
    echo.
    echo ============================================
    echo  Инсталлер: installer_output\VoiceDictation_Setup_%VERSION%.exe
    echo ============================================
) else (
    echo [WARN] Inno Setup не найден
    echo        Установите Inno Setup 6: https://jrsoftware.org/isinfo.php
)

:done
echo.
echo Готово!
pause
