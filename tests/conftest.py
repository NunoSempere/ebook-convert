import pathlib
import zipfile

from PIL import Image
import pytest


FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


def pack_epub(src, out, extra=None):
    """Zip the directory ``src`` into the EPUB ``out``.

    ``extra`` maps archive names to bytes (used to add a cover) and
    ``content.opf`` is patched to reference a cover when one is given.
    """
    extra = extra or {}
    with zipfile.ZipFile(out, 'w') as zf:
        # mimetype must come first and be stored uncompressed
        zf.write(src / 'mimetype', 'mimetype',
                 compress_type=zipfile.ZIP_STORED)
        for path in sorted(src.rglob('*')):
            if not path.is_file() or path.name == 'mimetype':
                continue
            name = str(path.relative_to(src))
            data = path.read_bytes()
            if name == 'OEBPS/content.opf' and 'OEBPS/cover.jpg' in extra:
                data = data.replace(
                    b'<manifest>',
                    b'<manifest><item id="cover" href="cover.jpg" '
                    b'media-type="image/jpeg" properties="cover-image"/>'
                ).replace(
                    b'<meta property="dcterms:modified">',
                    b'<meta name="cover" content="cover"/>'
                    b'<meta property="dcterms:modified">')
            zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        for name, data in extra.items():
            zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    return out


@pytest.fixture
def epub3_path(tmp_path):
    """Pack tests/fixtures/epub3 into a .epub file and return its path."""
    return pack_epub(FIXTURES / 'epub3', tmp_path / 'book.epub')


@pytest.fixture
def epub3_with_cover_path(tmp_path):
    """Same book, with a 600x800 JPEG cover image."""
    cover = tmp_path / 'cover.jpg'
    Image.new('RGB', (600, 800), (120, 30, 30)).save(cover, 'JPEG')
    return pack_epub(FIXTURES / 'epub3', tmp_path / 'book-cover.epub',
                     extra={'OEBPS/cover.jpg': cover.read_bytes()})
