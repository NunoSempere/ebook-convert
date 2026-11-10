"""Pure-Python stand-ins for the Calibre C extensions the conversion code uses.

Calibre ships a dozen C/C++ extensions under ``calibre_extensions``.
``tools/vendor.py`` rewrites ``from calibre_extensions import X`` to point
here.  Only the extensions the pipeline needs at import time or on common
paths have a Python implementation (``speedup``, ``fast_html_entities``,
``cPalmdoc``, ``uchardet``, ``translator``); importing any other name raises
``ImportError`` so that Calibre's own fallbacks (e.g. tinycss' Python
tokenizer) kick in.
"""
