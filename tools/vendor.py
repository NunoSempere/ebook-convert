#!/usr/bin/env python3
"""Vendor Calibre's conversion pipeline into the ``ebook_convert`` package.

Usage::

    python tools/vendor.py /path/to/calibre/checkout [--out ebook_convert]
    python tools/vendor.py --check [--out ebook_convert]

The script is deterministic and uses only the standard library.  It

1. copies an explicit include list of files/directories out of the Calibre
   checkout (``INCLUDE``),
2. deletes an explicit exclude list (``EXCLUDE``) plus all non-Python junk,
3. rewrites imports (``calibre.`` -> ``ebook_convert.``, ``polyglot.`` ->
   ``ebook_convert.polyglot.`` ...),
4. applies syntax transforms so the Python 3.14 code base also runs on
   Python 3.12/3.13 (``except A, B:`` -> ``except (A, B):``,
   ``from compression import zlib`` -> ``import zlib``, type parameter
   defaults ``class C[T = str]`` -> ``class C[T]``, and
   ``from __future__ import annotations`` for the deferred annotations
   Calibre relies on),
5. applies the ordered patch rules in ``tools/patches/*.py`` (small exact
   text replacements; a rule that does not match is an error so that
   re-vendoring against a newer Calibre fails loudly instead of silently),
6. copies the hand-written shims in ``tools/overlay/`` over the tree,
7. writes ``ebook_convert/_vendored.py`` with the Calibre commit used.

``--check`` scans the generated tree for imports that were not rewritten
(``calibre``, ``polyglot``, ``qt.core``, ``PyQt``, ``calibre_extensions`` ...).
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import importlib.util
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PATCHES_DIR = os.path.join(HERE, 'patches')
OVERLAY_DIR = os.path.join(HERE, 'overlay')

# --------------------------------------------------------------------------
# What to copy: (path inside the calibre checkout, path inside the package)
# --------------------------------------------------------------------------
INCLUDE = [
    # top-level helpers
    ('src/calibre/__init__.py', '__init__.py'),
    ('src/calibre/ptempfile.py', 'ptempfile.py'),
    ('src/calibre/prints.py', 'prints.py'),
    ('src/calibre/libunzip.py', 'libunzip.py'),
    # plugin system
    ('src/calibre/customize', 'customize'),
    # the conversion pipeline itself
    ('src/calibre/ebooks', 'ebooks'),
    # bits of the library layer that Metadata objects depend on
    ('src/calibre/library/__init__.py', 'library/__init__.py'),
    ('src/calibre/library/field_metadata.py', 'library/field_metadata.py'),
    ('src/calibre/library/comments.py', 'library/comments.py'),
    ('src/calibre/spell/__init__.py', 'spell/__init__.py'),
    ('src/calibre/translations/__init__.py', 'translations/__init__.py'),
    ('src/calibre/translations/dynamic.py', 'translations/dynamic.py'),
    # utilities (explicit list: utils/ is full of GUI/server/device code)
    ('src/calibre/utils/__init__.py', 'utils/__init__.py'),
    ('src/calibre/utils/cleantext.py', 'utils/cleantext.py'),
    ('src/calibre/utils/config.py', 'utils/config.py'),
    ('src/calibre/utils/config_base.py', 'utils/config_base.py'),
    ('src/calibre/utils/date.py', 'utils/date.py'),
    ('src/calibre/utils/ffml_processor.py', 'utils/ffml_processor.py'),
    ('src/calibre/utils/filenames.py', 'utils/filenames.py'),
    ('src/calibre/utils/fonts/__init__.py', 'utils/fonts/__init__.py'),
    ('src/calibre/utils/fonts/metadata.py', 'utils/fonts/metadata.py'),
    ('src/calibre/utils/fonts/scanner.py', 'utils/fonts/scanner.py'),
    ('src/calibre/utils/fonts/subset.py', 'utils/fonts/subset.py'),
    ('src/calibre/utils/fonts/utils.py', 'utils/fonts/utils.py'),
    ('src/calibre/utils/fonts/sfnt', 'utils/fonts/sfnt'),
    ('src/calibre/utils/formatter.py', 'utils/formatter.py'),
    ('src/calibre/utils/formatter_functions.py', 'utils/formatter_functions.py'),
    ('src/calibre/utils/html2text.py', 'utils/html2text.py'),
    ('src/calibre/utils/imghdr.py', 'utils/imghdr.py'),
    ('src/calibre/utils/ipc/__init__.py', 'utils/ipc/__init__.py'),
    ('src/calibre/utils/iso8601.py', 'utils/iso8601.py'),
    ('src/calibre/utils/localization.py', 'utils/localization.py'),
    ('src/calibre/utils/localunzip.py', 'utils/localunzip.py'),
    ('src/calibre/utils/lock.py', 'utils/lock.py'),
    ('src/calibre/utils/logging.py', 'utils/logging.py'),
    ('src/calibre/utils/monotonic.py', 'utils/monotonic.py'),
    ('src/calibre/utils/mreplace.py', 'utils/mreplace.py'),
    ('src/calibre/utils/ordered_dict.py', 'utils/ordered_dict.py'),
    ('src/calibre/utils/safe_atexit.py', 'utils/safe_atexit.py'),
    ('src/calibre/utils/serialize.py', 'utils/serialize.py'),
    ('src/calibre/utils/shared_file.py', 'utils/shared_file.py'),
    ('src/calibre/utils/short_uuid.py', 'utils/short_uuid.py'),
    ('src/calibre/utils/smartypants.py', 'utils/smartypants.py'),
    ('src/calibre/utils/speedups.py', 'utils/speedups.py'),
    ('src/calibre/utils/terminal.py', 'utils/terminal.py'),
    ('src/calibre/utils/text2int.py', 'utils/text2int.py'),
    ('src/calibre/utils/titlecase.py', 'utils/titlecase.py'),
    ('src/calibre/utils/unsmarten.py', 'utils/unsmarten.py'),
    ('src/calibre/utils/wordcount.py', 'utils/wordcount.py'),
    ('src/calibre/utils/xml_parse.py', 'utils/xml_parse.py'),
    ('src/calibre/utils/zipfile.py', 'utils/zipfile.py'),
    # pure-Python sibling packages that live next to calibre/ in src/
    ('src/polyglot', 'polyglot'),
    ('src/tinycss', 'tinycss'),
    ('src/css_selectors', 'css_selectors'),
    # resources (P() paths are kept relative to data/)
    ('resources/mime.types', 'data/mime.types'),
    ('resources/default_tweaks.py', 'data/default_tweaks.py'),
    ('resources/templates/fb2.xsl', 'data/templates/fb2.xsl'),
    ('resources/templates/lrf.xsl', 'data/templates/lrf.xsl'),
    ('resources/templates/rtf.xsl', 'data/templates/rtf.xsl'),
    ('resources/templates/html.css', 'data/templates/html.css'),
    ('resources/templates/kobo.js', 'data/templates/kobo.js'),
    ('resources/templates/new_nav.html', 'data/templates/new_nav.html'),
    ('resources/templates/new_book.html', 'data/templates/new_book.html'),
    ('resources/templates/inline_toc_styles.css', 'data/templates/inline_toc_styles.css'),
    ('resources/templates/html_export_default.css', 'data/templates/html_export_default.css'),
    ('resources/templates/html_export_default.mustache', 'data/templates/html_export_default.mustache'),
    ('resources/templates/html_export_default_index.mustache', 'data/templates/html_export_default_index.mustache'),
    ('resources/jacket', 'data/jacket'),
    ('resources/images/library.png', 'data/images/library.png'),
    ('resources/images/blank.png', 'data/images/blank.png'),
    ('resources/images/lt.png', 'data/images/lt.png'),
    ('resources/fonts/calibreSymbols.otf', 'data/fonts/calibreSymbols.otf'),
]

# --------------------------------------------------------------------------
# What to delete afterwards (fnmatch globs on paths relative to the package).
# Everything here needs Qt, a Calibre C extension, the calibre database/GUI/
# server, or is editor/viewer-only.
# --------------------------------------------------------------------------
EXCLUDE = [
    # needs lzx/msdes C extensions
    'ebooks/lit', 'ebooks/lit/*',
    'ebooks/conversion/plugins/lit_input.py', 'ebooks/conversion/plugins/lit_output.py',
    # needs the chm C library
    'ebooks/chm', 'ebooks/chm/*', 'ebooks/conversion/plugins/chm_input.py',
    # needs the bzzdec C extension
    'ebooks/djvu', 'ebooks/djvu/*', 'ebooks/conversion/plugins/djvu_input.py',
    # needs Qt (image processing) and unrar
    'ebooks/comic', 'ebooks/comic/*', 'ebooks/conversion/plugins/comic_input.py',
    # recipes need calibre.web (the news download framework)
    'ebooks/conversion/plugins/recipe_input.py',
    # PDF output renders with Qt WebEngine and PoDoFo
    'ebooks/conversion/plugins/pdf_output.py',
    'ebooks/pdf/html_writer.py', 'ebooks/pdf/image_writer.py', 'ebooks/pdf/develop.py',
    'ebooks/pdf/render', 'ebooks/pdf/render/*', 'ebooks/pdf/utils.h',
    # viewer / editor only
    'ebooks/iterator', 'ebooks/iterator/*',
    'ebooks/oeb/iterator', 'ebooks/oeb/iterator/*',
    'ebooks/oeb/display', 'ebooks/oeb/display/*',
    'ebooks/readability', 'ebooks/readability/*',
    'ebooks/render_html.py', 'ebooks/tweak.py', 'ebooks/mobi/tweak.py',
    # Tweak Book editor tools (Qt, hunspell, TTS, network)
    'ebooks/oeb/polish/check', 'ebooks/oeb/polish/check/*',
    'ebooks/oeb/polish/tts.py', 'ebooks/oeb/polish/spell.py',
    'ebooks/oeb/polish/download.py',
    'ebooks/oeb/polish/main.py', 'ebooks/oeb/polish/report.py',
    'ebooks/oeb/polish/stats.py', 'ebooks/oeb/polish/import_book.py',
    'ebooks/oeb/polish/hyphenation.py', 'ebooks/oeb/polish/tests', 'ebooks/oeb/polish/tests/*',
    # metadata download (network, Qt) and ipc workers
    'ebooks/metadata/sources', 'ebooks/metadata/sources/*',
    'ebooks/metadata/worker.py',
    # needs mechanize (network), unrar, calibre.db
    'ebooks/metadata/kdl.py', 'ebooks/metadata/rar.py', 'ebooks/metadata/book/render.py',
    # C sources and tests
    '*.c', '*.h', '*.cpp', '*.m', '*.rst',
    '*_test.py', 'test_*.py', '*/tests', '*/tests/*', 'ebooks/docx/writer/tests.py',
    'ebooks/metadata/test_author_sort.py',
    'tinycss/tests', 'tinycss/tests/*',
    # Calibre's own (Qt-based / C-extension based) implementations that the
    # overlay replaces
    'utils/icu.py', 'utils/img.py', 'ebooks/covers.py',
    'ebooks/oeb/transforms/rasterize.py',
]

# Modules whose imports get rewritten to live inside ebook_convert
MODULE_MAP = {
    'calibre_extensions': 'ebook_convert.calibre_extensions',
    'calibre': 'ebook_convert',
    'polyglot': 'ebook_convert.polyglot',
    'tinycss': 'ebook_convert.tinycss',
    'css_selectors': 'ebook_convert.css_selectors',
    'html5_parser': 'ebook_convert.html5_parser',
}
_MOD_ALTERNATION = '|'.join(sorted(MODULE_MAP, key=len, reverse=True))
RE_FROM = re.compile(r'^(\s*from\s+)(%s)(\.[\w.]+)?(\s+import\b)' % _MOD_ALTERNATION)
RE_IMPORT = re.compile(r'^(\s*import\s+)(%s)(\.[\w.]+)?(\s*(?:as\s+\w+)?\s*(?:#.*)?)$' % _MOD_ALTERNATION)
# Dotted module names in strings (fork_job targets, importlib.import_module)
RE_STRING_MODULE = re.compile(r"""(['"])calibre(\.[\w.]+)\1""")

CHECK_PATTERNS = [
    re.compile(r'^\s*(from|import)\s+(calibre|polyglot|tinycss|css_selectors|html5_parser|calibre_extensions)\b'),
    re.compile(r'^\s*(from|import)\s+(qt\.|PyQt\d|PySide\d)'),
    re.compile(r"""['"]calibre\.[\w.]+['"]"""),
]

RE_EXCEPT_TUPLE = re.compile(r'^(\s*)except\s+([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)+)(\s+as\s+\w+)?\s*:')
RE_COMPRESSION = re.compile(r'^(\s*)from compression import ([\w, ]+)$')
# PEP 696 type parameter defaults (``class Foo[T = str]:``) are Python 3.13+
RE_TYPEPARAMS = re.compile(r'^(\s*(?:class|def)\s+\w+)\[([^\]]*=[^\]]*)\]')


def log(*a):
    print(*a, file=sys.stderr)


# --------------------------------------------------------------------------
# copying
# --------------------------------------------------------------------------
def copy_tree(src_root, out_dir):
    copied = 0
    for src_rel, dst_rel in INCLUDE:
        src = os.path.join(src_root, src_rel)
        dst = os.path.join(out_dir, dst_rel)
        if not os.path.exists(src):
            raise SystemExit('Missing in Calibre checkout: %s' % src_rel)
        if os.path.isdir(src):
            for dirpath, dirnames, filenames in os.walk(src):
                dirnames[:] = [d for d in dirnames if d != '__pycache__']
                rel = os.path.relpath(dirpath, src)
                for fn in filenames:
                    if fn.endswith(('.pyc', '.pyo')):
                        continue
                    d = os.path.join(dst, rel, fn) if rel != '.' else os.path.join(dst, fn)
                    os.makedirs(os.path.dirname(d), exist_ok=True)
                    shutil.copyfile(os.path.join(dirpath, fn), d)
                    copied += 1
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            copied += 1
    return copied


def excluded(rel):
    rel = rel.replace(os.sep, '/')
    for pat in EXCLUDE:
        if fnmatch.fnmatchcase(rel, pat):
            return True
    return False


def prune(out_dir):
    removed = 0
    for dirpath, dirnames, filenames in os.walk(out_dir, topdown=False):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, out_dir)
            if excluded(rel) or any(part == '__pycache__' for part in rel.split(os.sep)):
                os.remove(p)
                removed += 1
                continue
            if not rel.startswith('data' + os.sep) and not fn.endswith('.py'):
                # only Python code outside data/
                os.remove(p)
                removed += 1
        for dn in dirnames:
            p = os.path.join(dirpath, dn)
            if os.path.isdir(p) and not os.listdir(p):
                os.rmdir(p)
    return removed


# --------------------------------------------------------------------------
# text transforms
# --------------------------------------------------------------------------
def rewrite_imports(text):
    out = []
    for line in text.split('\n'):
        m = RE_FROM.match(line)
        if m:
            line = m.group(1) + MODULE_MAP[m.group(2)] + (m.group(3) or '') + line[m.end(3) if m.group(3) else m.end(2):]
        else:
            m = RE_IMPORT.match(line)
            if m:
                rest = m.group(4)
                if not m.group(3) and 'as ' not in rest:
                    # ``import tinycss`` must keep binding the name ``tinycss``
                    rest = ' as ' + m.group(2) + rest
                line = m.group(1) + MODULE_MAP[m.group(2)] + (m.group(3) or '') + rest
        line = RE_STRING_MODULE.sub(lambda mm: mm.group(1) + 'ebook_convert' + mm.group(2) + mm.group(1), line)
        out.append(line)
    return '\n'.join(out)


def fix_syntax_for_312(text):
    """Make Python 3.14 syntax work on 3.12/3.13."""
    out = []
    for line in text.split('\n'):
        m = RE_EXCEPT_TUPLE.match(line)
        if m:
            line = '%sexcept (%s)%s:%s' % (m.group(1), m.group(2), m.group(3) or '', line[m.end():])
        m = RE_COMPRESSION.match(line)
        if m:
            names = [x.strip() for x in m.group(2).split(',') if x.strip()]
            line = '\n'.join('%simport %s' % (m.group(1), n) for n in names)
        m = RE_TYPEPARAMS.match(line)
        if m:
            params = ', '.join(p.split('=')[0].strip() for p in m.group(2).split(','))
            line = '%s[%s]%s' % (m.group(1), params, line[m.end():])
        out.append(line)
    return '\n'.join(out)


def add_future_annotations(text, path):
    if 'from __future__ import annotations' in text:
        return text
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        raise SystemExit('Cannot parse %s after transforms: %s' % (path, e))
    body = tree.body
    if not body:
        return text
    idx = 0
    if isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], 'value', None), ast.Constant) and isinstance(body[0].value.value, str):
        idx = 1
    if idx >= len(body):
        return text
    first = body[idx]
    lineno = first.lineno
    if isinstance(first, ast.ImportFrom) and first.module == '__future__':
        return text
    lines = text.split('\n')
    # insert before any decorators/comments directly attached to the stmt
    if hasattr(first, 'decorator_list') and first.decorator_list:
        lineno = first.decorator_list[0].lineno
    lines.insert(lineno - 1, 'from __future__ import annotations')
    return '\n'.join(lines)


def transform_python(out_dir):
    n = 0
    for dirpath, dirnames, filenames in os.walk(out_dir):
        if os.path.relpath(dirpath, out_dir).startswith('data'):
            continue
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(dirpath, fn)
            with open(p, encoding='utf-8') as f:
                text = f.read()
            new = rewrite_imports(text)
            new = fix_syntax_for_312(new)
            new = add_future_annotations(new, p)
            if new != text:
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(new)
                n += 1
    return n


# --------------------------------------------------------------------------
# patches
# --------------------------------------------------------------------------
def load_patch_modules():
    mods = []
    for fn in sorted(os.listdir(PATCHES_DIR)):
        if not fn.endswith('.py') or fn.startswith('_'):
            continue
        spec = importlib.util.spec_from_file_location('patch_' + fn[:-3], os.path.join(PATCHES_DIR, fn))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.__patch_name__ = fn
        mods.append(mod)
    return mods


def apply_patches(out_dir):
    applied = 0
    for mod in load_patch_modules():
        targets = getattr(mod, 'TARGETS', None) or [mod.TARGET]
        for target in targets:
            p = os.path.join(out_dir, target)
            if not os.path.exists(p):
                if getattr(mod, 'OPTIONAL', False):
                    continue
                raise SystemExit('%s: target %s does not exist' % (mod.__patch_name__, target))
            with open(p, encoding='utf-8') as f:
                text = f.read()
            for old, new in getattr(mod, 'REPLACEMENTS', ()):
                count = text.count(old)
                if count != 1:
                    raise SystemExit('%s: expected exactly one match in %s, found %d for:\n%s' % (mod.__patch_name__, target, count, old))
                text = text.replace(old, new)
            if hasattr(mod, 'apply'):
                text = mod.apply(text)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
            applied += 1
    return applied


def apply_overlay(out_dir):
    replaced, added = [], []
    for dirpath, dirnames, filenames in os.walk(OVERLAY_DIR):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for fn in filenames:
            if fn.endswith(('.pyc', '.pyo')):
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, OVERLAY_DIR)
            dst = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            (replaced if os.path.exists(dst) else added).append(rel)
            shutil.copyfile(src, dst)
    return replaced, added


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------
def git_head(src_root):
    head = os.path.join(src_root, '.git', 'HEAD')
    try:
        with open(head) as f:
            ref = f.read().strip()
    except OSError:
        return 'unknown'
    if ref.startswith('ref: '):
        refname = ref[5:]
        p = os.path.join(src_root, '.git', refname)
        if os.path.exists(p):
            with open(p) as f:
                return f.read().strip()
        packed = os.path.join(src_root, '.git', 'packed-refs')
        if os.path.exists(packed):
            with open(packed) as f:
                for line in f:
                    parts = line.split()
                    if len(parts) == 2 and parts[1] == refname:
                        return parts[0]
        return 'unknown'
    return ref


def calibre_version(src_root):
    with open(os.path.join(src_root, 'src', 'calibre', 'constants.py'), encoding='utf-8') as f:
        m = re.search(r'^numeric_version\s*=\s*\(([^)]*)\)', f.read(), re.M)
    return '.'.join(x.strip() for x in m.group(1).split(',')) if m else 'unknown'


def write_provenance(out_dir, src_root, commit):
    with open(os.path.join(out_dir, '_vendored.py'), 'w', encoding='utf-8') as f:
        f.write('# Generated by tools/vendor.py; do not edit.\n')
        f.write('CALIBRE_COMMIT = %r\n' % commit)
        f.write('CALIBRE_VERSION = %r\n' % calibre_version(src_root))


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------
def check(out_dir):
    """Report imports of calibre/Qt/C-extension modules left in the tree.

    Unindented (module level) imports are errors: the module cannot be
    imported.  Indented ones sit inside functions or ``if TYPE_CHECKING:``
    blocks and only matter if that code path runs; they are listed as lazy.
    """
    toplevel, lazy = [], []
    for dirpath, dirnames, filenames in os.walk(out_dir):
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(dirpath, fn)
            with open(p, encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    for pat in CHECK_PATTERNS:
                        if pat.search(line):
                            entry = '%s:%d: %s' % (os.path.relpath(p, out_dir), i, line.strip())
                            (lazy if line[:1].isspace() else toplevel).append(entry)
                            break
    for e in toplevel:
        print('ERROR (module level):', e)
    for e in lazy:
        print('lazy (runtime only): ', e)
    log('%d module-level problem(s), %d lazy reference(s)' % (len(toplevel), len(lazy)))
    return 1 if toplevel else 0


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('calibre', nargs='?', help='path to a Calibre git checkout')
    ap.add_argument('--out', default=os.path.join(ROOT, 'ebook_convert'), help='output package directory')
    ap.add_argument('--check', action='store_true', help='only scan the output for unrewritten imports')
    ap.add_argument('--commit', help='record this Calibre commit instead of reading .git/HEAD')
    args = ap.parse_args()

    if args.check and not args.calibre:
        return check(args.out)
    if not args.calibre:
        ap.error('path to the Calibre checkout is required')
    src_root = os.path.abspath(args.calibre)
    if not os.path.isdir(os.path.join(src_root, 'src', 'calibre')):
        raise SystemExit('%s does not look like a Calibre checkout' % src_root)

    out_dir = os.path.abspath(args.out)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    copied = copy_tree(src_root, out_dir)
    removed = prune(out_dir)
    transformed = transform_python(out_dir)
    patched = apply_patches(out_dir)
    replaced, added = apply_overlay(out_dir)
    commit = args.commit or git_head(src_root)
    write_provenance(out_dir, src_root, commit)
    log('calibre commit: %s (version %s)' % (commit, calibre_version(src_root)))
    log('files copied: %d, removed by exclude list: %d, import/syntax rewritten: %d' % (copied, removed, transformed))
    log('patch rules applied: %d, overlay files: %d replaced, %d added' % (patched, len(replaced), len(added)))
    log('replaced by overlay: ' + ', '.join(sorted(replaced)))
    if args.check:
        return check(out_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
