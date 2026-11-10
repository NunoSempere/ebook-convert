"""Markdown input: parsing "Series Name [index]" metadata used a helper from
calibre.db (not vendored); inline it."""

TARGET = 'ebooks/txt/processor.py'

REPLACEMENTS = [
    (
        '''    from ebook_convert.db.write import get_series_values
    from ebook_convert.ebooks.metadata.book.base import Metadata
''',
        '''    from ebook_convert.ebooks.metadata.book.base import Metadata

    def get_series_values(val):  # ebook-convert: from calibre.db.write
        import re

        if not val:
            return val, None
        match = re.match(r'(.*)\\s+\\[([.0-9]+)\\]$', val.strip())
        if match is not None:
            try:
                return match.group(1).strip(), float(match.group(2))
            except Exception:
                pass
        return val, None

''',
    ),
]
