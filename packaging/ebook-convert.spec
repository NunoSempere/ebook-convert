# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: build with `pyinstaller packaging/ebook-convert.spec`
# (or `./make.sh binary`).  Produces a single self-contained executable at
# dist/ebook-convert.
import glob
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

# Non-Python resources (mime.types, xsl, css, jacket, fonts, iso codes ...).
datas = collect_data_files('ebook_convert')
# default_tweaks.py is read as a *file* at runtime, not imported, and
# PyInstaller would otherwise fold it into the bytecode archive.
datas += [(path, 'ebook_convert/data') for path in
          glob.glob(os.path.join(ROOT, 'ebook_convert', 'data', '*.py'))]
datas += collect_data_files('tzdata')

hiddenimports = []
# Input/output plugins and tree builders are discovered at runtime.
for pkg in ('ebook_convert', 'html5lib', 'bs4', 'odf', 'css_parser',
            'PIL', 'dateutil', 'pystache', 'regex', 'tzlocal', 'resvg_py',
            'msgpack', 'chardet'):
    hiddenimports += collect_submodules(pkg)

a = Analysis(
    ['entry.py'],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'markdown', 'pykakasi'],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ebook-convert',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
