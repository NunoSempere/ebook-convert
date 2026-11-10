"""Tests for MOBI/AZW3 fixes back-ported from Calibre."""
import re
import shutil
import struct
from io import BytesIO

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
