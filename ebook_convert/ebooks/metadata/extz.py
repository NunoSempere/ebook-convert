"""
Metadata for "extended zip" containers (HTMLZ, TXTZ): a zip archive that
carries a ``metadata.opf`` next to the content, optionally with a cover
image referenced from it.
"""
import os
import posixpath
from io import BytesIO

from ebook_convert.ebooks.metadata.opf2 import OPF, metadata_to_opf
from ebook_convert.ebooks.metadata.book.base import Metadata
from ebook_convert.utils.zipfile import ZipFile, safe_replace


OPF_NAME = 'metadata.opf'


def _opf_name(names):
    for name in names:
        if posixpath.basename(name).lower() == OPF_NAME:
            return name
    return None


def get_metadata(stream, extract_cover=True):
    """Return a :class:`Metadata` built from the archive's ``metadata.opf``."""
    mi = Metadata('Unknown')
    stream.seek(0)
    with ZipFile(stream) as zf:
        names = zf.namelist()
        opf_name = _opf_name(names)
        if opf_name is None:
            return mi
        opf = OPF(BytesIO(zf.read(opf_name)), basedir='')
        mi = opf.to_book_metadata()
        if extract_cover:
            cover_href = opf.raster_cover or opf.cover
            if cover_href:
                cover_name = posixpath.normpath(posixpath.join(
                    posixpath.dirname(opf_name), cover_href))
                if cover_name in names:
                    ext = os.path.splitext(cover_name)[1][1:].lower() or 'jpg'
                    mi.cover_data = (ext, zf.read(cover_name))
    return mi


def set_metadata(stream, mi):
    """Replace the archive's ``metadata.opf`` with ``mi`` (and its cover
    image, if ``mi.cover_data`` is set)."""
    stream.seek(0)
    with ZipFile(stream) as zf:
        names = zf.namelist()
        opf_name = _opf_name(names) or OPF_NAME
        base = posixpath.dirname(opf_name)
        cover_name = None
        if getattr(mi, 'cover_data', None) and mi.cover_data[1]:
            ext = (mi.cover_data[0] or 'jpg').lower().lstrip('.')
            cover_name = posixpath.join(base, 'cover.' + ext) if base \
                else 'cover.' + ext
    if cover_name:
        safe_replace(stream, cover_name, BytesIO(mi.cover_data[1]),
                     add_missing=True)
        mi.cover = posixpath.basename(cover_name)
    stream.seek(0)
    safe_replace(stream, opf_name, BytesIO(metadata_to_opf(mi)),
                 add_missing=True)
