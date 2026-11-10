#!/usr/bin/env python
"""Entry point of the ``ebook-convert`` command.

The command line itself (``ebook-convert INPUT OUTPUT [options]``, with the
input/output format specific options and ``-h`` listing them) is Calibre's own
``calibre.ebooks.conversion.cli``, vendored unchanged apart from the recipe
(news download) support.
"""

from __future__ import annotations

import sys


def main(args: list[str] | None = None) -> int:
    import ebook_convert  # ruff: ignore[unused-import]  initialises builtins, mimetypes, temp dir
    from ebook_convert.ebooks.conversion.cli import main as cli_main

    argv = list(sys.argv if args is None else [sys.argv[0]] + list(args))
    if len(argv) > 1 and argv[1] in ('-V', '--version'):
        from ebook_convert.constants import __appname__, get_version

        print(__appname__, get_version())
        return 0
    return cli_main(argv)


if __name__ == '__main__':
    sys.exit(main())
