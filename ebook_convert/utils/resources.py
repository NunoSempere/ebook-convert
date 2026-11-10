# License: GPLv3 Copyright: 2009, Kovid Goyal <kovid@kovidgoyal.net>
# Trimmed for ebook-convert: replaces calibre/utils/resources.py.  Resource
# paths (``P('templates/fb2.xsl')``, ``I('library.png')``) resolve inside the
# ``ebook_convert/data`` directory that tools/vendor.py fills from Calibre's
# ``resources/`` tree.  There is no user override directory.

from __future__ import annotations

import builtins
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')


def get_path(path: str, data: bool = False, allow_user_override: bool = True) -> str | bytes:
    fpath = os.path.join(DATA_DIR, *path.replace(os.sep, '/').split('/'))
    if data:
        with open(fpath, 'rb') as f:
            return f.read()
    return fpath


def get_image_path(path: str, data: bool = False, allow_user_override: bool = True) -> str | bytes:
    if not path:
        return get_path('images', allow_user_override=allow_user_override)
    return get_path('images/' + path, data=data, allow_user_override=allow_user_override)


def set_data(path: str, data: bytes | None = None) -> None:
    raise NotImplementedError('ebook-convert has no user resource directory')


def get_user_path() -> str | None:
    return None


builtins.__dict__['P'] = get_path
builtins.__dict__['I'] = get_image_path
