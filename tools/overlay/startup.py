# License: GPLv3 Copyright: 2008, Kovid Goyal kovid@kovidgoyal.net
# Trimmed for ebook-convert: replaces calibre/startup.py.  It performs the
# process-wide initialisation the vendored code relies on (builtins such as
# ``_`` and ``P``, the temp-file base directory, mimetypes) and nothing else
# (no multiprocessing patches, no Qt, no C extensions).

from __future__ import annotations

import builtins
import locale

# Default translation is NOOP
builtins.__dict__['_'] = lambda s: s

# For strings which belong in the translation tables, but which shouldn't be
# immediately translated to the environment language
builtins.__dict__['__'] = lambda s: s

builtins.__dict__['ngettext'] = lambda singular, plural, n: singular if n == 1 else plural

# For backwards compat with some third party plugins
builtins.__dict__['dynamic_property'] = lambda func: func(None)

_calibre_initialized = False


def initialize_calibre() -> None:
    global _calibre_initialized
    if _calibre_initialized:
        return
    _calibre_initialized = True

    # Ensure that all temp files/dirs are created under our own tmp dir, which
    # is removed at exit
    from ebook_convert.ptempfile import fix_tempfile_module

    fix_tempfile_module()

    # Setup resources: installs the P() and I() builtins
    from ebook_convert.utils import resources  # ruff: ignore[unused-import]

    # Setup translations: installs the (NOOP) _ and ngettext builtins
    from ebook_convert.utils.localization import set_translators

    set_translators()

    # Register the ebook mimetypes with the stdlib mimetypes module so that
    # mimetypes.guess_type() knows about .epub, .mobi, .azw3 ...
    import mimetypes

    mimetypes.init([resources.get_path('mime.types')])

    import string  # ruff: ignore[unused-import]

    try:
        locale.setlocale(locale.LC_ALL, '')
    except Exception:
        pass

    builtins.__dict__['lopen'] = open  # legacy compatibility
    from ebook_convert.utils.icu import lower as icu_lower
    from ebook_convert.utils.icu import title_case
    from ebook_convert.utils.icu import upper as icu_upper

    builtins.__dict__['icu_lower'] = icu_lower
    builtins.__dict__['icu_upper'] = icu_upper
    builtins.__dict__['icu_title'] = title_case
