"""End-to-end PDF input tests over tests/fixtures/sample.pdf.

The fixture is written by tests/make_sample_pdf.py. The conversions need
poppler's pdftohtml (and pdfinfo for the metadata) and are skipped without it.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

import pytest

from tests.make_sample_pdf import AUTHOR, FIXTURE, HEADER, TITLE, build_pdf

needs_poppler = pytest.mark.skipif(shutil.which('pdftohtml') is None,
                                   reason='pdftohtml (poppler) not in PATH')

# Pairs of words that are split by a page break in the fixture and so must be
# joined by the cross-page paragraph merging of the calibre engine
STRADDLING = [
    ('bread and the week of newspapers', 'that the village had already'),
    ('He denied it when asked, but he', 'denied it in the manner'),
    ('until they vanished past the', 'headland and left him alone'),
]


def convert_cli(src, dst):
    proc = subprocess.run([sys.executable, '-m', 'ebook_convert.main',
                           str(src), str(dst)], capture_output=True,
                          text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    assert dst.exists() and dst.stat().st_size > 0, proc.stderr
    return proc


def convert_with_engine(src, dst, engine):
    """Convert in-process: the CLI exposes no options, so the engine is set
    through the Plumber's UI recommendations."""
    import logging as stdlib_logging

    from ebook_convert import logging
    from ebook_convert.customize.conversion import OptionRecommendation
    from ebook_convert.ebooks.conversion.plumber import Plumber

    plumber = Plumber(str(src), str(dst), logging.default_log)
    plumber.merge_ui_recommendations([('pdf_engine', engine,
                                       OptionRecommendation.HIGH)])
    # Plumber.setup_options() logs the changed options with a format string
    # that has fewer placeholders than arguments. Outside pytest the logging
    # module only prints that mistake to stderr; pytest's capture handler
    # re-raises it, so turn that off for the duration of the conversion.
    raise_exceptions = stdlib_logging.raiseExceptions
    stdlib_logging.raiseExceptions = False
    try:
        plumber.run()
    finally:
        stdlib_logging.raiseExceptions = raise_exceptions
    assert dst.exists() and dst.stat().st_size > 0


def epub_text(path):
    "The OPF and the concatenated XHTML text of an EPUB"
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        opf = zf.read(next(n for n in names if n.endswith('.opf'))).decode('utf-8')
        html = '\n'.join(zf.read(n).decode('utf-8') for n in sorted(names)
                         if n.endswith(('.html', '.xhtml')))
        ncx = ''
        for n in names:
            if n.endswith('.ncx'):
                ncx = zf.read(n).decode('utf-8')
    return opf, html, ncx


def paragraphs_of_html(html):
    "The text of each <p>/<h*> element, whitespace normalised"
    body = html.split('<body', 1)[1] if '<body' in html else html
    ans = []
    for m in re.finditer(r'<(p|h\d)\b[^>]*>(.*?)</\1>', body, flags=re.S):
        text = ' '.join(re.sub(r'<[^>]+>', ' ', m.group(2)).split())
        if text:
            ans.append(text)
    return ans


def paragraphs_of_txt(text):
    return [' '.join(p.split()) for p in re.split(r'\n\s*\n', text) if p.strip()]


def test_fixture_is_up_to_date():
    # The generator is deterministic, so the checked in file must match it
    assert FIXTURE.read_bytes() == build_pdf()
    assert FIXTURE.read_bytes().startswith(b'%PDF-1.4')


def check_calibre_engine_output(paras):
    body = ' '.join(paras)
    assert 'The lighthouse keeper had counted the ships' in body
    assert 'counted once again.' in body
    # The running header and the bare page numbers are removed
    assert HEADER not in body
    assert not any(re.fullmatch(r'\d+', p) for p in paras), paras
    # Paragraphs are merged across page breaks
    for first, second in STRADDLING:
        joined = [p for p in paras if first in p]
        assert len(joined) == 1, (first, paras)
        assert second in joined[0], (second, joined[0])


@needs_poppler
def test_calibre_engine_to_epub(tmp_path):
    out = tmp_path / 'out.epub'
    convert_cli(FIXTURE, out)
    opf, html, ncx = epub_text(out)
    assert TITLE in opf and AUTHOR in opf
    # pdftohtml's intermediate XML must not be in the manifest
    assert 'index.xml' not in opf
    assert 'src.pdf' not in opf
    check_calibre_engine_output(paragraphs_of_html(html))
    # The PDF outline became the table of contents
    for chapter in ('Chapter One', 'Chapter Two', 'Chapter Three'):
        assert chapter in ncx


@needs_poppler
def test_calibre_engine_to_txt(tmp_path):
    out = tmp_path / 'out.txt'
    convert_cli(FIXTURE, out)
    check_calibre_engine_output(paragraphs_of_txt(out.read_text(encoding='utf-8')))


@needs_poppler
def test_calibre_engine_in_process(tmp_path):
    out = tmp_path / 'out.txt'
    convert_with_engine(FIXTURE, out, 'calibre')
    check_calibre_engine_output(paragraphs_of_txt(out.read_text(encoding='utf-8')))


@needs_poppler
@pytest.mark.parametrize('ext', ['epub', 'txt'])
def test_pdftohtml_engine(tmp_path, ext):
    out = tmp_path / ('out.' + ext)
    convert_with_engine(FIXTURE, out, 'pdftohtml')
    if ext == 'epub':
        opf, html, ncx = epub_text(out)
        assert TITLE in opf
        assert 'index.xml' not in opf
        body = ' '.join(paragraphs_of_html(html))
        assert 'Chapter Two' in ncx
    else:
        body = ' '.join(paragraphs_of_txt(out.read_text(encoding='utf-8')))
    assert 'The lighthouse keeper had counted the ships' in body
    assert 'counted once again.' in body
    # This engine has no header/footer removal
    assert HEADER in body
