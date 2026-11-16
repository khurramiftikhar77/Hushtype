# PyInstaller build for the Windows app. Run from the repository root:
#   pyinstaller --noconfirm packaging/hushtype.spec
# Output: dist/Hushtype/Hushtype.exe (a folder, packed by installer.iss)

import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 (SPECPATH is set by PyInstaller)

datas = [(os.path.join(ROOT, "hushtype", "ui"), "hushtype/ui")]
datas += collect_data_files("faster_whisper")  # voice activity detection model (.onnx)
binaries = collect_dynamic_libs("ctranslate2")  # Whisper inference engine

a = Analysis(  # noqa: F821
    [os.path.join(SPECPATH, "launcher.py")],  # noqa: F821
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=["pynput.keyboard._win32", "pynput.mouse._win32", "pystray._win32",
                   "webview.platforms.winforms", "webview.platforms.edgechromium"],
    excludes=["tkinter", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Hushtype",
    icon=os.path.join(SPECPATH, "hushtype.ico"),  # noqa: F821
    console=False,  # no black terminal window
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Hushtype", upx=False)  # noqa: F821
