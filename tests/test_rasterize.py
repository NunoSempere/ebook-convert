"""SVG rasterization through resvg."""
import pathlib
import shutil
import zipfile
from io import BytesIO

from lxml import etree
from PIL import Image
import pytest

from ebook_convert.ebooks.oeb.transforms import rasterize
from tests.conftest import FIXTURES, pack_epub
from tests.test_convert import convert


SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" '
       'viewBox="0 0 200 100"><rect width="200" height="100" fill="#00f"/>'
       '<circle cx="50" cy="50" r="40" fill="#f00"/></svg>')


def test_renderer_available():
    assert rasterize.renderer_available()


def test_intrinsic_size_and_fit():
    root = etree.fromstring(SVG)
    assert rasterize.svg_intrinsic_size(root) == (200, 100)
    root = etree.fromstring('<svg xmlns="http://www.w3.org/2000/svg" '
                            'viewBox="0 0 40 20"/>')
    assert rasterize.svg_intrinsic_size(root) == (40, 20)
    root = etree.fromstring('<svg xmlns="http://www.w3.org/2000/svg" '
                            'width="2in" viewBox="0 0 40 20"/>')
    assert rasterize.svg_intrinsic_size(root) == (192, 96)
    root = etree.fromstring('<svg xmlns="http://www.w3.org/2000/svg"/>')
    assert rasterize.svg_intrinsic_size(root) == (100, 100)
    assert rasterize.fit_size((200, 100), 100, 100) == (100, 50)
    assert rasterize.fit_size((200, 100), 0, 300) == (600, 300)
    assert rasterize.fit_size((200, 100)) == (200, 100)


def test_render_svg_to_png():
    png = rasterize.render_svg(SVG.encode('utf-8'), 400, 400)
    im = Image.open(BytesIO(png))
    assert im.format == 'PNG'
    assert im.size == (400, 200)
    assert im.getpixel((100, 100))[:3] == (255, 0, 0)   # circle
    assert im.getpixel((390, 10))[:3] == (0, 0, 255)    # rect
    png = rasterize.render_svg(SVG, size=(200, 100))
    assert Image.open(BytesIO(png)).size == (200, 100)


@pytest.fixture
def epub_with_svg_path(tmp_path):
    """EPUB 3 fixture plus an external SVG referenced by <img> and used as
    the cover image; chapter 1 already carries an inline <svg>."""
    src = tmp_path / 'epub3'
    shutil.copytree(FIXTURES / 'epub3', src)
    (src / 'OEBPS' / 'fig.svg').write_text(SVG, encoding='utf-8')
    opf = src / 'OEBPS' / 'content.opf'
    text = opf.read_text(encoding='utf-8')
    text = text.replace(
        '<manifest>',
        '<manifest><item id="fig" href="fig.svg" media-type="image/svg+xml" '
        'properties="cover-image"/>')
    text = text.replace('<meta property="dcterms:modified">',
                        '<meta name="cover" content="fig"/>'
                        '<meta property="dcterms:modified">')
    opf.write_text(text, encoding='utf-8')
    ch2 = src / 'OEBPS' / 'ch2.xhtml'
    ch2.write_text(ch2.read_text(encoding='utf-8').replace(
        '</p></body>', '</p><p><img src="fig.svg" alt="figure"/></p></body>'),
        encoding='utf-8')
    return pack_epub(src, tmp_path / 'svg.epub')


@pytest.mark.parametrize('ext', ['mobi', 'docx', 'fb2'])
def test_svg_is_rasterized_for_formats_without_svg(epub_with_svg_path,
                                                   tmp_path, ext):
    out = tmp_path / ('out.' + ext)
    proc = convert(epub_with_svg_path, out, '-v')
    assert 'rasterizer unavailable' not in proc.stderr
    assert 'Rasterizing' in proc.stderr
    data = out.read_bytes()
    if ext == 'docx':
        with zipfile.ZipFile(out) as zf:
            media = [n for n in zf.namelist() if n.startswith('word/media/')]
        assert any(n.endswith('.png') for n in media)
        assert not any(n.endswith('.svg') for n in media)
    elif ext == 'fb2':
        assert b'image/png' in data
    else:
        assert b'\x89PNG' in data or b'GIF8' in data


def test_epub_output_keeps_svg(epub_with_svg_path, tmp_path):
    out = tmp_path / 'out.epub'
    convert(epub_with_svg_path, out)
    with zipfile.ZipFile(out) as zf:
        assert any(n.endswith('fig.svg') for n in zf.namelist())
