# License: GPLv3 Copyright: 2024, Kovid Goyal <kovid at kovidgoyal.net>
# ebook-convert: replaces calibre/utils/safe_atexit.py.  Calibre delegates
# cleanup of temporary files to a helper process so that it also happens when
# the main process crashes; we have no worker executable, so clean up with the
# stdlib atexit machinery in this process.

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
from contextlib import suppress
from threading import RLock

RMTREE_ACTION = 'rmtree'
UNLINK_ACTION = 'unlink'
RUN_PROGRAM_ACTION = 'run_program'

_lock = RLock()
_folders: list[str] = []
_files: list[str] = []
_registered = False


def _cleanup() -> None:
    for path in reversed(_files):
        unlink(path)
    for path in reversed(_folders):
        remove_dir(path)


def _ensure_registered() -> None:
    global _registered
    if not _registered:
        _registered = True
        atexit.register(_cleanup)


def remove_folder_atexit(path: str) -> None:
    with _lock:
        _ensure_registered()
        _folders.append(os.path.abspath(path))


def remove_file_atexit(path: str) -> None:
    with _lock:
        _ensure_registered()
        _files.append(os.path.abspath(path))


def run_program_now(cmdline: list[str]) -> None:
    with suppress(Exception):
        subprocess.Popen(cmdline, close_fds=True)


def unlink(path: str) -> None:
    with suppress(Exception):
        if os.path.exists(path):
            os.remove(path)


def remove_dir(path: str) -> None:
    with suppress(Exception):
        shutil.rmtree(path, ignore_errors=True)


def run_program(cmdline: list[str]) -> None:
    run_program_now(cmdline)


def reset_after_fork() -> None:
    global _registered
    with _lock:
        _folders.clear()
        _files.clear()
        _registered = False


def ensure_worker():
    return None


def close_worker(worker) -> None:
    pass
