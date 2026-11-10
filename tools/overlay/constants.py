# License: GPLv3 Copyright: 2008, Kovid Goyal <kovid@kovidgoyal.net>
# Trimmed for ebook-convert: this replaces calibre/constants.py.  It defines
# the subset of names the vendored conversion code imports, without the
# plugin (C extension) loader, the frozen-build/portable logic or anything Qt.

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager

from ebook_convert._vendored import CALIBRE_COMMIT, CALIBRE_VERSION  # ruff: ignore[unused-import]

__appname__ = 'ebook-convert'
numeric_version = (5, 0, 0)
__version__ = '5.0.0'
__author__ = 'Kovid Goyal <kovid@kovidgoyal.net>'

'''
Various run time constants.
'''

_plat = sys.platform.lower()
iswindows = 'win32' in _plat or 'win64' in _plat
ismacos = isosx = 'darwin' in _plat
isnewosx = ismacos
isfreebsd = 'freebsd' in _plat
isnetbsd = 'netbsd' in _plat
isdragonflybsd = 'dragonfly' in _plat
isbsd = isfreebsd or isnetbsd or isdragonflybsd
ishaiku = 'haiku1' in _plat
islinux = not (iswindows or ismacos or isbsd or ishaiku)
isunix = ismacos or islinux or ishaiku
isfrozen = hasattr(sys, 'frozen')
isportable = False
ispy3 = True
isxp = isoldvista = False
is64bit = sys.maxsize > (1 << 32)
isworker = False

FAKE_PROTOCOL, FAKE_HOST = 'clbr', 'internal.invalid'
SPECIAL_TITLE_FOR_WEBENGINE_COMMS = '__webengine_messages_pending__'
VIEWER_APP_UID = 'com.calibre-ebook.viewer'
EDITOR_APP_UID = 'com.calibre-ebook.edit-book'
MAIN_APP_UID = 'com.calibre-ebook.main-gui'
STORE_DIALOG_APP_UID = 'com.calibre-ebook.store-dialog'
TOC_DIALOG_APP_UID = 'com.calibre-ebook.toc-editor'

try:
    import locale

    preferred_encoding = (locale.getpreferredencoding(False) or 'utf-8').lower()
except Exception:
    preferred_encoding = 'utf-8'
if preferred_encoding in {'ascii', 'ansi_x3.4-1968', 'us-ascii', 'cp65001'}:
    preferred_encoding = 'utf-8'

filesystem_encoding = sys.getfilesystemencoding() or 'utf-8'
if filesystem_encoding.lower() in {'ascii', 'ansi_x3.4-1968', 'us-ascii'}:
    filesystem_encoding = 'utf-8'

DEBUG = bool(os.environ.get('CALIBRE_DEBUG') or os.environ.get('EBOOK_CONVERT_DEBUG'))


def debug(val: object = True) -> None:
    global DEBUG
    DEBUG = bool(val)


def is_debugging() -> bool:
    return DEBUG


def get_version() -> str:
    'Return version string for display to user'
    return f'{__version__} (calibre {CALIBRE_VERSION})'


def get_appname_for_display() -> str:
    return __appname__


def get_portable_base() -> str | None:
    return None


def get_windows_username() -> str:
    return os.environ.get('USERNAME', '') if iswindows else ''


def get_windows_temp_path() -> str:
    return os.environ.get('TEMP', '') if iswindows else ''


def get_windows_user_locale_name() -> str:
    import locale

    return locale.getdefaultlocale()[0] or ''


def get_umask() -> int:
    mask = os.umask(0o22)
    os.umask(mask)
    return mask


def bundled_binaries_dir() -> str:
    return ''


def sanitize_env_vars_in(env):
    return dict(env)


@contextmanager
def sanitize_env_vars():
    yield


# config_dir {{{
CONFIG_DIR_MODE = 0o700

if 'EBOOK_CONVERT_CONFIG_DIRECTORY' in os.environ:
    config_dir = os.path.abspath(os.path.expanduser(os.environ['EBOOK_CONVERT_CONFIG_DIRECTORY']))
elif iswindows:
    config_dir = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'ebook-convert')
elif ismacos:
    config_dir = os.path.expanduser('~/Library/Preferences/ebook-convert')
else:
    bdir = os.path.abspath(os.path.expanduser(os.environ.get('XDG_CONFIG_HOME', '~/.config')))
    config_dir = os.path.join(bdir, 'ebook-convert')

try:
    os.makedirs(config_dir, mode=CONFIG_DIR_MODE, exist_ok=True)
except OSError:
    pass

if not os.path.isdir(config_dir) or not os.access(config_dir, os.W_OK) or not os.access(config_dir, os.X_OK):
    config_dir = tempfile.mkdtemp(prefix='ebook-convert-config-')

    def _cleanup_cdir() -> None:
        shutil.rmtree(config_dir, ignore_errors=True)

    atexit.register(_cleanup_cdir)
# }}}


def _get_cache_dir(create: bool = True) -> str:
    if 'EBOOK_CONVERT_CACHE_DIRECTORY' in os.environ:
        ans = os.path.abspath(os.path.expanduser(os.environ['EBOOK_CONVERT_CACHE_DIRECTORY']))
    elif iswindows:
        ans = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'ebook-convert-cache')
    elif ismacos:
        ans = os.path.expanduser('~/Library/Caches/ebook-convert')
    else:
        ans = os.path.join(os.path.abspath(os.path.expanduser(os.environ.get('XDG_CACHE_HOME', '~/.cache'))), 'ebook-convert')
    if create:
        try:
            os.makedirs(ans, exist_ok=True)
        except OSError:
            ans = os.path.join(tempfile.gettempdir(), 'ebook-convert-cache')
            os.makedirs(ans, exist_ok=True)
    return ans


def cache_dir() -> str:
    return _get_cache_dir()


def existing_cache_dir() -> str:
    return _get_cache_dir(create=False)


# Plugins (Calibre's C extensions).  None are available in this build; code
# that asks for one gets (None, error_message) and must fall back.
class Plugins:
    def __getitem__(self, name: str) -> tuple[None, str]:
        return None, f'C extension {name!r} is not available in ebook-convert'

    def __contains__(self, name: object) -> bool:
        return False

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def get(self, name: str, default=None):
        return default


plugins = Plugins()
plugins_loc = None
system_plugins_loc = None
trash_name = '.trash'
in_develop_mode = False


def is_running_from_develop() -> bool:
    return False


def git_version() -> str:
    return CALIBRE_COMMIT
