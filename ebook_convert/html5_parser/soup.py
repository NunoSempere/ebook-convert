"""BeautifulSoup front-end of the html5_parser stand-in (see package doc)."""

from __future__ import annotations

import warnings

import bs4
from html5lib.constants import DataLossWarning

_soup_module = bs4


def set_soup_module(mod) -> None:
    global _soup_module
    _soup_module = mod


def parse(markup, return_root=True, keep_doctype=True, stack_size=16 * 1024, **kwargs):
    """Parse markup with the HTML5 algorithm into a BeautifulSoup object.

    ``return_root`` is accepted for API compatibility; a soup object is
    always returned (the soup *is* the document)."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DataLossWarning)
        return _soup_module.BeautifulSoup(markup, 'html5lib')
