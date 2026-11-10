# License: GPLv3 Copyright: 2015, Kovid Goyal <kovid at kovidgoyal.net>
# Pillow re-implementation for ebook-convert: replaces calibre/ebooks/covers.py.
#
# Calibre draws generated covers with Qt, using user-configurable colour
# themes, drawing styles and templates.  This module keeps the public
# functions the conversion pipeline calls (``create_cover``, ``calibre_cover2``,
# ``generate_cover``, ``message_image``, ``generate_masthead``, ``scale_cover``)
# and renders a plain cover with Pillow: a coloured background, the title,
# series and authors centred in a bundled/system TrueType font.  Templates,
# themes and styles from ``cover_generation`` preferences are not supported.

from __future__ import annotations

import os
import re
import textwrap
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from ebook_convert import fit_image
from ebook_convert.ebooks.metadata import authors_to_string, fmt_sidx
from ebook_convert.utils.cleantext import clean_ascii_chars
from ebook_convert.utils.config import JSONConfig

cprefs = JSONConfig('cover_generation')
cprefs.defaults['title_font_size'] = 120  # px
cprefs.defaults['subtitle_font_size'] = 80  # px
cprefs.defaults['footer_font_size'] = 80  # px
cprefs.defaults['cover_width'] = 1200  # px
cprefs.defaults['cover_height'] = 1600  # px
cprefs.defaults['title_font_family'] = None
cprefs.defaults['subtitle_font_family'] = None
cprefs.defaults['footer_font_family'] = None
cprefs.defaults['color_themes'] = {}
cprefs.defaults['disabled_color_themes'] = []
cprefs.defaults['disabled_styles'] = []
cprefs.defaults['title_template'] = '<b>{title}'
cprefs.defaults['subtitle_template'] = ''
cprefs.defaults['footer_template'] = ''

# A few of calibre's default colour themes (background, title, subtitle, footer)
default_color_themes = {  # calibre's defaults: background, accent, contrast 1, contrast 2
    'Earth': 'e8d9ac c7b07b 564628 382d1a',
    'Grass': 'd8edb5 abc8a4 375d3b 183128',
    'Water': 'd3dcf2 829fe4 00448d 00305a',
    'Silver': 'e6f1f5 aab3b6 6e7476 3b3e40',
}
fallback_colors = 'ffffff 000000 000000 000000'

_FONT_CANDIDATES = (
    'LiberationSerif-Bold.ttf', 'LiberationSerif-Regular.ttf', 'DejaVuSerif-Bold.ttf', 'DejaVuSerif.ttf',
    'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf', 'NotoSerif-Bold.ttf', 'NotoSerif-Regular.ttf', 'FreeSerifBold.ttf',
    'FreeSerif.ttf', 'Arial Bold.ttf', 'Arial.ttf', 'Georgia.ttf', 'arialbd.ttf', 'arial.ttf', 'georgia.ttf',
)
_FONT_DIRS = (
    '/usr/share/fonts', '/usr/local/share/fonts', os.path.expanduser('~/.fonts'), os.path.expanduser('~/.local/share/fonts'),
    '/Library/Fonts', '/System/Library/Fonts', os.path.expanduser('~/Library/Fonts'), 'C:\\Windows\\Fonts',
)
_font_path_cache: dict[str | None, str | None] = {}


def _find_font_file(family: str | None = None) -> str | None:
    if family in _font_path_cache:
        return _font_path_cache[family]
    ans = None
    wanted = [family + '.ttf', family + '-Bold.ttf', family.replace(' ', '') + '.ttf'] if family else []
    wanted += list(_FONT_CANDIDATES)
    try:
        from ebook_convert.utils.fonts.scanner import font_scanner

        if family:
            for face in font_scanner.fonts_for_family(family) or ():
                if face.get('path'):
                    ans = face['path']
                    break
    except Exception:
        pass
    if ans is None:
        for base in _FONT_DIRS:
            if not os.path.isdir(base):
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                lower = {f.lower(): f for f in filenames}
                for w in wanted:
                    if w.lower() in lower:
                        ans = os.path.join(dirpath, lower[w.lower()])
                        break
                if ans:
                    break
            if ans:
                break
    _font_path_cache[family] = ans
    return ans


def _font(size: int, family: str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _find_font_file(family)
    if path:
        try:
            return ImageFont.truetype(path, size=max(6, int(size)))
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=max(6, int(size)))
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def init_environment() -> None:
    pass


def sanitize(s: str) -> str:
    return clean_ascii_chars(re.sub(r'\s+', ' ', s or '')).strip()


def escape_formatting(s: str) -> str:
    return s


def unescape_formatting(s: str) -> str:
    return s


def to_theme(x: str) -> dict[str, str]:
    bg, title, subtitle, footer = x.split()
    return {'color1': bg, 'color2': title, 'contrast_color1': subtitle, 'contrast_color2': footer}


def _colors(prefs, mi) -> tuple[str, str, str, str]:
    themes = dict(default_color_themes)
    themes.update({k: v for k, v in (prefs.get('color_themes') or {}).items() if isinstance(v, str)})
    for k in prefs.get('disabled_color_themes') or ():
        themes.pop(k, None)
    if not themes:
        return tuple('#' + c for c in fallback_colors.split())
    names = sorted(themes)
    seed = (mi.title or '') + '|' + authors_to_string(mi.authors or ())
    theme = themes[names[sum(map(ord, seed)) % len(names)]]
    return tuple('#' + c for c in theme.split())


def scale_cover(prefs, scale: float) -> None:
    for x in ('cover_width', 'cover_height', 'title_font_size', 'subtitle_font_size', 'footer_font_size'):
        prefs[x] = int(scale * prefs[x])


def override_prefs(base_prefs, **overrides):
    ans = {k: base_prefs.get(k, cprefs.defaults[k]) for k in cprefs.defaults}
    for k, v in overrides.items():
        if v is not None:
            ans[k] = v
    return ans


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines = []
    for para in text.split('\n'):
        words = para.split()
        if not words:
            continue
        cur = words[0]
        for w in words[1:]:
            trial = cur + ' ' + w
            if draw.textlength(trial, font=font) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines or ['']


def _draw_block(draw, text, font_size, family, color, width, top, bottom, align_bottom=False, max_lines=8, measure_only=False) -> int:
    'Draw text centred between top and bottom; return the y coordinate below the text'
    if not text:
        return top
    font = _font(font_size, family)
    margin = int(width * 0.08)
    lines = _wrap(draw, text, font, width - 2 * margin)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [textwrap.shorten(' '.join(lines[max_lines - 1 :]), 40, placeholder='...')]
    line_height = int(font_size * 1.2)
    total = line_height * len(lines)
    y = bottom - total if align_bottom else top
    y = max(top, min(y, bottom - total))
    if measure_only:
        return y + total
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((width - w) / 2, y), line, font=font, fill=color)
        y += line_height
    return y


def _render(mi, prefs, logo_path: str | None = None) -> Image.Image:
    prefs = override_prefs(prefs or cprefs)
    width, height = int(prefs['cover_width']), int(prefs['cover_height'])
    bg, c_title, c_subtitle, c_footer = _colors(prefs, mi)
    img = Image.new('RGB', (width, height), bg)
    draw = ImageDraw.Draw(img)
    title = sanitize(mi.title or '')
    subtitle = ''
    if getattr(mi, 'series', None):
        subtitle = sanitize(mi.series)
        if mi.series_index is not None:
            subtitle += ' - ' + fmt_sidx(mi.series_index, use_roman=False)
    footer = sanitize(authors_to_string(mi.authors or ()))
    if footer.lower() in ('unknown', 'unbekannt'):
        footer = ''
    pad = int(height * 0.06)
    # Layout after calibre's "The Cross" style: a band in the accent colour
    # behind the title and subtitle, a stripe down the left edge, title and
    # subtitle in the darkest contrast colour, the author line in the other.
    band_top = pad * 2
    y = _draw_block(draw, title, prefs['title_font_size'], prefs['title_font_family'], c_footer, width, band_top + pad // 2, height // 2, measure_only=True)
    y = _draw_block(draw, subtitle, prefs['subtitle_font_size'], prefs['subtitle_font_family'], c_footer, width, y + pad // 4, height * 2 // 3, max_lines=3, measure_only=True)
    band_bottom = y + pad // 2
    radius = max(8, width // 60)
    draw.rounded_rectangle((0, band_top, width - 1, band_bottom), radius=radius, fill=c_title)
    draw.rectangle((0, 0, int(width * 0.04), height), fill=c_title)
    y = _draw_block(draw, title, prefs['title_font_size'], prefs['title_font_family'], c_footer, width, band_top + pad // 2, height // 2)
    y = _draw_block(draw, subtitle, prefs['subtitle_font_size'], prefs['subtitle_font_family'], c_footer, width, y + pad // 4, height * 2 // 3, max_lines=3)
    y = band_bottom
    footer_top = _draw_block(draw, footer, prefs['footer_font_size'], prefs['footer_font_family'], c_subtitle, width, y + pad, height - pad, align_bottom=True, max_lines=4)
    if logo_path:
        try:
            logo = Image.open(logo_path).convert('RGBA')
            box_top, box_bottom = y + pad, height - pad - int(prefs['footer_font_size'] * 1.2 * 2)
            if box_bottom - box_top > 50:
                scaled, lw, lh = fit_image(logo.width, logo.height, width - 2 * pad, box_bottom - box_top)
                if scaled:
                    logo = logo.resize((lw, lh), Image.LANCZOS)
                img.paste(logo, ((width - logo.width) // 2, box_top + (box_bottom - box_top - logo.height) // 2), logo)
        except Exception:
            pass
    return img


def _to_bytes(img: Image.Image, fmt: str = 'JPEG') -> bytes:
    buf = BytesIO()
    img.convert('RGB').save(buf, fmt, quality=90)
    return buf.getvalue()


def generate_cover(mi, prefs=None, as_qimage: bool = False) -> bytes:
    img = _render(mi, prefs)
    return img if as_qimage else _to_bytes(img)


def create_cover(title: str, authors, series: str | None = None, series_index: float | None = 1, prefs=None, as_qimage: bool = False) -> bytes:
    'Create a cover from the specified title, author and series.'
    from ebook_convert.ebooks.metadata.book.base import Metadata

    mi = Metadata(title, authors)
    if series:
        mi.series, mi.series_index = series, series_index
    return generate_cover(mi, prefs=prefs, as_qimage=as_qimage)


def calibre_cover2(title: str, author_string: str = '', series_string: str = '', prefs=None, as_qimage: bool = False, logo_path: str | None = None) -> bytes:
    from ebook_convert.ebooks.metadata.book.base import Metadata

    mi = Metadata(title, [author_string] if author_string else [])
    if series_string:
        mi.series, mi.series_index = series_string, None
    sprefs = override_prefs(prefs or cprefs)
    scale_cover(sprefs, 800.0 / sprefs['cover_height'])
    img = _render(mi, sprefs, logo_path=logo_path or I('library.png'))
    return img if as_qimage else _to_bytes(img)


def message_image(text: str, width: int = 500, height: int = 400, font_size: int = 20) -> bytes:
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    font = _font(font_size)
    lines = _wrap(draw, text, font, width - 20)
    line_height = int(font_size * 1.3)
    y = max(10, (height - line_height * len(lines)) // 2)
    for line in lines:
        draw.text((10, y), line, font=font, fill='black')
        y += line_height
    return _to_bytes(img, 'PNG')


def generate_masthead(title: str, output_path: str | None = None, width: int = 600, height: int = 60, as_qimage: bool = False, font_family: str | None = None):
    font_family = font_family or cprefs['title_font_family'] or 'Liberation Serif'
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    font = _font((height * 3) // 4, font_family)
    draw.text((4, height // 8), sanitize(title), font=font, fill='black')
    if as_qimage:
        return img
    data = _to_bytes(img, 'PNG')
    if output_path is None:
        return data
    with open(output_path, 'wb') as f:
        f.write(data)
