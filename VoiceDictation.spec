# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Voice Dictation (onedir, windowed)."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None
ROOT = os.path.abspath('.')

# CTranslate2 нужны .dll / .so рядом с модулем (для LLM)
ct2_binaries = collect_dynamic_libs('ctranslate2')

# ONNX Runtime DLLs (для ASR)
try:
    ort_binaries = collect_dynamic_libs('onnxruntime')
except Exception:
    ort_binaries = []

a = Analysis(
    ['dictation.pyw'],
    pathex=[ROOT],
    binaries=ct2_binaries + ort_binaries,
    datas=[
        ('VERSION', '.'),
        ('dictionary.txt', '.'),
        ('dictionaries', 'dictionaries'),
        ('Ava.jpg', '.'),
        ('assets/sounds', 'assets/sounds'),
        ('assets/silero_vad.onnx', 'assets'),
        ('README.md', '.'),
    ],
    hiddenimports=[
        # PyQt6
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        # Audio
        'sounddevice', '_sounddevice_data', 'numpy',
        # ASR (Qwen3-ASR ONNX)
        'onnxruntime', 'tokenizers', 'librosa', 'soundfile',
        # LLM (CTranslate2)
        'ctranslate2',
        'huggingface_hub', 'huggingface_hub.utils', 'huggingface_hub.utils.tqdm',
        'tqdm',
        # Input
        'keyboard', 'pyperclip', 'pyautogui',
        # Win32
        'win32gui', 'win32api', 'win32con', 'pywintypes',
        # App modules
        'core', 'core.config_manager', 'core.recognizer', 'core.hotkeys',
        'core.tray', 'core.model_manager', 'core.model_catalog',
        'core.asr_backend', 'core.qwen3_asr', 'core.vad',
        'core.history_manager', 'core.event_bus',
        'app', 'settings_dialog',
        # LLM conversion (dynamic imports in settings_dialog.py / convert_llm.py)
        'scripts', 'scripts.convert_llm',
        'ctranslate2.converters', 'ctranslate2.converters.transformers',
        'transformers', 'transformers.models', 'transformers.models.auto',
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
    uac_admin=False,
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
