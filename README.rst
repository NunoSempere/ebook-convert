=============
ebook-convert
=============

Command-line ebook converter carved out of the `Calibre project`_. It is only
the conversion pipeline: no GUI, no library management, no Qt, no C
extensions, no device drivers.

**No installation needed.** With `uv`_ on your machine, this is the whole
thing:

.. code:: shell-session

   $ uvx ebook-convert book.epub book.mobi

``uvx`` fetches the package into a cache the first time and runs it straight
away; later runs start instantly. Swap the extensions to convert between any
of the formats listed below, for example ``uvx ebook-convert novel.docx
novel.epub`` or ``uvx ebook-convert story.fb2 story.txt``.

The package is pure Python and every dependency ships binary wheels, so it
runs anywhere with a stock Python 3.12+ and no compiler.

This is the 5.x line of the project: a **fresh extraction of current Calibre**
(9.18.0, git ``0ccdcb283f``, November 2026) produced by a script, so that it
can be re-synchronised with Calibre cheaply. The 4.x line was a hand-pruned
copy of Calibre 4.13 from 2020 (`gryf's ebook-converter`_, later maintained as
`ebook-convert 4.x`_); it served as the reference for what this version has to
look like and do, and its test-suite is the acceptance suite here. All credit
for the conversion code goes to Kovid Goyal and the Calibre contributors;
credit for showing that Calibre's converter can live without Qt goes to gryf.


Installation
------------

The recommended way is not to install at all and run it through ``uvx`` as
shown above. uv itself is a single binary; see its `install page`_.

If you would rather have a permanent ``ebook-convert`` command on your
``$PATH``:

.. code:: shell-session

   $ uv tool install ebook-convert      # with uv
   $ pipx install ebook-convert         # with pipx
   $ pip install ebook-convert          # into the current environment

Single-file executables for Linux (x86_64, aarch64) and macOS (arm64, x86_64)
that need no Python at all are attached to each `GitHub release`_.

Optional pieces:

- ``pdftohtml``, ``pdfinfo`` and ``pdftoppm`` from `poppler`_ are needed in
  ``$PATH`` for conversion *from* PDF.
- ``pip install 'ebook-convert[japanese]'`` adds Japanese transliteration for
  ``--asciiize``.
- ``optipng``, ``jpegtran``/``cjpeg`` and ``cwebp`` are used to optimise
  images when present; Pillow is used otherwise.


Usage
-----

.. code:: shell-session

   $ ebook-convert INPUT OUTPUT [options]

The command line is Calibre's own ``ebook-convert`` command, unchanged: the
output format is taken from the extension of ``OUTPUT`` (``.EXT`` alone
derives the name from the input, no extension writes an OEB folder), and all
of Calibre's conversion options work, from ``--authors`` and ``--cover`` to
``--base-font-size``, ``--chapter``, ``--level1-toc``, ``--extra-css``,
``--embed-font-family``, ``--search-replace`` and the heuristic processing
switches. ``ebook-convert in.epub out.mobi -h`` lists the options that apply
to that pair of formats. The `Calibre conversion manual`_ applies verbatim.

Diagnostics go to stderr; ``-v`` makes them more verbose, ``--debug-pipeline
DIR`` dumps the intermediate stages.


Supported formats
-----------------

Every entry below is exercised by ``tools/survey.py`` with a real conversion
(output: EPUB fixture to the format; input: that result back to EPUB, text
checked to survive).

**Input:** ``azw``, ``azw3``, ``azw4``, ``docx``, ``docm``, ``epub``,
``fb2``, ``fbz``, ``htm``, ``html``, ``xhtml``, ``shtml``, ``htmlz``,
``lrf``, ``md``/``markdown``, ``mobi``,
``prc``, ``pobi``, ``odt``, ``opf``, ``pdb``, ``updb``, ``pdf`` (needs
poppler), ``pml``, ``pmlz``, ``rb``, ``rtf``, ``snb``, ``tcr``, ``txt``,
``text``, ``textile``, ``txtz``, ``zip`` (of HTML), ``kepub`` (also as
``.kepub.epub``; the Kobo markup is stripped).

**Output:** ``azw3``, ``docx``, ``epub``, ``fb2``, ``htmlz``, ``kepub`` (or
``.kepub.epub``, Kobo's own naming), ``lrf``, ``mobi``, ``oeb`` (a folder),
``pdb``, ``pmlz``, ``rb``, ``rtf``, ``snb``,
``tcr``, ``txt``, ``txtz``, ``zip`` (Calibre's "HTML output": a zip of HTML
files with an index).

Compared with the 4.x line this adds HTML/zip, PDB, PMLZ, RB, RTF, SNB and
TCR output, KEPUB input and output, and PML, RB, SNB, TCR and AZW4 input,
plus everything
Calibre changed in the converters between 2020 and 2026 (EPUB 3 navigation,
KF8 fixes, DOCX tables and footnotes, the new CSS parser, ...).

Not included, and why:

- **PDF output**: rendered by Calibre with Qt WebEngine and PoDoFo (C++).
- **LIT** input/output: needs the ``lzx``/``msdes`` C extensions.
- **CHM** and **DjVu** input: need the ``chm`` and ``bzzdec`` C extensions.
- **Comic (CBZ/CBR)** input: image processing with Qt, ``unrar``.
- **News download (recipes)**: needs Calibre's web framework.
- **RAR** archives anywhere: need ``unrardll``.
- Metadata download, library, devices, viewer, editor, server, AI features:
  not conversion.


Differences from Calibre
------------------------

A handful of Calibre's building blocks are C/C++ or Qt and have been replaced
by pure-Python equivalents. These are the places where behaviour can differ
from running ``ebook-convert`` inside a Calibre install:

- **Sentence splitting** (``calibre.spell.break_iterator``): the Kobo
  ``<span>`` per sentence in KEPUB output is placed by ICU's sentence
  iterator in Calibre. Here it follows `kepubify`_'s rule instead (a
  sentence ends at ``.``, ``!`` or ``?``, an optional closing quote or
  ellipsis, and whitespace), which is what Kobo's own tooling produces.
- **ICU** (``calibre.utils.icu``): sorting, case changes and case-insensitive
  searches are done with Unicode normalisation and case folding from the
  standard library. Results are locale independent (no Swedish ``v``/``w``
  merging, no Turkish ``i`` rules, no language specific contractions), and
  bidi reordering of PDF text (``visual_to_logical``) is an identity
  transform. Sorting is only used for things like index pages and manifest
  ordering; for conversion output the difference is cosmetic.
- **Images** (``calibre.utils.img``): re-implemented on Pillow. Covers, image
  rescaling, grayscale/dither for e-ink profiles, GIF/PNG/JPEG/WebP
  conversion all work; the quality of resampling and JPEG encoding is
  Pillow's rather than Qt's. JPEG-XR needs the external ``JxrDecApp``.
- **SVG rasterisation**: rendered by `resvg`_ (``resvg_py`` wheel) instead
  of ``QSvgRenderer``. resvg is a complete SVG 1.1 renderer; SVG fonts and
  CSS ``@font-face`` inside SVG are not supported.
- **Generated covers** (the "default cover" EPUB output adds when a book has
  none): a plain title/series/author cover drawn with Pillow, instead of
  Calibre's themed, template-driven Qt painter.
- **HTML parsing**: ``html5lib`` instead of the ``html5-parser`` C extension.
  Same HTML5 algorithm, slower, and element line numbers are not recorded.
- **Encoding detection**: ``chardet`` instead of ``uchardet``.
- **PalmDOC compression** (MOBI/PDB): the Python implementation; slower on
  very large books.
- **Translations**: none, ``_()`` is the identity. All messages are English.
- **Fonts**: no FreeType/fontconfig; the system font scanner reads font files
  directly (``--embed-font-family`` works with fonts from ``~/.fonts``,
  ``/usr/share/fonts`` etc.). Liberation fonts are not bundled, so LRF output
  and font embedding fall back to whatever the system has.
- **Configuration** lives in ``~/.config/ebook-convert`` (XDG), not in
  Calibre's directory; Calibre tweaks can be put in a ``tweaks.json`` there.
  Set ``EBOOK_CONVERT_CONFIG_DIRECTORY`` to move it.
- **Workers**: jobs Calibre runs in a helper process (``pdfinfo`` metadata,
  exploding AZW3 files) run in-process.
- Reading PDF metadata works (``pdfinfo``); *writing* PDF metadata does not
  (PoDoFo).


How this package is built
-------------------------

``ebook_convert/`` is **generated**; do not edit it by hand. Everything that
turns a Calibre checkout into this package lives in ``tools/``:

``tools/vendor.py`` (standard library only)
  ``python tools/vendor.py /path/to/calibre`` rebuilds ``ebook_convert/``
  from scratch, deterministically:

  1. copies an explicit include list (``src/calibre/ebooks``, ``customize``,
     the needed ``utils`` modules, ``polyglot``, ``tinycss``,
     ``css_selectors`` and the resource files under ``resources/`` into
     ``ebook_convert/data/``);
  2. deletes an explicit exclude list (LIT/CHM/DjVu/comic/PDF-output/recipe
     plugins, editor-only ``oeb/polish`` modules, metadata download sources,
     C sources, tests) and every non-Python file outside ``data/``;
  3. rewrites imports: ``calibre`` to ``ebook_convert``, ``polyglot``,
     ``tinycss``, ``css_selectors``, ``html5_parser`` and
     ``calibre_extensions`` to the copies/stand-ins inside ``ebook_convert``;
  4. makes Calibre's Python 3.14 code run on 3.12 and 3.13 (``except A, B:``
     to ``except (A, B):``, ``from compression import zlib`` to ``import
     zlib``, type parameter defaults dropped, ``from __future__ import
     annotations`` added for the deferred annotations Calibre relies on);
  5. applies the ordered patch rules in ``tools/patches/`` (small exact text
     replacements; a rule that no longer matches makes the run fail, which
     is the point: after a Calibre upgrade you fix or drop the rule);
  6. copies the hand-written modules in ``tools/overlay/`` over the tree;
  7. writes ``ebook_convert/_vendored.py`` with the Calibre commit.

  ``python tools/vendor.py --check`` lists imports of ``calibre``, ``qt``,
  ``PyQt`` or ``calibre_extensions`` still present; module-level ones fail
  the check, indented (lazy) ones are listed for information.

``tools/patches/``
  One file per patch, applied in name order:

  - ``010_localization_iso639``: build the ISO-639 language tables from the
    bundled ``iso_639-3.json`` instead of Calibre's build-time msgpack file.
  - ``020_customize_builtins``: keep only the archive, metadata and
    conversion plugins and the profiles; register the verified plugin set.
  - ``030_customize_ui``: placeholder classes for device drivers and metadata
    sources in the plugin registry.
  - ``040_formatter_functions``: inline two constants from ``calibre.db``.
  - ``050_conversion_cli``: no recipe listing; log to stderr; usage text.
  - ``060_docx_paper_sizes``: inline the paper size table from the PDF renderer.
  - ``070_lrf_device_stub``: inline ``DevicePlugin.THUMBNAIL_HEIGHT``.
  - ``080_metadata_pdf_podofo``: PDF metadata writing raises instead of
    importing PoDoFo.
  - ``090_txt_input_txtz_metadata``: read TXTZ metadata from the archive, not
    from the inner ``.txt`` (fixes lost title/author).
  - ``100_markdown_series``: inline the "Series [index]" parser from
    ``calibre.db``.

``tools/overlay/``
  Replacements and additions, kept small and documented in each file:

  - ``constants.py``, ``startup.py``, ``utils/resources.py``: trimmed
    constants, process initialisation (``_``, ``P()``, ``I()`` builtins,
    mimetypes, temp dir) and resource lookup inside ``ebook_convert/data``.
  - ``utils/icu.py``: the pure-Python ICU replacement described above.
  - ``utils/img.py``: Pillow image utilities (from the 4.x line, plus
    WebP and alt-text helpers from current Calibre).
  - ``utils/html5.py``, ``html5_parser/``: html5lib-based ``html5_parser``.
  - ``calibre_extensions/``: Python stand-ins for the C extensions
    ``speedup``, ``fast_html_entities``, ``cPalmdoc``, ``uchardet``,
    ``translator`` and ``tokenizer`` (CSS Color 4 parser); any other
    extension raises ``ImportError`` so Calibre's own fallbacks kick in.
  - ``utils/ipc/simple_worker.py``, ``utils/safe_atexit.py``: in-process
    replacements for Calibre's worker processes.
  - ``ebooks/oeb/transforms/rasterize.py``: resvg rasteriser.
  - ``ebooks/covers.py``: Pillow cover generator.
  - ``ebooks/metadata/sources/identify.py``: ``urls_from_identifiers`` only.
  - ``main.py``: the console entry point.
  - ``data/iso_639-3.json``: language codes (from the iso-codes project).

``tools/check_imports.py``
  Imports every module under ``ebook_convert/`` and lists failures.

``tools/survey.py``
  Runs a real conversion through every registered input and output plugin
  and prints a table.

Re-syncing with a newer Calibre
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: shell-session

   $ git clone --depth 1 https://github.com/kovidgoyal/calibre.git /tmp/calibre
   $ ./make.sh vendor /tmp/calibre      # vendor + --check + import check
   $ ./make.sh test
   $ ./make.sh survey

If a patch rule no longer matches, ``vendor.py`` stops and names it: look at
the new Calibre code, update the rule (or remove it if Calibre no longer
needs it) and run again. New ``calibre_extensions`` names or Qt imports show
up in ``--check`` and ``check_imports.py``; add a stand-in to the overlay or
an entry to the exclude list. Commit the regenerated tree together with the
tooling change.


Development
-----------

.. code:: shell-session

   $ ./make.sh install     # uv venv with all extras
   $ ./make.sh test        # pytest (the 4.x acceptance suite + tree checks)
   $ ./make.sh check       # vendor --check + import every module
   $ ./make.sh survey      # convert through every plugin
   $ ./make.sh build       # sdist + wheel + twine check
   $ ./make.sh binary      # PyInstaller single-file executable

CI runs the test-suite on Python 3.12, 3.13 and 3.14 on Linux and on macOS,
builds the wheel and smoke-tests it with ``uvx``.


Related projects
----------------

Tools that get books *into* a format this converter understands, or that
cover ground it does not:

- `FicHub`_: paste a fanfiction URL, get an EPUB (also MOBI, PDF or zipped
  HTML). Covers FanFiction.net, FictionPress, SpaceBattles,
  SufficientVelocity, QuestionableQuesting and more. `Source`_ is on GitHub.
- `WebToEpub`_: browser extension (Chrome, Firefox) that turns the web novel
  or serial you are reading into an EPUB for offline reading; supports
  Archive of Our Own, FanFiction.net, Royal Road, Baka-Tsuki and many others.
  `Code`_ is on GitHub.
- `FanFicFare`_: command-line tool and Calibre plugin that downloads
  fanfiction from a long list of sites into EPUB, with metadata.
- `Calibre`_: the real thing, with GUI, library, viewer, editor and every
  format. Use it if you can install it.
- `pandoc`_: converts between document formats including EPUB and DOCX, from
  Markdown and LaTeX; no MOBI/AZW3/LRF.
- `kepubify`_: EPUB to Kobo KEPUB, in Go; the sentence rule for Kobo spans
  here is taken from it.
- `KCC`_: comics to e-reader formats.


License
-------

GPL-3.0-or-later, like Calibre. Copyright Kovid Goyal and the Calibre
contributors for the converted code (headers are kept in every file); the
tooling and overlay modules are copyright their respective authors as noted
in the files.

.. _Calibre project: https://calibre-ebook.com
.. _Calibre: https://calibre-ebook.com
.. _uv: https://docs.astral.sh/uv/
.. _install page: https://docs.astral.sh/uv/getting-started/installation/
.. _gryf's ebook-converter: https://github.com/gryf/ebook-converter
.. _ebook-convert 4.x: https://github.com/NunoSempere/ebook-convert/tree/1a3a973
.. _GitHub release: https://github.com/NunoSempere/ebook-convert/releases
.. _poppler: https://poppler.freedesktop.org/
.. _Calibre conversion manual: https://manual.calibre-ebook.com/conversion.html
.. _resvg: https://github.com/linebender/resvg
.. _FicHub: https://fichub.net/
.. _Source: https://github.com/FicHub/fichub.net
.. _WebToEpub: https://chromewebstore.google.com/detail/webtoepub/akiljllkbielkidmammnifcnibaigelm
.. _Code: https://github.com/dteviot/WebToEpub
.. _FanFicFare: https://github.com/JimmXinu/FanFicFare
.. _pandoc: https://pandoc.org
.. _kepubify: https://pgaskin.net/kepubify/
.. _KCC: https://github.com/ciromattia/kcc
