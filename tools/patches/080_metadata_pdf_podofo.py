"""ebooks/metadata/pdf.py: writing PDF metadata needs the PoDoFo C++
extension; make the import lazy so reading PDF metadata (pdfinfo) still
works."""

TARGET = 'ebooks/metadata/pdf.py'

REPLACEMENTS = [
    (
        '''from ebook_convert.utils.podofo import set_metadata as podofo_set_metadata


def set_metadata(stream: IO[bytes], mi: Metadata) -> None:
    stream.seek(0)
    return podofo_set_metadata(stream, mi)
''',
        '''def set_metadata(stream: IO[bytes], mi: Metadata) -> None:
    # ebook-convert: PoDoFo is not available
    raise NotImplementedError('Writing PDF metadata needs the PoDoFo extension, which ebook-convert does not include')
''',
    ),
]
