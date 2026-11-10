"""The generated package is consistent: provenance recorded, no imports of
Calibre/Qt/C extensions left at module level, every module imports."""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_provenance_recorded():
    from ebook_convert import _vendored

    assert len(_vendored.CALIBRE_COMMIT) == 40
    assert _vendored.CALIBRE_VERSION.count('.') == 2


def test_no_module_level_calibre_or_qt_imports():
    proc = subprocess.run([sys.executable, str(ROOT / 'tools' / 'vendor.py'), '--check'],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_module_imports():
    proc = subprocess.run([sys.executable, str(ROOT / 'tools' / 'check_imports.py')],
                          capture_output=True, text=True, cwd=ROOT, timeout=600)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_version_flag():
    proc = subprocess.run([sys.executable, '-m', 'ebook_convert.main', '--version'],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0
    assert 'calibre' in proc.stdout
