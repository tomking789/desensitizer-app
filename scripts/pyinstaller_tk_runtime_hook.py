from __future__ import annotations

import os
import sys
import ctypes
from pathlib import Path


base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
if not (base_dir / "_tcl_data").exists() and (base_dir / "_internal").exists():
    base_dir = base_dir / "_internal"

try:
    _DLL_DIRECTORY_HANDLE = os.add_dll_directory(str(base_dir))
except (AttributeError, OSError):
    _DLL_DIRECTORY_HANDLE = None
    os.environ["PATH"] = str(base_dir) + os.pathsep + os.environ.get("PATH", "")
sys._desensitizer_dll_directory_handle = _DLL_DIRECTORY_HANDLE

_preloaded_dlls = []
for dll_name in ("tcl86t.dll", "tk86t.dll"):
    dll_path = base_dir / dll_name
    if dll_path.exists():
        try:
            _preloaded_dlls.append(ctypes.WinDLL(str(dll_path)))
        except OSError:
            pass
sys._desensitizer_preloaded_tk_dlls = _preloaded_dlls

os.environ.setdefault("TCL_LIBRARY", str(base_dir / "_tcl_data"))
os.environ.setdefault("TK_LIBRARY", str(base_dir / "_tk_data"))
