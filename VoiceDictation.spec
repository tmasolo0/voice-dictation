# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Voice Dictation (onedir, windowed)."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None
ROOT = os.path.abspath('.')

# CTranslate2 нужны .dll / .so рядом с модулем
ct2_binaries = collect_dynamic_libs('ctranslate2')

# faster-whisper assets (silero_vad_v6.onnx)
fw_assets = collect_data_files('faster_whisper', includes=['assets/*'])

a = Analysis(
    ['dictation.pyw'],
    pathex=[ROOT],
    binaries=ct2_binaries,
    datas=[
        ('VERSION', '.'),
        ('dictionary.txt', '.'),
        ('dictionaries', 'dictionaries'),
    ] + fw_assets,
    hiddenimports=[
        # PyQt6
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        # Audio
        'sounddevice', '_sounddevice_data', 'numpy',
        # Whisper / CTranslate2
        'ctranslate2', 'faster_whisper', 'huggingface_hub', 'tqdm',
        # Input
        'keyboard', 'pyperclip', 'pyautogui',
        # Win32
        'win32gui', 'win32api', 'win32con', 'pywintypes',
        # App modules
        'core', 'core.config_manager', 'core.recognizer', 'core.hotkeys',
        'core.tray', 'core.model_manager', 'core.model_catalog',
        'core.history_manager', 'core.event_bus',
        'app', 'settings_dialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas', 'PIL', 'pytest'],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VoiceDictation',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VoiceDictation',
)
