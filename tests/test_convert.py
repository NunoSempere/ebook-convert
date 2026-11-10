"""End-to-end smoke tests: run the CLI over small fixtures."""
import pathlib
import re
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


@pytest.mark.parametrize('ext', ['epub', 'mobi', 'azw3', 'txt', 'docx',
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


@pytest.mark.parametrize('ext', ['mobi', 'azw3', 'docx', 'fb2', 'lrf', 'htmlz'])
def test_cover_image_survives(epub3_with_cover_path, tmp_path, ext):
    out = tmp_path / ('out.' + ext)
    proc = convert(epub3_with_cover_path, out)
    assert 'thumbnail' not in proc.stderr
    assert 'Bad image' not in proc.stderr
    data = out.read_bytes()
    if ext in ('mobi', 'azw3', 'lrf'):
        assert b'JFIF' in data
    elif ext == 'fb2':
        assert b'<binary' in data
    else:
        with zipfile.ZipFile(out) as zf:
            assert any(n.lower().endswith(('.jpg', '.jpeg'))
                       for n in zf.namelist())


def test_azw3_round_trip(epub3_path, tmp_path):
    azw3 = tmp_path / 'book.azw3'
    convert(epub3_path, azw3)
    data = azw3.read_bytes()
    assert data[60:68] == b'BOOKMOBI'
    assert b'KF8' not in data[:16]  # header is PalmDOC, KF8 lives inside
    back = tmp_path / 'back.epub'
    convert(azw3, back)
    with zipfile.ZipFile(back) as zf:
        names = zf.namelist()
        html = b''.join(zf.read(n) for n in names
                        if n.endswith(('.html', '.xhtml')))
        ncx = next(n for n in names if n.endswith('.ncx'))
        toc = zf.read(ncx).decode('utf-8')
    assert b'HTML5 fallback' in html
    assert b'Chapter Two' in html
    assert 'Chapter One' in toc and 'Chapter Two' in toc


@pytest.mark.parametrize('ext', ['htmlz', 'txtz'])
def test_zip_containers_round_trip_metadata_and_cover(
        epub3_with_cover_path, tmp_path, ext):
    mid = tmp_path / ('mid.' + ext)
    convert(epub3_with_cover_path, mid)
    with zipfile.ZipFile(mid) as zf:
        names = zf.namelist()
        assert 'metadata.opf' in names
        opf = zf.read('metadata.opf').decode('utf-8')
    assert 'Broken Book' in opf
    if ext == 'htmlz':
        assert 'cover.jpg' in names
    back = tmp_path / 'back.epub'
    proc = convert(mid, back)
    assert 'Traceback' not in proc.stderr
    with zipfile.ZipFile(back) as zf:
        names = zf.namelist()
        opf = zf.read(next(n for n in names if n.endswith('.opf')))
    assert b'Broken Book' in opf
    assert b'Someone' in opf
    if ext == 'htmlz':
        assert any(n.endswith('cover.jpg') for n in names)


def test_rtf_with_date_field_border_and_emoji(tmp_path):
    """Regressions from Calibre: DATE fields with a format, bordered
    paragraphs and astral-plane characters (UTF-16 surrogate pairs) used to
    crash or produce invalid XML."""
    out = tmp_path / 'out.txt'
    convert(FIXTURES / 'tricky.rtf', out)
    text = out.read_text(encoding='utf-8')
    assert 'Bordered paragraph' in text
    assert '1 January 2024' in text
    assert '\U0001F600' in text


def _epub_text(path):
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        html = b''.join(zf.read(n) for n in names
                        if n.endswith(('.xhtml', '.html'))).decode('utf-8')
    return names, html


@pytest.mark.parametrize('name', ['out.kepub', 'out.kepub.epub'])
def test_kepub_output_adds_kobo_markup(epub3_path, tmp_path, name):
    out = tmp_path / name
    convert(epub3_path, out)
    names, html = _epub_text(out)
    assert any(n.endswith('kobo.js') for n in names)
    assert 'id="book-columns"' in html and 'id="book-inner"' in html
    # one Kobo span per sentence, trailing whitespace inside the span
    spans = re.findall(r'<span class="koboSpan" id="kobo\.\d+\.\d+">([^<]*)</span>',
                       html)
    assert len(spans) > 5
    assert any(s.endswith('. ') or s.endswith('.') for s in spans)


def test_kepub_input_strips_kobo_markup(epub3_path, tmp_path):
    kepub = tmp_path / 'book.kepub.epub'
    convert(epub3_path, kepub)
    _, text = _epub_text(kepub)
    assert 'koboSpan' in text
    back = tmp_path / 'back.epub'
    convert(kepub, back)
    names, html = _epub_text(back)
    assert 'koboSpan' not in html and 'book-columns' not in html
    assert not any(n.endswith('kobo.js') for n in names)
    with zipfile.ZipFile(epub3_path) as zf:
        original = b''.join(zf.read(n) for n in zf.namelist()
                            if n.endswith('.xhtml')).decode('utf-8')
    sentence = re.search(r'<p[^>]*>([^<]{20,})</p>', original).group(1)
    assert sentence in html


def test_mobi_round_trip_keeps_full_toc(epub3_path, tmp_path):
    # Nested TOC with entries inside a chapter; the MOBI's inline contents
    # page (if any) is not the source of truth, the NCX index record is.
    import shutil
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from conftest import pack_epub
    src = tmp_path / 'src'
    shutil.copytree(pathlib.Path(__file__).parent / 'fixtures' / 'epub3', src)
    ch1 = src / 'OEBPS' / 'ch1.xhtml'
    ch1.write_text(ch1.read_text(encoding='utf-8').replace(
        '</body>', '<h2 id="s1">Section One</h2><p>one one</p>'
                   '<h2 id="s2">Section Two</h2><p>one two</p></body>'), encoding='utf-8')
    nav = src / 'OEBPS' / 'nav.xhtml'
    nav.write_text(nav.read_text(encoding='utf-8').replace(
        '<li><a href="ch1.xhtml">Chapter One</a></li>',
        '<li><a href="ch1.xhtml">Chapter One</a><ol>'
        '<li><a href="ch1.xhtml#s1">Section One</a></li>'
        '<li><a href="ch1.xhtml#s2">Section Two</a></li></ol></li>'), encoding='utf-8')
    epub = pack_epub(src, tmp_path / 'nested.epub')
    mobi = tmp_path / 'book.mobi'
    convert(epub, mobi)
    back = tmp_path / 'back.epub'
    convert(mobi, back)
    with zipfile.ZipFile(back) as zf:
        ncx = zf.read(next(n for n in zf.namelist() if n.endswith('.ncx'))).decode('utf-8')
    labels = re.findall(r'<text>([^<]*)</text>', ncx)
    assert {'Chapter One', 'Section One', 'Section Two', 'Chapter Two'} <= set(labels), labels
