import pathlib
import zipfile

import pytest


FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


@pytest.fixture
def epub3_path(tmp_path):
    """Pack tests/fixtures/epub3 into a .epub file and return its path."""
    src = FIXTURES / 'epub3'
    out = tmp_path / 'book.epub'
    with zipfile.ZipFile(out, 'w') as zf:
        # mimetype must come first and be stored uncompressed
        zf.write(src / 'mimetype', 'mimetype',
                 compress_type=zipfile.ZIP_STORED)
        for path in sorted(src.rglob('*')):
            if path.is_file() and path.name != 'mimetype':
                zf.write(path, str(path.relative_to(src)),
                         compress_type=zipfile.ZIP_DEFLATED)
    return out
