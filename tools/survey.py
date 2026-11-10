#!/usr/bin/env python3
"""Exercise every registered input and output plugin with a real conversion.

Converts the EPUB test fixture to every output format, then converts each
result back to EPUB (which exercises the matching input plugin) and checks
that the chapter text survived.  Prints a table; exit status 1 if anything
failed.  Run inside the project environment::

    uv run python tools/survey.py [workdir]
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.conftest import FIXTURES, pack_epub  # noqa: E402

MARKER = 'Chapter One'


def run(src, dst, *args):
    proc = subprocess.run([sys.executable, '-m', 'ebook_convert.main', str(src), str(dst)] + list(args), capture_output=True, text=True, timeout=600)
    return proc


def epub_text(path):
    with zipfile.ZipFile(path) as zf:
        return b''.join(zf.read(n) for n in zf.namelist() if n.endswith(('.html', '.xhtml', '.htm'))).decode('utf-8', 'replace')


def main():
    work = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(tempfile.mkdtemp(prefix='ebook-convert-survey-'))
    work.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    cover = work / 'cover.jpg'
    Image.new('RGB', (600, 800), (120, 30, 30)).save(cover, 'JPEG')
    book = pack_epub(FIXTURES / 'epub3', work / 'book.epub', extra={'OEBPS/cover.jpg': cover.read_bytes()})

    from ebook_convert.customize.ui import available_input_formats, available_output_formats

    outputs = sorted(available_output_formats())
    inputs = sorted(available_input_formats())
    rows = []
    produced = {}
    for fmt in outputs:
        dst = work / ('out.' + fmt)
        if fmt == 'oeb':
            dst = work / 'out_oeb'
        proc = run(book, dst)
        ok = proc.returncode == 0 and (dst.is_dir() or (dst.exists() and dst.stat().st_size > 0))
        note = ''
        if not ok:
            note = (proc.stderr.strip().splitlines() or ['?'])[-1][:100]
        elif 'Traceback' in proc.stderr:
            note = 'traceback in log'
        rows.append(('output', fmt, 'ok' if ok else 'FAIL', note))
        if ok:
            produced[fmt] = dst

    # extra inputs that no output plugin produces
    extra = {
        'txt': FIXTURES / 'sample.txt',
        'html': FIXTURES / 'sample.html',
        'rtf': FIXTURES / 'tricky.rtf',
    }
    # samples for input formats no output plugin produces
    text = (FIXTURES / 'sample.txt').read_text(encoding='utf-8')
    (work / 'sample.md').write_text('# Chapter One\n\nSome *markdown* text.\n\n# Chapter Two\n\nMore.\n', encoding='utf-8')
    extra['md'] = extra['markdown'] = work / 'sample.md'
    (work / 'sample.textile').write_text('h1. Chapter One\n\nSome _textile_ text.\n\nh1. Chapter Two\n\nMore.\n', encoding='utf-8')
    extra['textile'] = work / 'sample.textile'
    (work / 'sample.text').write_text(text, encoding='utf-8')
    extra['text'] = work / 'sample.text'
    for name in ('xhtm', 'xhtml', 'htm', 'shtm', 'shtml'):
        shutil.copyfile(FIXTURES / 'sample.html', work / ('sample.' + name))
        extra[name] = work / ('sample.' + name)
    try:
        from odf.opendocument import OpenDocumentText
        from odf.text import H, P

        doc = OpenDocumentText()
        doc.text.addElement(H(outlinelevel=1, text='Chapter One'))
        doc.text.addElement(P(text='Some ODT text.'))
        doc.text.addElement(H(outlinelevel=1, text='Chapter Two'))
        doc.text.addElement(P(text='More ODT text.'))
        doc.save(str(work / 'sample.odt'))
        extra['odt'] = work / 'sample.odt'
    except Exception as e:
        print('could not build ODT sample:', e, file=sys.stderr)
    if 'pmlz' in produced:
        with zipfile.ZipFile(produced['pmlz']) as zf:
            for n in zf.namelist():
                if n.endswith('.pml'):
                    (work / 'sample.pml').write_bytes(zf.read(n))
                    extra['pml'] = work / 'sample.pml'
                    break
    if 'fb2' in produced:
        with zipfile.ZipFile(work / 'sample.fbz', 'w') as zf:
            zf.write(produced['fb2'], 'book.fb2')
        extra['fbz'] = work / 'sample.fbz'
    with zipfile.ZipFile(work / 'sample.zip', 'w') as zf:
        zf.write(FIXTURES / 'sample.html', 'index.html')
    extra['zip'] = work / 'sample.zip'
    for fmt in inputs:
        src = None
        if fmt in produced and produced[fmt].is_file():
            src = produced[fmt]
        elif fmt == 'opf' and 'oeb' in produced:
            src = produced['oeb'] / 'content.opf'
        elif fmt in extra:
            src = extra[fmt]
        elif fmt == 'pmlz' and 'pml' in produced:
            src = produced['pml']
        elif fmt == 'azw' and 'mobi' in produced:
            src = work / 'out.azw'
            shutil.copyfile(produced['mobi'], src)
        elif fmt == 'prc' and 'mobi' in produced:
            src = work / 'out.prc'
            shutil.copyfile(produced['mobi'], src)
        elif fmt == 'pdf':
            for cand in ('/usr/share/doc', '/usr/share/cups/data', '/usr/share/texmf'):
                for dirpath, dirnames, filenames in os.walk(cand):
                    for fn in filenames:
                        if fn.endswith('.pdf'):
                            src = pathlib.Path(dirpath) / fn
                            break
                    if src:
                        break
                if src:
                    break
        if src is None:
            rows.append(('input', fmt, 'skip', 'no sample'))
            continue
        dst = work / ('back_from_%s.epub' % fmt)
        proc = run(src, dst)
        ok = proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0
        note = ''
        if ok and src != extra.get(fmt) and fmt != 'pdf':
            try:
                if MARKER not in epub_text(dst):
                    note = 'text lost'
            except Exception as e:
                note = 'unreadable epub: %s' % e
        if not ok:
            note = (proc.stderr.strip().splitlines() or ['?'])[-1][:100]
        elif 'Traceback' in proc.stderr:
            note = (note + '; ' if note else '') + 'traceback in log'
        rows.append(('input', fmt, 'ok' if ok else 'FAIL', note + (' (%s)' % src.name if fmt == 'pdf' else '')))

    width = max(len(r[1]) for r in rows)
    bad = 0
    for kind, fmt, status, note in rows:
        print('%-6s %-*s %-4s %s' % (kind, width, fmt, status, note))
        bad += status == 'FAIL' or 'lost' in note or 'traceback' in note
    print('work dir:', work, file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
