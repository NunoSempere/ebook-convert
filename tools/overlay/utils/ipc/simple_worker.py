"""In-process replacement for calibre.utils.ipc.simple_worker.

Calibre runs some jobs (reading PDF metadata with pdfinfo, exploding AZW3
files) in a separate worker process started through its own launcher.
ebook-convert has no worker executable, so ``fork_job`` imports the module and
calls the function in this process, taking care of the two side effects a
separate process would have isolated: the current directory is restored and
anything printed is captured into a file (``result['stdout_stderr']``), as the
callers expect.  Only the pieces of the API the vendored code uses exist.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import tempfile
import traceback


class WorkerError(Exception):
    def __init__(self, msg: str, orig_tb: str = '', log_path: str | None = None) -> None:
        Exception.__init__(self, msg)
        self.orig_tb = orig_tb
        self.log_path = log_path


def fork_job(mod_name: str, func_name: str, args=(), kwargs=None, timeout=300, abort=None, module_is_source_code=False, env=None, no_output=False, heartbeat=None):
    if mod_name.startswith('calibre.'):
        mod_name = 'ebook_convert.' + mod_name[len('calibre.') :]
    cwd = os.getcwd()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            mod = importlib.import_module(mod_name)
            result = getattr(mod, func_name)(*args, **(kwargs or {}))
    except Exception as e:
        raise WorkerError(f'{mod_name}.{func_name} failed: {e}', traceback.format_exc()) from e
    finally:
        with contextlib.suppress(OSError):
            os.chdir(cwd)
    log_path = None
    if not no_output:
        from ebook_convert.ptempfile import base_dir

        fd, log_path = tempfile.mkstemp(suffix='.log', prefix='worker-', dir=base_dir())
        with os.fdopen(fd, 'w', encoding='utf-8', errors='replace') as f:
            f.write(buf.getvalue())
    return {'result': result, 'stdout_stderr': log_path}


def start_pipe_worker(*a, **kw):
    raise WorkerError('Worker processes are not available in ebook-convert')


def offload_worker(*a, **kw):
    raise WorkerError('Worker processes are not available in ebook-convert')
