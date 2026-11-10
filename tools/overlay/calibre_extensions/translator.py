"""Stand-in for calibre's ``translator`` C extension: a gettext-style
translator.  ebook-convert ships no translation catalogs, so this is the
NullTranslations behaviour (identity) unless ``.mo`` data is passed in."""

from __future__ import annotations

import builtins
import gettext
import io


class Translator(gettext.NullTranslations):
    def __init__(self, data: bytes | None = None) -> None:
        super().__init__()
        self._impl = gettext.GNUTranslations(io.BytesIO(data)) if data else None

    def add_fallback(self, fallback) -> None:
        if self._impl is not None:
            self._impl.add_fallback(fallback)
        else:
            super().add_fallback(fallback)

    def gettext(self, message: str) -> str:
        return self._impl.gettext(message) if self._impl is not None else message

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        if self._impl is not None:
            return self._impl.ngettext(msgid1, msgid2, n)
        return msgid1 if n == 1 else msgid2

    def pgettext(self, context: str, message: str) -> str:
        return self._impl.pgettext(context, message) if self._impl is not None else message

    def npgettext(self, context: str, msgid1: str, msgid2: str, n: int) -> str:
        if self._impl is not None:
            return self._impl.npgettext(context, msgid1, msgid2, n)
        return msgid1 if n == 1 else msgid2

    def info(self) -> dict:
        return self._impl.info() if self._impl is not None else {}

    def install(self, names=None) -> None:
        builtins.__dict__['_'] = self.gettext
        for name in names or ():
            if hasattr(self, name):
                builtins.__dict__[name] = getattr(self, name)
