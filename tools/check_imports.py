#!/usr/bin/env python3
"""Import every module under ebook_convert/ and report the ones that fail.

Run from the repository root inside the project virtualenv::

    python tools/check_imports.py [-v]

Exit status is 1 when any module fails to import.  Use this after re-vendoring
to find modules that still need a patch, an exclude entry or an overlay.
"""
from __future__ import annotations

import importlib
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, 'ebook_convert')


def modules():
    for dirpath, dirnames, filenames in os.walk(PKG):
        dirnames[:] = sorted(d for d in dirnames if d not in ('__pycache__', 'data'))
        for fn in sorted(filenames):
            if not fn.endswith('.py'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)[:-3]
            parts = rel.split(os.sep)
            if parts[-1] == '__init__':
                parts = parts[:-1]
            yield '.'.join(parts)


# Modules that need an optional third-party package
OPTIONAL = {
    'ebook_convert.ebooks.unihandecode.jadecoder': 'pykakasi (Japanese transliteration, extra "japanese")',
    'ebook_convert.ebooks.txt.markdownml': 'markdown (extra "markdown")',
}


def main() -> int:
    verbose = '-v' in sys.argv
    sys.path.insert(0, ROOT)
    failures = {}
    count = 0
    for name in modules():
        count += 1
        try:
            importlib.import_module(name)
        except ImportError as e:
            if name in OPTIONAL and getattr(e, 'name', '') and not getattr(e, 'name', '').startswith('ebook_convert'):
                print(f'{name}: optional dependency missing: {OPTIONAL[name]}', file=sys.stderr)
                continue
            failures[name] = e if not verbose else traceback.format_exc()
        except BaseException as e:  # SystemExit from __main__ guards etc.
            failures[name] = e if not verbose else traceback.format_exc()
    for name, err in failures.items():
        print(f'{name}: {err}' if not verbose else f'=== {name}\n{err}')
    print(f'{count - len(failures)}/{count} modules import cleanly', file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
