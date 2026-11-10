"""Stand-in for Calibre's macOS-only ``usbobserver`` extension.

Besides watching USB devices (not needed here) it answers two questions for
``utils.localization`` and ``utils.date``: the user's locale and the system
short date format.  ``localization.get_system_locale`` imports it outside a
``try`` block on macOS, so without this module every conversion on a Mac
failed at startup.
"""
from __future__ import annotations

import locale
import os


def user_locale() -> str | None:
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        val = os.environ.get(var)
        if val and val not in ('C', 'POSIX'):
            return val.split('.')[0]
    try:
        return locale.getlocale()[0] or None
    except Exception:
        return None


def date_format() -> str | None:
    # None makes utils.date fall back to month-first parsing of ambiguous dates
    return None
