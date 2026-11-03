# PyInstaller spec: builds dist/SlideshowMaker.exe (one file, no console).
#   pyinstaller slideshow.spec
import os

ROOT = os.path.abspath(os.path.dirname(SPEC))
SRC = os.path.join(ROOT, "src")
ASSETS = os.path.join(SRC, "slideshow_maker", "assets")

a = Analysis(
    [os.path.join(ROOT, "launcher.py")],
    pathex=[SRC],
    datas=[(os.path.join(ASSETS, "icon.ico"), "."), (os.path.join(ASSETS, "icon.png"), ".")],
    hiddenimports=["slideshow_maker.app.main_window", "slideshow_maker.cli", "PIL._tkinter_finder"],
    excludes=[
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtPdf", "PySide6.QtNetwork", "tkinter", "matplotlib", "scipy",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="SlideshowMaker",
    icon=os.path.join(ASSETS, "icon.ico"),
    console=False,
    upx=False,
)
