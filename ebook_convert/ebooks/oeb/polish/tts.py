"""The one function ``calibre.ebooks.oeb.polish.tts`` lends to the kepubifier.

The real module embeds text-to-speech audio into EPUB 3 books and depends on
hunspell, ICU and a speech engine; only ``lang_for_elem`` is needed here.
"""
from __future__ import annotations

from lxml.etree import _Element

from ebook_convert.utils.localization import canonicalize_lang


def lang_for_elem(elem: _Element, parent_lang: str | None) -> str | None:
    return canonicalize_lang(elem.get('lang') or elem.get('xml_lang') or elem.get('{http://www.w3.org/XML/1998/namespace}lang')) or parent_lang
