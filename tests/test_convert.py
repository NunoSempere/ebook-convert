"""End-to-end smoke tests: run the CLI over small fixtures."""
import pathlib
import subprocess
import sys
import zipfile

import pytest


FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


def convert(src, dst, *args):
    proc = subprocess.run([sys.executable, '-m', 'ebook_convert.main',
                           str(src), str(dst)] + list(args),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    assert dst.exists() and dst.stat().st_size > 0, proc.stderr
    return proc


def test_txt_to_epub(tmp_path):
    out = tmp_path / 'out.epub'
    convert(FIXTURES / 'sample.txt', out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert 'mimetype' in names
        html = next(n for n in names if n.endswith('.html'))
        assert 'Chapter One' in zf.read(html).decode('utf-8')


def test_tag_soup_html_to_epub(tmp_path):
    out = tmp_path / 'out.epub'
    convert(FIXTURES / 'sample.html', out)
    with zipfile.ZipFile(out) as zf:
        opf = next(n for n in zf.namelist() if n.endswith('.opf'))
        assert 'Test Author' in zf.read(opf).decode('utf-8')


@pytest.mark.parametrize('ext', ['epub', 'mobi', 'txt', 'docx',
                                 'htmlz', 'lrf', 'fb2'])
def test_epub3_with_malformed_xhtml(epub3_path, tmp_path, ext):
    out = tmp_path / ('out.' + ext)
    convert(epub3_path, out)
    if ext == 'txt':
        text = out.read_text(encoding='utf-8')
        assert 'Chapter One' in text
        assert 'HTML5 fallback' in text
        assert 'Chapter Two' in text


def test_epub_toc_is_taken_from_nav(epub3_path, tmp_path):
    out = tmp_path / 'out.epub'
    convert(epub3_path, out)
    with zipfile.ZipFile(out) as zf:
        ncx = next(n for n in zf.namelist() if n.endswith('.ncx'))
        data = zf.read(ncx).decode('utf-8')
    assert 'Chapter One' in data and 'Chapter Two' in data


@pytest.mark.parametrize('ext', ['mobi', 'docx', 'fb2', 'lrf', 'htmlz'])
def test_cover_image_survives(epub3_with_cover_path, tmp_path, ext):
    out = tmp_path / ('out.' + ext)
    proc = convert(epub3_with_cover_path, out)
    assert 'thumbnail' not in proc.stderr
    assert 'Bad image' not in proc.stderr
    data = out.read_bytes()
    if ext in ('mobi', 'lrf'):
        assert b'JFIF' in data
    elif ext == 'fb2':
        assert b'<binary' in data
    else:
        with zipfile.ZipFile(out) as zf:
            assert any(n.lower().endswith(('.jpg', '.jpeg'))
                       for n in zf.namelist())
