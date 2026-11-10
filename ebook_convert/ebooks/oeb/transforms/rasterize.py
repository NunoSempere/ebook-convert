"""
SVG rasterization transform.

Calibre renders SVG with Qt.  Here the rendering is done by resvg (through the
``resvg_py`` wheel), a complete SVG renderer with no system dependencies.
"""
import os
import re
import urllib.parse
from io import BytesIO

from ebook_convert import constants as const
from ebook_convert.ebooks.oeb import base
from ebook_convert.ebooks.oeb.base import SVG_MIME, PNG_MIME
from ebook_convert.ebooks.oeb.base import xml2str, xpath
from ebook_convert.ebooks.oeb.base import urlnormalize
from ebook_convert.ebooks.oeb.stylizer import Stylizer
from ebook_convert.ptempfile import PersistentTemporaryFile
from ebook_convert.utils.imghdr import what


IMAGE_TAGS = {base.tag('xhtml', 'img'), base.tag('xhtml', 'object')}
KEEP_ATTRS = {'class', 'style', 'width', 'height', 'align'}


class Unavailable(Exception):
    pass


def renderer_available():
    """Return True if the resvg renderer can be imported."""
    try:
        import resvg_py  # noqa: F401
    except ImportError:
        return False
    return True


def _length(value):
    """Parse an SVG length attribute (``"120"``, ``"120px"``, ``"2in"``) into
    CSS pixels; return None for percentages or garbage."""
    if value is None:
        return None
    m = re.match(r'^\s*([0-9.]+)\s*([a-z%]*)\s*$', value, re.I)
    if m is None:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2).lower()
    factor = {'': 1, 'px': 1, 'pt': 96/72., 'pc': 16, 'in': 96, 'cm': 96/2.54,
              'mm': 96/25.4, 'em': 16, 'ex': 8}.get(unit)
    if factor is None:
        return None
    return num * factor


def svg_intrinsic_size(root, logger=None):
    """Return the (width, height) an SVG root element declares, in pixels.

    Uses the width/height attributes, then the viewBox, then falls back to
    100x100 like Qt's QSvgRenderer does.
    """
    width = _length(root.get('width'))
    height = _length(root.get('height'))
    view_box = root.get('viewBox', root.get('viewbox'))
    box = None
    if view_box is not None:
        try:
            box = [float(x) for x in filter(None, re.split('[, ]+', view_box))]
            if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
                raise ValueError(view_box)
        except (TypeError, ValueError):
            box = None
            if logger is not None:
                logger.warning('SVG image has invalid viewBox="%s", ignoring '
                               'the viewBox', view_box)
    if width and height:
        return width, height
    if box is not None:
        bw, bh = box[2], box[3]
        if width:
            return width, width * bh / bw
        if height:
            return height * bw / bh, height
        return bw, bh
    return 100., 100.


def fit_size(size, width=0, height=0):
    """Scale ``size`` to fit inside ``width`` x ``height`` keeping the aspect
    ratio (both bounds optional), returning integer pixel dimensions."""
    w, h = size
    if width and height:
        scale = min(width / w, height / h)
    elif width:
        scale = width / w
    elif height:
        scale = height / h
    else:
        scale = 1.
    return max(1, int(round(w * scale))), max(1, int(round(h * scale)))


def render_svg(svg_bytes, width=0, height=0, size=None, bgcolor='#ffffff'):
    """Render SVG markup to PNG bytes of the given size using resvg.

    ``size`` is the intrinsic size to scale from; when omitted it is read
    from the markup.
    """
    import resvg_py
    if size is None:
        from ebook_convert.utils.xml_parse import safe_xml_fromstring
        size = svg_intrinsic_size(safe_xml_fromstring(svg_bytes))
    w, h = fit_size(size, width, height)
    if isinstance(svg_bytes, bytes):
        svg_bytes = svg_bytes.decode('utf-8', 'replace')
    png = resvg_py.svg_to_bytes(svg_string=svg_bytes, width=w, height=h,
                                background=bgcolor)
    return bytes(png)


class SVGRasterizer(object):

    def __init__(self, base_css=''):
        if not renderer_available():
            raise Unavailable('SVG rasterization needs the resvg_py package; '
                              'SVG images are left as they are')
        self.base_css = base_css

    @classmethod
    def config(cls, cfg):
        return cfg

    @classmethod
    def generate(cls, opts):
        return cls()

    def __call__(self, oeb, context):
        oeb.logger.info('Rasterizing SVG images...')
        self.temp_files = []
        self.stylizer_cache = {}
        self.oeb = oeb
        self.opts = context
        self.profile = context.dest
        self.images = {}
        self.dataize_manifest()
        self.rasterize_spine()
        self.rasterize_cover()
        for pt in self.temp_files:
            try:
                os.remove(pt)
            except:
                pass

    def rasterize_svg(self, elem, width=0, height=0, format='PNG'):
        logger = self.oeb.logger
        size = svg_intrinsic_size(elem, logger)
        for image in elem.xpath('descendant::*[local-name()="image" and '
                                '@height and contains(@height, "%")]'):
            logger.info('Found SVG image height in %, trying to convert...')
            try:
                h = float(image.get('height').replace('%', ''))/100.
                image.set('height', str(h*size[1]))
            except Exception:
                logger.exception('Failed to convert percentage height: %s',
                                 image.get('height'))
        w, h = fit_size(size, width, height)
        logger.info('Rasterizing %r to %dx%d', elem, w, h)
        data = render_svg(xml2str(elem, with_tail=False), w, h, size=size)
        if format.upper() != 'PNG':
            from ebook_convert.utils.img import image_to_data
            data = image_to_data(data, fmt=format)
        return data

    def dataize_manifest(self):
        for item in self.oeb.manifest.values():
            if item.media_type == SVG_MIME and item.data is not None:
                self.dataize_svg(item)

    def dataize_svg(self, item, svg=None):
        if svg is None:
            svg = item.data
        hrefs = self.oeb.manifest.hrefs
        for elem in xpath(svg, '//svg:*[@xl:href]'):
            href = urlnormalize(elem.attrib[base.tag('xlink', 'href')])
            path = urllib.parse.urldefrag(href)[0]
            if not path:
                continue
            abshref = item.abshref(path)
            if abshref not in hrefs:
                continue
            linkee = hrefs[abshref]
            data = linkee.bytes_representation
            ext = what(None, data) or 'jpg'
            with PersistentTemporaryFile(suffix='.'+ext) as pt:
                pt.write(data)
                self.temp_files.append(pt.name)
            elem.attrib[base.tag('xlink', 'href')] = pt.name
        return svg

    def stylizer(self, item):
        ans = self.stylizer_cache.get(item, None)
        if ans is None:
            ans = Stylizer(item.data, item.href, self.oeb, self.opts,
                    self.profile, base_css=self.base_css)
            self.stylizer_cache[item] = ans
        return ans

    def rasterize_spine(self):
        for item in self.oeb.spine:
            self.rasterize_item(item)

    def rasterize_item(self, item):
        html = item.data
        hrefs = self.oeb.manifest.hrefs
        for elem in xpath(html, '//h:img[@src]'):
            src = urlnormalize(elem.attrib['src'])
            image = hrefs.get(item.abshref(src), None)
            if image and image.media_type == SVG_MIME:
                style = self.stylizer(item).style(elem)
                self.rasterize_external(elem, style, item, image)
        for elem in xpath(html, '//h:object[@type="%s" and @data]' % SVG_MIME):
            data = urlnormalize(elem.attrib['data'])
            image = hrefs.get(item.abshref(data), None)
            if image and image.media_type == SVG_MIME:
                style = self.stylizer(item).style(elem)
                self.rasterize_external(elem, style, item, image)
        for elem in xpath(html, '//svg:svg'):
            style = self.stylizer(item).style(elem)
            self.rasterize_inline(elem, style, item)

    def rasterize_inline(self, elem, style, item):
        width = style['width']
        height = style['height']
        width = (width / 72) * self.profile.dpi
        height = (height / 72) * self.profile.dpi
        elem = self.dataize_svg(item, elem)
        data = self.rasterize_svg(elem, width, height)
        manifest = self.oeb.manifest
        href = os.path.splitext(item.href)[0] + '.png'
        id, href = manifest.generate(item.id, href)
        manifest.add(id, href, PNG_MIME, data=data)
        img = elem.makeelement(base.tag('xhtml', 'img'), src=item.relhref(href))
        elem.getparent().replace(elem, img)
        # Keep the text that followed the <svg> element
        img.tail = elem.tail
        for prop in ('width', 'height'):
            if prop in elem.attrib:
                img.attrib[prop] = elem.attrib[prop]

    def rasterize_external(self, elem, style, item, svgitem):
        width = style['width']
        height = style['height']
        width = (width / 72) * self.profile.dpi
        height = (height / 72) * self.profile.dpi
        svg = self.dataize_svg(svgitem)
        size = svg_intrinsic_size(svg, self.oeb.logger)
        w, h = fit_size(size, width, height)
        key = (svgitem.href, w, h)
        if key in self.images:
            href = self.images[key]
        else:
            logger = self.oeb.logger
            logger.info('Rasterizing %r to %dx%d', svgitem.href, w, h)
            data = render_svg(xml2str(svg), w, h, size=size)
            manifest = self.oeb.manifest
            href = os.path.splitext(svgitem.href)[0] + '.png'
            id, href = manifest.generate(svgitem.id, href)
            manifest.add(id, href, PNG_MIME, data=data)
            self.images[key] = href
        elem.tag = base.tag('xhtml', 'img')
        for attr in list(elem.attrib):
            if attr not in KEEP_ATTRS:
                del elem.attrib[attr]
        elem.attrib['src'] = item.relhref(href)
        if elem.text:
            elem.attrib['alt'] = elem.text
            elem.text = None
        for child in list(elem):
            elem.remove(child)

    def rasterize_cover(self):
        covers = self.oeb.metadata.cover
        if not covers:
            return
        if str(covers[0]) not in self.oeb.manifest.ids:
            self.oeb.logger.warning('Cover not in manifest, skipping.')
            self.oeb.metadata.clear('cover')
            return
        cover = self.oeb.manifest.ids[str(covers[0])]
        if not cover.media_type == SVG_MIME:
            return
        width = (self.profile.width / 72) * self.profile.dpi
        height = (self.profile.height / 72) * self.profile.dpi
        data = self.rasterize_svg(cover.data, width, height)
        href = os.path.splitext(cover.href)[0] + '.png'
        id, href = self.oeb.manifest.generate(cover.id, href)
        self.oeb.manifest.add(id, href, PNG_MIME, data=data)
        covers[0].value = id
