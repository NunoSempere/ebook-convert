"""Regression tests for fixes back-ported from Calibre into the legacy
input/output plugins (TXT, FB2, RTF, ODT, HTML/HTMLZ), the metadata
readers/writers and the small utility modules."""
import io
import os
import pathlib
import subprocess
import sys
import zipfile

from PIL import Image
import pytest

from tests.test_convert import convert, FIXTURES


def convert_with(src, dst, **recommendations):
    """Run a conversion in-process with explicit option values (the CLI has
    no option flags)."""
    from ebook_convert import logging
    from ebook_convert.customize.conversion import OptionRecommendation
    from ebook_convert.ebooks.conversion.plumber import Plumber
    plumber = Plumber(str(src), str(dst), logging.default_log)
    plumber.merge_ui_recommendations(
        [(k, v, OptionRecommendation.HIGH) for k, v in recommendations.items()])
    plumber.run()
    assert dst.exists() and dst.stat().st_size > 0
    return dst


# ---------------------------------------------------------------- TXT

def test_split_utf8_never_splits_a_multibyte_sequence():
    from ebook_convert.ebooks.txt.processor import split_utf8, split_txt
    text = ('a' * 15 + 'é' + 'b' * 10).encode('utf-8')  # é straddles 16
    for n in range(4, 20):
        parts = list(split_utf8(text, n))
        assert b''.join(parts) == text
        for part in parts:
            part.decode('utf-8')  # must not raise
    # the whole pipeline: a huge single paragraph of multibyte text is split
    # into flows without producing replacement characters
    para = ('中文' * 20000)
    out = split_txt(para, epub_split_size_kb=50)
    assert '�' not in out and out.replace('\n', '') == para


def test_remove_indents_keeps_newlines():
    from ebook_convert.ebooks.txt.processor import remove_indents
    assert remove_indents('  a\n\tb\n\nc') == 'a\nb\n\nc'


def test_nested_list_txt_output_has_separators(tmp_path):
    src = tmp_path / 'in.html'
    src.write_text('<html><body><ul><li>foo<ul><li>bar</li></ul></li>'
                   '<li>baz</li></ul><div>x<span>y</span><div>z</div></div>'
                   '</body></html>', encoding='utf-8')
    out = tmp_path / 'out.txt'
    convert(src, out)
    lines = [l for l in out.read_text(encoding='utf-8').splitlines() if l.strip()]
    assert lines == ['foo', 'bar', 'baz', 'xy', 'z']


def test_txtz_round_trip_keeps_formatting_and_cover(epub3_with_cover_path, tmp_path):
    mid = tmp_path / 'mid.txtz'
    convert_with(epub3_with_cover_path, mid, txt_output_formatting='markdown')
    with zipfile.ZipFile(mid) as zf:
        names = zf.namelist()
        opf = zf.read('metadata.opf').decode('utf-8')
    assert '<text-formatting>markdown</text-formatting>' in opf
    assert '<cover-relpath-from-base>' in opf
    # images are only kept when the text format can reference them
    assert any(n.lower().endswith(('.jpg', '.jpeg')) for n in names)
    from ebook_convert.ebooks.metadata.extz import get_metadata
    with open(mid, 'rb') as f:
        mi = get_metadata(f)
    assert mi.title == 'Broken Book' and mi.cover_data[1]
    back = tmp_path / 'back.epub'
    convert(mid, back)
    with zipfile.ZipFile(back) as zf:
        names = zf.namelist()
        assert any(n.lower().endswith(('.jpg', '.jpeg')) for n in names)


# ---------------------------------------------------------------- FB2

def test_fb2_output_keeps_nbsp_only_paragraph(tmp_path):
    src = tmp_path / 'in.html'
    src.write_bytes(b'<html><body><h1>T</h1><p>One</p><p>\xc2\xa0</p><p>Two</p></body></html>')
    out = tmp_path / 'out.fb2'
    convert(src, out)
    data = out.read_text(encoding='utf-8')
    assert '<p>\xa0</p>' in data


FB22 = '''<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.2" xmlns:l="http://www.w3.org/1999/xlink">
<description><title-info><genre>sf</genre>
<author><first-name>Anna</first-name><last-name>Author</last-name></author>
<book-title>Namespace Test</book-title><lang>en</lang>
<coverpage><image l:href="#cover.png"/></coverpage>
</title-info><publish-info><publisher>P</publisher><year>2001</year></publish-info></description>
<body><title><p>Chapter One</p></title><section><p>First paragraph.</p>
<p>Second paragraph.</p><image l:href="#cover.png"/></section></body>
<binary id="cover.png" content-type="image/png">iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==</binary>
</FictionBook>'''


def test_fb2_input_with_unknown_namespace_converts(tmp_path):
    src = tmp_path / 'ns22.fb2'
    src.write_text(FB22, encoding='utf-8')
    out = tmp_path / 'out.epub'
    convert(src, out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        html = b''.join(zf.read(n) for n in names if n.endswith('.xhtml'))
        opf = zf.read(next(n for n in names if n.endswith('.opf')))
    assert b'First paragraph.' in html and b'Second paragraph.' in html
    assert b'<p ' in html or b'<p>' in html  # div.paragraph became <p>
    assert b'Namespace Test' in opf and b'Anna Author' in opf
    assert any(n.endswith('.png') for n in names)


def test_fb2_metadata_round_trip_with_apply_null():
    from ebook_convert.ebooks.metadata.fb2 import get_metadata, set_metadata
    raw = FB22.encode('utf-8')
    mi = get_metadata(io.BytesIO(raw))
    assert mi.title == 'Namespace Test' and mi.authors == ['Anna Author']
    assert mi.publisher == 'P'
    mi.publisher = 'New Publisher'
    mi.tags = []
    stream = io.BytesIO(raw)
    set_metadata(stream, mi, apply_null=True)
    stream.seek(0)
    mi2 = get_metadata(stream)
    assert mi2.publisher == 'New Publisher' and mi2.tags == []


# ---------------------------------------------------------------- RTF

def test_rtf_metadata_write_with_backslash():
    from ebook_convert.ebooks.metadata.rtf import get_metadata, set_metadata
    from ebook_convert.ebooks.metadata.book.base import Metadata
    stream = io.BytesIO(br'{\rtf1\ansi\ansicpg1252{\info{\title old}}}')
    mi = Metadata('Back\\slash \\u title', ['An Author'])
    set_metadata(stream, mi)
    stream.seek(0)
    assert get_metadata(stream).title == 'Back\\slash \\u title'


# ---------------------------------------------------------------- ODT

def make_odt(path):
    from odf.opendocument import OpenDocumentText
    from odf.text import P, H
    from odf.draw import Frame, Image as DImage
    from odf.style import Style, GraphicProperties
    doc = OpenDocumentText()
    doc.text.addElement(H(outlinelevel=1, text='Chapter One'))
    doc.text.addElement(P(text='Hello from ODT.'))
    buf = io.BytesIO()
    Image.new('RGB', (40, 30), (0, 120, 200)).save(buf, 'PNG')
    href = doc.addPicture('Pictures/pic.png', 'image/png', buf.getvalue())
    fs = Style(name='fr1', family='graphic')
    fs.addElement(GraphicProperties(wrap='none'))
    doc.automaticstyles.addElement(fs)
    p = P()
    frame = Frame(stylename=fs, width='4cm', height='3cm', anchortype='paragraph')
    frame.addElement(DImage(href=href))
    p.addElement(frame)
    doc.text.addElement(p)
    doc.save(str(path))
    return path


def test_odt_with_image_converts_and_keeps_it(tmp_path):
    src = make_odt(tmp_path / 'book.odt')
    out = tmp_path / 'out.epub'
    convert(src, out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        html = b''.join(zf.read(n) for n in names if n.endswith('.xhtml'))
    assert any(n.endswith('pic.png') for n in names)
    assert b'Hello from ODT.' in html


# ---------------------------------------------------------------- HTML / HTMLZ

def make_html_book(root):
    (root / 'css' / 'deep').mkdir(parents=True)
    (root / 'img').mkdir()
    (root / 'fonts').mkdir()
    Image.new('RGB', (20, 20), (10, 200, 10)).save(root / 'img' / 'bg.png')
    Image.new('RGB', (20, 20), (200, 10, 10)).save(root / 'img' / 'inline.png')
    (root / 'fonts' / 'f.ttf').write_bytes(b'\0\1\0\0' + b'\0' * 100)
    (root / 'index.html').write_text(
        '<html><head><title>Nested</title>'
        '<link rel="stylesheet" href="css/a.css"/></head>'
        '<body><h1 class="bg">Chapter One</h1><p class="deep">Hello</p>'
        '<p><img src="img/inline.png" alt="inline"/></p></body></html>',
        encoding='utf-8')
    (root / 'css' / 'a.css').write_text(
        '@import url("deep/b.css");\n'
        '@font-face { font-family: F; src: url("../fonts/f.ttf"); }\n'
        '.bg { background-image: url("../img/bg.png"); font-family: F; }\n')
    (root / 'css' / 'deep' / 'b.css').write_text('.deep { font-weight: bold; }\n')
    return root / 'index.html'


def test_htmlz_output_has_fonts_and_rewritten_css_urls(tmp_path):
    src = make_html_book(tmp_path / 'book')
    out = tmp_path / 'out.htmlz'
    convert(src, out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        css = zf.read('style.css').decode('utf-8')
    assert 'fonts/000000.ttf' in names
    assert 'images/000000.png' in names and 'images/000001.png' in names
    assert 'url(fonts/000000.ttf)' in css
    assert 'url(images/00000' in css
    # the nested @import was resolved
    assert 'font-weight: bold' in css
    assert '@import' not in css


def test_html_input_can_confine_resources_to_the_document_root(tmp_path):
    src = make_html_book(tmp_path / 'book')
    outside = tmp_path / 'outside'
    outside.mkdir()
    Image.new('RGB', (20, 20), (10, 10, 200)).save(outside / 'out.png')
    html = src.read_text(encoding='utf-8').replace(
        '</body>', '<p><img src="../outside/out.png" alt="outside"/></p></body>')
    src.write_text(html, encoding='utf-8')
    # default: the fork keeps including resources from outside the root
    out = tmp_path / 'default.htmlz'
    convert(src, out)
    with zipfile.ZipFile(out) as zf:
        assert sum(n.endswith('.png') for n in zf.namelist()) == 3
    out = tmp_path / 'confined.htmlz'
    convert_with(src, out, allow_local_files_outside_root=False)
    with zipfile.ZipFile(out) as zf:
        assert sum(n.endswith('.png') for n in zf.namelist()) == 2


def test_html_input_filename_sanitising():
    from ebook_convert.ebooks.conversion.plugins.html_input import sanitize_file_name
    assert '/' not in sanitize_file_name('a%2Fb%2fc.html')
    assert sanitize_file_name('a?b=c#d.png') == 'a_b_c_d.png'


# ---------------------------------------------------------------- metadata

def test_opf2_isbn_without_scheme_and_editors():
    from ebook_convert.ebooks.metadata.opf2 import OPF
    raw = b'''<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="u">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
<dc:identifier id="u">978-0-306-40615-7</dc:identifier><dc:title>T</dc:title>
<dc:creator opf:role="edt">Ed Itor</dc:creator></metadata>
<manifest><item id="nohref" media-type="text/html"/></manifest><spine/></package>'''
    opf = OPF(io.BytesIO(raw), os.getcwd())
    assert opf.get_identifiers() == {'isbn': '9780306406157'}
    assert opf.authors == ['Ed Itor']
    mi = opf.to_book_metadata()
    assert mi.isbn == '9780306406157'


def test_opf2_language_written_as_und_and_ids_escaped():
    from ebook_convert.ebooks.metadata.opf2 import OPF, metadata_to_opf
    from ebook_convert.ebooks.metadata.book.base import Metadata
    mi = Metadata('title', ['author'])
    evil = 'x</dc:identifier><dc:title>injected</dc:title><dc:identifier>'
    mi.uuid = evil
    raw = metadata_to_opf(mi)
    assert b'<dc:title>injected' not in raw
    opf = OPF(io.BytesIO(raw), os.getcwd())
    assert opf.title == 'title'
    assert opf.to_book_metadata().uuid == evil
    opf.languages = []
    assert list(opf.raw_languages) == ['und']


def test_opf3_subtitle_editors_and_url_identifier():
    from ebook_convert.ebooks.metadata.opf import get_metadata
    raw = b'''<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="u">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="u">x</dc:identifier>
<dc:title id="t1">Main</dc:title><dc:title id="t2">Sub</dc:title>
<meta refines="#t2" property="title-type">subtitle</meta>
<dc:creator id="c1">Second</dc:creator><meta refines="#c1" property="role" scheme="marc:relators">edt</meta>
<meta refines="#c1" property="display-seq">2</meta>
<dc:creator id="c2">First</dc:creator><meta refines="#c2" property="role" scheme="marc:relators">edt</meta>
<meta refines="#c2" property="display-seq">1</meta>
<dc:identifier>https://example.com/book</dc:identifier>
</metadata><manifest><item id="c" href="c.jpg" media-type="image/jpeg"/></manifest>
<spine><itemref idref="c"/></spine></package>'''
    mi, ver, raster_cover, first = get_metadata(raw)
    assert mi.title == 'Main: Sub'
    assert mi.authors == ['First', 'Second']
    assert mi.get_identifiers() == {'url': 'https://example.com/book'}
    assert raster_cover == 'c.jpg'  # first spine item is an image


def test_roman_numeral_series_index_and_title_sort():
    from ebook_convert.ebooks.metadata import fmt_sidx, title_sort, check_isbn, normalize_isbn
    assert fmt_sidx('XV') == 'XV'
    assert fmt_sidx(2.5) == '2.5' and fmt_sidx(3) == '3'
    assert title_sort('"The Book"') == 'Book, The'
    assert title_sort('“A Tale”') == 'Tale, A'
    assert check_isbn('0-306-40615-2', simple_sanitize=True) == '0306406152'
    assert check_isbn('x0306406152') is None
    assert check_isbn('0-306-40615-2 ') == '0306406152'
    assert normalize_isbn('0306406152') == '9780306406157'


def test_epub_and_mobi_metadata_readers(epub3_with_cover_path, tmp_path):
    from ebook_convert.ebooks.metadata.epub import get_metadata as epub_get, set_metadata as epub_set
    from ebook_convert.ebooks.metadata.mobi import get_metadata as mobi_get, set_metadata as mobi_set
    from ebook_convert.ebooks.metadata.meta import get_metadata as any_get
    for ext, getter, setter in (('epub', epub_get, epub_set),
                                ('mobi', mobi_get, mobi_set),
                                ('azw3', mobi_get, mobi_set)):
        out = tmp_path / ('out.' + ext)
        convert(epub3_with_cover_path, out)
        with open(out, 'rb') as f:
            mi = getter(f)
        assert mi.title == 'Broken Book', ext
        assert mi.authors == ['Someone'], ext
        assert mi.cover_data[1], ext
        with open(out, 'rb') as f:
            assert any_get(f, ext).title == 'Broken Book'
        mi.title = 'Renamed'
        mi.authors = ['New Author']
        with open(out, 'r+b') as f:
            setter(f, mi)
        with open(out, 'rb') as f:
            mi2 = getter(f)
        assert (mi2.title, mi2.authors) == ('Renamed', ['New Author']), ext


def test_opf_cover_confined_to_opf_directory(tmp_path):
    from ebook_convert.ebooks.metadata.meta import opf_metadata
    book = tmp_path / 'book'
    book.mkdir()
    (tmp_path / 'secret.png').write_bytes(b'secret')
    (book / 'cover.png').write_bytes(b'cover')

    def read_cover(href):
        opf = book / 'metadata.opf'
        opf.write_text(
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uuid_id">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">'
            '<dc:identifier opf:scheme="calibre" id="calibre_id">1</dc:identifier><dc:title>t</dc:title>'
            '</metadata><guide><reference type="cover" href="%s"/></guide></package>' % href)
        return opf_metadata(str(opf)).cover_data[1]

    assert read_cover('cover.png') == b'cover'
    assert read_cover('../secret.png') is None


# ---------------------------------------------------------------- utils

def test_chardet_none_confidence(monkeypatch):
    import chardet
    from ebook_convert.ebooks import chardet as cd
    monkeypatch.setattr(chardet, 'detect', lambda b: {'encoding': None, 'confidence': None})
    ans = cd.detect(b'xyz')
    assert ans == {'encoding': '', 'confidence': 0}
    assert cd.force_encoding(b'xyz', False) in ('utf-8', 'utf8')
    monkeypatch.setattr(chardet, 'detect', lambda b: {'encoding': 'MAC-CENTRALEUROPE', 'confidence': 1})
    assert cd.detect(b'xyz')['encoding'] == 'cp1250'


def test_imghdr_identifies_webp():
    from ebook_convert.utils.imghdr import identify, what
    for lossless in (False, True):
        buf = io.BytesIO()
        Image.new('RGB', (37, 23), (1, 2, 3)).save(buf, 'WEBP', lossless=lossless)
        assert what(None, buf.getvalue()) == 'webp'
        assert identify(buf.getvalue()) == ('webp', 37, 23)


def test_xml_parse_helpers_and_dates():
    from ebook_convert.utils.xml_parse import safe_xml_fromstring, safe_html_fromstring, fragment_fromstring
    assert safe_xml_fromstring('<a>é</a>').text == 'é'
    assert safe_html_fromstring('<p>é</p>').text_content() == 'é'
    assert fragment_fromstring('<p>x</p>').tag == 'p'
    from ebook_convert.utils.date import now, utcnow, fromtimestamp, w3cdtf
    assert now().tzinfo is not None and utcnow().tzinfo is not None
    assert fromtimestamp(0).year == 1970
    assert w3cdtf(utcnow()).endswith('Z')
    from ebook_convert.utils.localization import lang_as_bcp47, is_rtl_lang
    assert lang_as_bcp47('eng') == 'en' and not lang_as_bcp47('und')
    assert is_rtl_lang('ar') and not is_rtl_lang('en')
