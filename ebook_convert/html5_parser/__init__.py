"""Drop-in for the ``html5-parser`` C extension that Calibre uses.

Implemented with html5lib in :mod:`ebook_convert.utils.html5`; the import
``from html5_parser import parse`` in vendored code is rewritten to this
package by tools/vendor.py.
"""

from ebook_convert.utils.html5 import parse  # ruff: ignore[unused-import]

__all__ = ('parse',)
