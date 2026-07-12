# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


datas = [('assets', 'assets')]
for telemetry_config in ('telemetry.json', 'telemetry.local.json', 'telemetry.example.json'):
    if Path(telemetry_config).exists():
        datas.append((telemetry_config, '.'))

python_root = Path(sys.base_prefix)
for source, target in (
    (python_root / 'Lib' / 'tkinter', 'tkinter'),
    (python_root / 'tcl' / 'tcl8', 'tcl8'),
    (python_root / 'tcl' / 'tcl8.6', '_tcl_data'),
    (python_root / 'tcl' / 'tk8.6', '_tk_data'),
):
    if source.exists():
        datas.append((str(source), target))

binaries = []
for dll_name in ('tcl86t.dll', 'tk86t.dll', '_tkinter.pyd'):
    dll_path = python_root / 'DLLs' / dll_name
    if dll_path.exists():
        binaries.append((str(dll_path), '.'))

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=['tkinter', 'tkinter.ttk'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['scripts\\pyinstaller_tk_runtime_hook.py'],
    excludes=[
        'torch', 'torchvision', 'torchaudio', 'tensorflow',
        'onnxruntime', 'numba', 'llvmlite', 'matplotlib',
        'sympy', 'cv2', 'PIL.ImageQt', 'notebook', 'jupyter',
        'ipython', 'qtpy', 'PyQt5', 'PySide2', 'PySide6',
        'scipy', 'scipy.sparse', 'scipy.special', 'scipy.spatial',
        'scipy.stats', 'scipy.linalg', 'scipy.io',
        'pandas', 'numpy',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='本地资料脱敏工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\app_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='本地资料脱敏工具',
)
