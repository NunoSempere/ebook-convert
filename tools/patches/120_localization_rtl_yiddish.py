"""Yiddish is written in the Hebrew script, so treat it as right-to-left like
the 4.x line did (Calibre's list stops at Farsi)."""

TARGET = 'utils/localization.py'

REPLACEMENTS = [
    (
        "    return lang and lang in ('ara', 'heb', 'aze', 'div', 'arc', 'syc', 'myz', 'ckb', 'urd', 'fas')\n",
        "    return lang and lang in ('ara', 'heb', 'aze', 'div', 'arc', 'syc', 'myz', 'ckb', 'urd', 'fas', 'yid')\n",
    ),
]
