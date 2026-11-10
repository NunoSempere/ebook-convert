"""Tests for MOBI/AZW3 fixes back-ported from Calibre."""
import re
import shutil
import struct
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest

from tests.conftest import FIXTURES, pack_epub
from tests.test_convert import convert


# Helpers {{{

def epub_with_image(tmp_path, name, mime, data):
    """Pack the EPUB3 fixture with an extra image shown in chapter two."""
    src = tmp_path / 'src'
    shutil.copytree(FIXTURES / 'epub3', src)
    opf = src / 'OEBPS' / 'content.opf'
    opf.write_text(opf.read_text().replace(
        '<manifest>',
        '<manifest><item id="pic" href="%s" media-type="%s"/>' % (name, mime)))
    ch2 = src / 'OEBPS' / 'ch2.xhtml'
    ch2.write_text(ch2.read_text().replace(
        '</body>', '<p><img src="%s" alt="pic"/></p></body>' % name))
    (src / 'OEBPS' / name).write_bytes(data)
    return pack_epub(src, tmp_path / 'book.epub')


def jpeg_bytes(img, **kw):
    buf = BytesIO()
    img.save(buf, 'JPEG', **kw)
    return buf.getvalue()


def jpegs_in(data):
    """Decode every JPEG embedded in a MOBI/AZW3 container."""
    for m in re.finditer(b'\xff\xd8\xff', data):
        try:
            img = Image.open(BytesIO(data[m.start():]))
            img.load()
        except Exception:
            continue
        yield img


class RecordingLog:
    """Duck typed stand-in for the conversion log."""

    def __init__(self):
        self.warnings = []

    def _record(self, msg, *args):
        self.warnings.append(msg % args if args else msg)

    warning = warn = error = _record

    def info(self, *args):
        pass

    debug = info

# }}}


# Kindle image pipeline (Calibre 9e2a7fca94, a8e449dcbc, 812fecec5f,
# 8e167914cd, f15ead933a, 2d68fbabb0, 555b629e17) {{{

class TestProcessJpegsForAmazon:

    def test_jpeg_without_exif_is_unchanged(self):
        from ebook_convert.ebooks.mobi.writer2.resources import process_jpegs_for_amazon
        data = jpeg_bytes(Image.new('RGB', (8, 8), (255, 0, 0)))
        assert process_jpegs_for_amazon(data) is data

    def test_jpeg_with_exif_is_stripped(self):
        from ebook_convert.ebooks.mobi.writer2.resources import process_jpegs_for_amazon
        img = Image.new('RGB', (8, 8), (0, 255, 0))
        exif = img.getexif()
        exif[0x010E] = 'test'
        data = jpeg_bytes(img, exif=exif.tobytes())
        assert 'exif' in Image.open(BytesIO(data)).info
        out = process_jpegs_for_amazon(data)
        assert 'exif' not in Image.open(BytesIO(out)).info
        assert b'JFIF' in out

    def test_jpeg_with_empty_exif_segment_is_stripped(self):
        # Regression test for https://bugs.launchpad.net/bugs/1943495
        from ebook_convert.ebooks.mobi.writer2.resources import process_jpegs_for_amazon
        base = jpeg_bytes(Image.new('RGB', (8, 8)))
        tiff = b'II' + struct.pack('<HI', 42, 8) + struct.pack('<HI', 0, 0)
        payload = b'Exif\x00\x00' + tiff
        app1 = b'\xff\xe1' + struct.pack('>H', len(payload) + 2) + payload
        data = base[:2] + app1 + base[2:]
        assert 'exif' in Image.open(BytesIO(data)).info
        out = process_jpegs_for_amazon(data)
        assert 'exif' not in Image.open(BytesIO(out)).info

    def test_jpeg_without_jfif_gets_one(self):
        from ebook_convert.ebooks.mobi.writer2.resources import process_jpegs_for_amazon
        data = jpeg_bytes(Image.new('RGB', (8, 8)))
        app0_len = struct.unpack('>H', data[4:6])[0]
        nojfif = data[:2] + data[4 + app0_len:]
        assert b'JFIF' not in nojfif
        assert b'JFIF' in process_jpegs_for_amazon(nojfif)

    def test_orientation_is_applied(self):
        from ebook_convert.ebooks.mobi.writer2.resources import process_jpegs_for_amazon
        img = Image.new('RGB', (100, 50), (200, 10, 10))
        exif = img.getexif()
        exif[0x0112] = 6
        out = process_jpegs_for_amazon(jpeg_bytes(img, exif=exif.tobytes()))
        res = Image.open(BytesIO(out))
        assert res.size == (50, 100)
        assert 'exif' not in res.info

    def test_non_jpeg_untouched(self):
        from ebook_convert.ebooks.mobi.writer2.resources import process_jpegs_for_amazon
        buf = BytesIO()
        Image.new('RGB', (8, 8)).save(buf, 'PNG')
        data = buf.getvalue()
        assert process_jpegs_for_amazon(data) is data
        assert process_jpegs_for_amazon(b'not an image') == b'not an image'


@pytest.mark.parametrize('ext', ['mobi', 'azw3'])
def test_rotated_jpeg_comes_out_upright_without_exif(tmp_path, ext):
    img = Image.new('RGB', (100, 50), (200, 10, 10))
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise to display
    src = epub_with_image(tmp_path, 'pic.jpg', 'image/jpeg',
                          jpeg_bytes(img, exif=exif.tobytes()))
    out = tmp_path / ('out.' + ext)
    proc = convert(src, out)
    assert 'Bad image' not in proc.stderr
    found = list(jpegs_in(out.read_bytes()))
    assert found, 'no JPEG found in output'
    for res in found:
        assert 'exif' not in res.info
        assert 'jfif' in res.info
    assert any(res.size == (50, 100) for res in found)


@pytest.mark.parametrize('ext', ['mobi', 'azw3'])
def test_webp_image_becomes_png(tmp_path, ext):
    buf = BytesIO()
    Image.new('RGB', (40, 30), (10, 200, 10)).save(buf, 'WEBP')
    src = epub_with_image(tmp_path, 'pic.webp', 'image/webp', buf.getvalue())
    out = tmp_path / ('out.' + ext)
    proc = convert(src, out)
    assert 'Bad image' not in proc.stderr
    data = out.read_bytes()
    assert b'WEBP' not in data
    pos = data.find(b'\x89PNG\r\n\x1a\n')
    assert pos >= 0
    png = Image.open(BytesIO(data[pos:]))
    assert png.size == (40, 30)

# }}}


# KF8 reader: url() rewriting in CSS flows (Calibre 529c26f60a, a67fb90335,
# 61ccbfc995) {{{

class TestFlowLinks:
    resource_map = ['images/00001.jpeg', 'fonts/00002.ttf', None]

    @property
    def flowinfo(self):
        from ebook_convert.ebooks.mobi.reader.mobi8 import FlowInfo
        return [
            FlowInfo(None, None, None, None),
            FlowInfo('css', 'file', 'styles', '0001.css'),
            FlowInfo('css', 'file', 'styles', '0002.css'),
            FlowInfo('css', 'inline', None, None),
        ]

    def convert(self, css):
        from ebook_convert.ebooks.mobi.reader.markup import update_flow_links
        reader = SimpleNamespace(flows=[None, css], flowinfo=self.flowinfo,
                                 header=SimpleNamespace(codec='utf-8'))
        log = RecordingLog()
        flows = update_flow_links(reader, self.resource_map, log)
        return flows[1], log.warnings

    def assert_converts(self, src, expected):
        output, warnings = self.convert(src)
        assert output == expected
        assert warnings == []

    @pytest.mark.parametrize('quote', ['', '"', "'"])
    @pytest.mark.parametrize('url,expected', [
        ('kindle:embed:0002?mime=application/x-font-ttf', '../fonts/00002.ttf'),
        ('kindle:embed:0002', '../fonts/00002.ttf'),
        ('kindle:embed:0001?mime=image/jpeg', '../images/00001.jpeg'),
        ('kindle:flow:0002?mime=text/css', '../styles/0002.css'),
    ])
    def test_quoting_is_preserved(self, quote, url, expected):
        self.assert_converts('a { b: url(%s%s%s); }' % (quote, url, quote),
                             'a { b: url(%s%s%s); }' % (quote, expected, quote))

    def test_whitespace_inside_url(self):
        self.assert_converts('@import url( "kindle:flow:0001?mime=text/css" );',
                             '@import url("../styles/0001.css");')

    def test_multiple_urls(self):
        self.assert_converts(
            '@font-face { src: url(kindle:embed:0002?mime=font/ttf) format("truetype"), url("kindle:embed:0002") }'
            ' p { background: url(KINDLE:EMBED:0001?mime=image/jpeg) }',
            '@font-face { src: url(../fonts/00002.ttf) format("truetype"), url("../fonts/00002.ttf") }'
            ' p { background: url(../images/00001.jpeg) }',
        )

    def test_extra_query_parameters(self):
        self.assert_converts('url(kindle:embed:0002?foo=1&mime=font/ttf)',
                             'url(../fonts/00002.ttf)')

    def test_style_attribute_is_not_broken(self):
        self.assert_converts(
            '<div style="background: url(kindle:embed:0001?mime=image/jpeg)"/>',
            '<div style="background: url(../images/00001.jpeg)"/>',
        )

    @pytest.mark.parametrize('url,expected_warning', [
        ('url("kindle:embed:0003?mime=font/ttf")', 'Referenced font 3'),
        ('url(kindle:embed:0003?mime=image/png)', 'Referenced image 3'),
        ('url(kindle:embed:0000)', 'Referenced font 0'),
        ('url(kindle:embed:00ZZ)', 'unrecognized'),
        ('url(kindle:embed:00|1)', 'unrecognized'),
        ('url(kindle:embed:0100)', 'Referenced font 1024'),
        ('url(kindle:flow:0003?mime=text/css)', 'invalid flow'),
        ('url(kindle:flow:0000?mime=text/css)', 'invalid flow'),
        ('url(kindle:flow:0100?mime=text/css)', 'invalid flow'),
    ])
    def test_invalid_references_are_preserved_with_warning(self, url, expected_warning):
        output, warnings = self.convert(url)
        assert output == url
        assert len(warnings) == 1, warnings
        assert expected_warning in warnings[0]

    def test_non_kindle_urls_untouched(self):
        self.assert_converts('url(images/x.png) url("kindle.png")',
                             'url(images/x.png) url("kindle.png")')

    def test_bytes_flows_are_decoded(self):
        from ebook_convert.ebooks.mobi.reader.markup import update_flow_links
        reader = SimpleNamespace(
            flows=[None, b'a { b: url(kindle:embed:0001?mime=image/jpeg) }'],
            flowinfo=self.flowinfo, header=SimpleNamespace(codec='utf-8'))
        flows = update_flow_links(reader, self.resource_map, RecordingLog())
        assert flows[1] == 'a { b: url(../images/00001.jpeg) }'


def test_out_of_range_image_references():
    from ebook_convert.ebooks.mobi.reader.markup import insert_images_into_markup
    parts = ['<img src="kindle:embed:0000?mime=image/jpeg"/>'
             '<p style="background: url(kindle:embed:0005)"/>']
    log = RecordingLog()
    insert_images_into_markup(parts, ['images/00001.jpeg'], log)
    assert 'kindle:embed:0000' in parts[0]
    assert 'kindle:embed:0005' in parts[0]
    assert len(log.warnings) == 2, log.warnings


def test_pos_fid_regex_rejects_pipe():
    # [0-9|A-V] used to accept a literal | in base-32 numbers
    from ebook_convert.ebooks.mobi.reader.markup import update_internal_links
    def must_not_be_called(*args):
        raise AssertionError('get_id_tag_by_pos_fid called with %r' % (args,))

    reader = SimpleNamespace(parts=[b'<a href="kindle:pos:fid:00|1:off:0000000000">x</a>'],
                             header=SimpleNamespace(codec='utf-8'),
                             get_id_tag_by_pos_fid=must_not_be_called)
    parts = update_internal_links(reader, RecordingLog())
    assert 'kindle:pos:fid:00|1' in parts[0]

# }}}


# MOBI language codes (Calibre 15c4ba730f and the locale_to_iana rewrite) {{{

@pytest.mark.parametrize('lang,sublang,expected', [
    (0, 0, 'und'),
    (255, 0, 'und'),
    (9, 0, 'en'),
    (9, 4, 'en-us'),
    (7, 0, 'de'),
    (7, 8, 'de-ch'),
    # German has no sub language 4, the region of another language
    # (Arabic: Saudi Arabia) must not be used
    (7, 4, 'de'),
    (25, 8, 'ru'),
    # hr and sr share a langcode
    (26, 0, 'hr'),
    (26, 4, 'hr'),
    (26, 12, 'sr'),
])
def test_mobi2iana(lang, sublang, expected):
    from ebook_convert.ebooks.mobi.langcodes import mobi2iana
    assert mobi2iana(lang, sublang) == expected


@pytest.mark.parametrize('code,expected', [
    ('en', 'en'),
    ('en-US', 'en-us'),
    ('en-CA', 'en-ca'),
    ('de-CH', 'de-ch'),
    ('zh-TW', 'zh-tw'),
    ('sr', 'sr'),
    ('hr', 'hr'),
    ('fr-BE', 'fr-be'),
    (None, 'und'),
])
def test_locale_round_trip(code, expected):
    from ebook_convert.ebooks.mobi.langcodes import iana2mobi, locale_to_iana
    locale, = struct.unpack('>L', iana2mobi(code))
    assert locale_to_iana(locale) == expected

# }}}


# INDX records with an incorrect TAGX offset (Calibre aec2c1a551) {{{

def make_indx(tagx_offset_field, tagx_pos):
    from ebook_convert.ebooks.mobi.reader.index import INDEX_HEADER_FIELDS
    fields = dict.fromkeys(INDEX_HEADER_FIELDS, 0)
    fields['len'] = 4 * (len(INDEX_HEADER_FIELDS) + 1)
    fields['tagx'] = tagx_offset_field
    header = b'INDX' + b''.join(struct.pack('>L', fields[f])
                                for f in INDEX_HEADER_FIELDS)
    # TAGX section: one tag (1, 1, 1, 0) and an end-of-field marker
    tagx = (b'TAGX' + struct.pack('>LL', 20, 1) + bytes([1, 1, 1, 0]) +
            bytes([0, 0, 0, 1]))
    assert tagx_pos >= len(header)
    return header + b'\0' * (tagx_pos - len(header)) + tagx


def test_tagx_offset_is_verified():
    from ebook_convert.ebooks.mobi.reader.index import (
        get_tag_section_start, parse_indx_header, parse_tagx_section)
    real_pos = 4 * (45 + 1) + 16
    for claimed in (real_pos, real_pos - 8, 0, 4):
        data = make_indx(claimed, real_pos)
        hdr = parse_indx_header(data)
        assert hdr['idx_header_end_pos'] == 4 * (45 + 1)
        start = get_tag_section_start(data, hdr)
        assert start == real_pos
        control_byte_count, tags = parse_tagx_section(data[start:])
        assert control_byte_count == 1
        assert [tuple(t) for t in tags] == [(1, 1, 1, 0), (0, 0, 0, 1)]

# }}}


# MOBI Output: colours, guide references and margins (Calibre 47ec4b5521,
# 2a057203e2, fdbffe60fe) {{{

@pytest.mark.parametrize('val,expected', [
    ('currentColor', 'currentColor'),
    ('inherit', 'inherit'),
    ('red', '#ff0000'),
    ('#012', '#001122'),
    ('rgb(10%, 20%, 30%)', '#1a334d'),
    ('rgb(-51, 306, 0)', '#00ff00'),
    ('rgb(var(--x))', 'rgb(var(--x))'),
    # plain numbers used to be returned as-is and later crash the serializer
    (1.5, '1.5'),
    (None, 'None'),
])
def test_convert_color_for_font_tag(val, expected):
    from ebook_convert.ebooks.mobi.utils import convert_color_for_font_tag
    got = convert_color_for_font_tag(val)
    assert got == expected
    assert isinstance(got, str)


def test_is_guide_ref_start_tolerates_missing_title():
    import logging
    from ebook_convert.ebooks.mobi.utils import is_guide_ref_start
    from ebook_convert.ebooks.oeb.base import OEBBook
    guide = OEBBook(logging.getLogger('test'), html_preprocessor=None).guide
    # A non-standard type gets no default title
    assert not is_guide_ref_start(guide.add('foo', None, 'a.html'))
    assert is_guide_ref_start(guide.add('text', 'Main', 'b.html'))
    assert is_guide_ref_start(guide.add('bar', 'Start', 'c.html'))


class FakeStyle:
    """Just enough of oeb.stylizer.Style for convert_margin()."""

    def __init__(self, computed, raw):
        self.computed, self.raw = computed, raw

    def __getitem__(self, name):
        return self.computed[name]

    def _get(self, name):
        return self.raw.get(name)

    def _unit_convert(self, value, base=None):
        try:
            return float(value[:-1]) / 100 * base
        except ValueError:
            # like Stylizer._unit_convert, unparsable values come back as-is
            return value


def test_convert_margin_caps_percentages_at_kindle_width():
    from ebook_convert.ebooks.mobi.mobiml import convert_margin
    # 10% of a 1000px wide (tablet) profile is 100px, but on a 600px Kindle
    # screen it should be at most 60px
    style = FakeStyle({'margin-left': 100.0}, {'margin-left': '10%'})
    assert convert_margin(style, 'margin-left') == 60.0
    # absolute values are untouched
    style = FakeStyle({'margin-left': 12.0}, {'margin-left': '12pt'})
    assert convert_margin(style, 'margin-left') == 12.0
    # invalid % lengths must not raise
    style = FakeStyle({'margin-left': 7.0}, {'margin-left': 'bad%'})
    assert convert_margin(style, 'margin-left') == 7.0
    style = FakeStyle({'margin-left': 'auto'}, {'margin-left': 'auto'})
    assert convert_margin(style, 'margin-left') == 0.0

# }}}


# Right-to-left books and EXTH records (Calibre 4b00f39ef0, 7919f5e9f9 and
# the writer8/exth.py snapshot changes) {{{

@pytest.mark.parametrize('lang,rtl', [
    ('he', True), ('ar', True), ('fa', True), ('ur', True), ('yi', True),
    ('heb', True), ('he-IL', True), ('Hebrew', True),
    ('en', False), ('de', False), ('ja', False), (None, False), ('', False),
])
def test_is_rtl_lang(lang, rtl):
    from ebook_convert.utils.localization import is_rtl_lang
    assert bool(is_rtl_lang(lang)) is rtl


def test_hebrew_book_gets_rtl_page_progression(tmp_path):
    src = tmp_path / 'src'
    shutil.copytree(FIXTURES / 'epub3', src)
    opf = src / 'OEBPS' / 'content.opf'
    opf.write_text(opf.read_text().replace(
        '<dc:language>en</dc:language>', '<dc:language>he</dc:language>'))
    out = tmp_path / 'out.azw3'
    convert(pack_epub(src, tmp_path / 'he.epub'), out)
    data = out.read_bytes()
    assert struct.pack('>II', 527, 8 + 3) + b'rtl' in data
    pwm = b'horizontal-rl'
    assert struct.pack('>II', 525, 8 + len(pwm)) + pwm in data


def test_english_book_has_no_page_progression_record(epub3_path, tmp_path):
    out = tmp_path / 'out.azw3'
    convert(epub3_path, out)
    assert struct.pack('>II', 527, 8 + 3) + b'rtl' not in out.read_bytes()


def test_build_exth_start_offset_int_or_sequence():
    import logging
    from ebook_convert.ebooks.mobi.writer8.exth import build_exth
    from ebook_convert.ebooks.oeb.base import OEBBook
    mi = OEBBook(logging.getLogger('test'), html_preprocessor=None).metadata
    mi.add('title', 'T')
    # a missing date is reported properly (not as an UnboundLocalError)
    with pytest.raises(ValueError):
        build_exth(mi)
    mi.add('date', '2024-01-01T00:00:00+00:00')
    rec = lambda so: struct.pack('>III', 116, 12, so)
    assert rec(5) in build_exth(mi, start_offset=5)
    both = build_exth(mi, start_offset=[5, None, 7])
    assert rec(5) in both and rec(7) in both
    assert rec(5) not in build_exth(mi)

# }}}
