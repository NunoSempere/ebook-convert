# License: GPLv3 Copyright: 2008, Kovid Goyal <kovid at kovidgoyal.net>

from __future__ import annotations
import os
from typing import IO, TYPE_CHECKING

from ebook_convert import CurrentDir
from ebook_convert.ptempfile import TemporaryDirectory
from ebook_convert.utils import StreamOrPath
from ebook_convert.utils.zipfile import ZipFile

if TYPE_CHECKING:
    from ebook_convert.ebooks.metadata.book.base import Metadata


def get_metadata(stream: IO[bytes]) -> Metadata:
    from ebook_convert.ebooks.metadata.archive import is_comic
    from ebook_convert.ebooks.metadata.meta import get_metadata

    stream_type = None
    zf = ZipFile(stream, 'r')
    names = zf.namelist()
    if is_comic(names):
        # Is probably a comic
        return get_metadata(stream, 'cbz')

    for f in names:
        stream_type = os.path.splitext(f)[1].lower()
        if stream_type:
            stream_type = stream_type[1:]
            if stream_type in (
                'lit',
                'opf',
                'prc',
                'mobi',
                'fb2',
                'epub',
                'rb',
                'imp',
                'pdf',
                'lrf',
                'azw',
                'azw1',
                'azw3',
            ):
                with TemporaryDirectory() as tdir:
                    with CurrentDir(tdir):
                        path = zf.extract(f)
                        with open(path, 'rb') as f:
                            mi = get_metadata(f, stream_type)
                        if stream_type == 'opf' and mi.application_id is None:
                            try:
                                # zip archive opf files without an application_id were assumed not to have a cover
                                # reparse the opf and if cover exists read its data from zip archive for the metadata
                                nmi = zip_opf_metadata(path, zf)
                                nmi.timestamp = None
                                return nmi
                            except Exception:
                                pass
                        mi.timestamp = None
                        return mi
    raise ValueError('No ebook found in ZIP archive ({})'.format(os.path.basename(getattr(stream, 'name', '') or '<stream>')))


def zip_opf_metadata(opfpath: str, zf: ZipFile) -> Metadata:
    from ebook_convert.ebooks.metadata.opf2 import OPF

    with StreamOrPath(opfpath, 'rb') as f:
        opfpath = getattr(f, 'name', os.getcwd())
        opf = OPF(f, os.path.dirname(opfpath))
    mi = opf.to_book_metadata()
    # This is broken, in that it only works for
    # when both the OPF file and the cover file are in the root of the
    # zip file and the cover is an actual raster image, but I don't care
    # enough to make it more robust
    if mi.cover:
        covername = os.path.basename(mi.cover)
        mi.cover = None
        names = zf.namelist()
        if covername in names:
            fmt = covername.rpartition('.')[-1]
            data = zf.read(covername)
            mi.cover_data = (fmt, data)
    return mi
