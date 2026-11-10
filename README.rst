=============
ebook-convert
=============

Command-line ebook converter, carved out of the `Calibre project`_. It is only
the conversion pipeline: no GUI, no library management, no Qt, no device
drivers. Just:

.. code:: shell-session

   $ ebook-convert book.epub book.mobi

The package is pure Python and every dependency ships binary wheels, so it
installs anywhere with a stock Python 3.10+ and no compiler.

This is a packaging-focused fork of `gryf's ebook-convert`_, which did the
hard work of extracting the converter from Calibre and removing Qt. All
credit for that goes to gryf and, of course, to Kovid Goyal and the Calibre
contributors. The fork exists to publish the tool on PyPI under the name
``ebook-convert``, to make it installable with ``uvx``, and to ship
single-file binaries.


Installation
------------

Run it without installing anything permanently, with `uv`_:

.. code:: shell-session

   $ uvx ebook-convert book.epub book.mobi

Or install it as a tool:

.. code:: shell-session

   $ uv tool install ebook-convert      # with uv
   $ pipx install ebook-convert         # with pipx
   $ pip install ebook-convert          # into the current environment

Single-file executables for Linux (x86_64, aarch64) and macOS (arm64, x86_64)
that need no Python at all are attached to each `GitHub release`_.

Optional system tools:

- ``pdftohtml``, ``pdfinfo`` and ``pdftoppm`` from `poppler`_ are needed in
  ``$PATH`` for conversion *from* PDF.
- `Liberation fonts`_ are used when embedding fonts into LRF output.

Markdown-formatted text input additionally needs the ``markdown`` package:
``pip install 'ebook-convert[markdown]'``.


Usage
-----

.. code:: shell-session

   $ ebook-convert INPUT OUTPUT [-v|-q]

The formats are taken from the file extensions. ``-v`` makes the output more
verbose (repeat for more), ``-q`` quieter.


What's supported
----------------

Input formats
~~~~~~~~~~~~~

- EPUB, both v2 and v3 (``epub``)
- Mobipocket and Kindle (``mobi``, ``prc``, ``azw``, ``azw3``)
- Microsoft Word 2007 and up (``docx``)
- LibreOffice / OpenDocument text (``odt``)
- Rich Text Format (``rtf``)
- FictionBook (``fb2``)
- HTML (``html``, ``htm``, ``xhtml``, ``opf``) and zipped HTML (``htmlz``)
- Plain text (``txt``, ``txtz``), Markdown (``md``) and Textile
- PDF (``pdf``), via poppler
- Broadband eBooks (BBeB) (``lrf``)
- PalmOS databases (``pdb``, ``updb``): Plucker, eReader, zTXT, PalmDOC,
  Haodoo

The old binary Microsoft ``doc`` format is not supported; convert it to
``docx`` or ``odt`` with Word or LibreOffice first.

Output formats
~~~~~~~~~~~~~~

- EPUB v2 (``epub``)
- Mobipocket (``mobi``)
- Microsoft Word (``docx``)
- FictionBook (``fb2``)
- Zipped HTML with assets (``htmlz``)
- Plain text (``txt``) and zipped text (``txtz``)
- Broadband eBooks (BBeB) (``lrf``)
- Unpacked OEB directory (``oeb``)

Calibre's remaining formats (LIT, AZW3/KF8 output, PDB output, PDF output,
RB, SNB, TCR, PML, CHM, DJVU, comics, recipes) were never ported and are not
registered.

Known limitations
~~~~~~~~~~~~~~~~~

- SVG images are not rasterized (Calibre does that with Qt). Formats that
  cannot display SVG, like ``mobi``, will show such images as missing. A
  warning is logged when this happens.
- The *Kindle periodical* format (discontinued by Amazon in 2023) is treated
  as an ordinary book.
- Windows is not tested.
- Conversion options are not exposed on the command line yet; Calibre's
  defaults are used.


Development
-----------

.. code:: shell-session

   $ git clone https://github.com/NunoSempere/ebook-convert
   $ cd ebook-convert
   $ ./make.sh install        # uv sync: creates .venv with dev dependencies
   $ ./make.sh test           # pytest
   $ ./make.sh build          # sdist + wheel into dist/
   $ ./make.sh binary         # single-file executable via PyInstaller

Releasing: bump ``version`` in ``pyproject.toml`` and ``numeric_version`` in
``ebook_convert/constants_old.py``, commit, then tag ``vX.Y.Z`` and push the
tag. The ``release.yml`` workflow runs the tests, publishes to PyPI through
trusted publishing, builds the binaries and attaches everything to a GitHub
release. To publish by hand instead, run ``UV_PUBLISH_TOKEN=pypi-... ./make.sh
publish`` after ``./make.sh build``.


Background
----------

In gryf's words, `the original project`_ started as "an impudent ripoff of the
conversion bits from Calibre", with the aim of having only the converter,
runnable from the command line, without the rest of Calibre, and with a
cleaner, more pythonic code base. Qt and GUI code were removed and most
vendored third-party modules replaced by their PyPI versions. This fork adds
PyPI packaging, binaries, a test-suite, and swaps the HTML5 parser for the
pure-Python `html5lib`_ instead of a C extension that had to be compiled
against a matching ``libxml2``.

Note that Calibre itself installs a command with the same name,
``ebook-convert``. If you have Calibre installed, whichever comes first on
your ``$PATH`` wins; ``uvx ebook-convert`` always runs this one.

There is no Python 2 support and there will not be.


License
-------

This work is licensed under GPL3, like the original. See LICENSE for details.

.. _Calibre project: https://calibre-ebook.com/
.. _gryf's ebook-converter: https://github.com/gryf/ebook-converter
.. _uv: https://docs.astral.sh/uv/
.. _GitHub release: https://github.com/NunoSempere/ebook-convert/releases
.. _poppler: https://poppler.freedesktop.org/
.. _Liberation fonts: https://github.com/liberationfonts/liberation-fonts
.. _html5lib: https://github.com/html5lib/html5lib-python
.. _the original project: https://github.com/gryf/ebook-converter
