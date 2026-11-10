#!/usr/bin/env python
# License: GPLv3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
"""Upgrade an EPUB 2 book to EPUB 3."""

import sys
import uuid

from ebook_convert import constants as const
from ebook_convert.ebooks import escape_xpath_attr
from ebook_convert.ebooks.conversion.plugins.epub_input import ADOBE_OBFUSCATION
from ebook_convert.ebooks.conversion.plugins.epub_input import IDPF_OBFUSCATION
from ebook_convert.ebooks.metadata.opf3 import XPath
from ebook_convert.ebooks.metadata.opf_2_to_3 import upgrade_metadata
from ebook_convert.ebooks.oeb import base
from ebook_convert.ebooks.oeb.parse_utils import ensure_namespace_prefixes
from ebook_convert.ebooks.oeb.polish.opf import get_book_language
from ebook_convert.ebooks.oeb.polish.opf import set_package_language
from ebook_convert.ebooks.oeb.polish.toc import commit_nav_toc
from ebook_convert.ebooks.oeb.polish.toc import find_existing_ncx_toc
from ebook_convert.ebooks.oeb.polish.toc import get_landmarks
from ebook_convert.ebooks.oeb.polish.toc import get_toc
from ebook_convert.ebooks.oeb.polish.utils import OEB_FONTS
from ebook_convert.ebooks.oeb.transforms.guide import CUSTOM_GUIDE_TYPE_PREFIX
from ebook_convert.ebooks.oeb.transforms.guide import KNOWN_GUIDE_TYPES


def uuid4():
    return str(uuid.uuid4())


def add_properties(item, *props):
    existing = set((item.get('properties') or '').split())
    existing |= set(props)
    item.set('properties', ' '.join(sorted(existing)))


def fix_font_mime_types(container):
    changed = False
    for item in container.opf_xpath(
            '//opf:manifest/opf:item[@href and @media-type]'):
        mt = item.get('media-type') or ''
        if mt.lower() in OEB_FONTS:
            name = container.href_to_name(item.get('href'), container.opf_name)
            if name is None:  # href does not point into the book
                continue
            item.set('media-type', container.guess_type(name))
            changed = True
    return changed


def migrate_obfuscated_fonts(container):
    if not getattr(container, 'obfuscated_fonts', None):
        return
    name_to_elem_map = {}
    for em, cr in container.iter_encryption_entries():
        alg = em.get('Algorithm')
        if cr is None or alg not in {ADOBE_OBFUSCATION, IDPF_OBFUSCATION}:
            continue
        name = container.href_to_name(cr.get('URI'))
        name_to_elem_map[name] = em, cr
    package_id, raw_unique_identifier, idpf_key = \
        container.read_raw_unique_identifier()
    if not idpf_key:
        if not package_id:
            package_id = uuid4()
            container.opf.set('unique-identifier', package_id)
        existing = container.opf_xpath(
            '//*[@id=%s]' % escape_xpath_attr(package_id))
        if existing:  # the unique identifier element exists but is empty
            ident = existing[0]
        else:
            metadata = XPath('./opf:metadata')(container.opf)[0]
            ident = metadata.makeelement(base.tag('dc', 'identifier'),
                                         id=package_id)
            metadata.append(ident)
        ident.text = uuid4()
        package_id, raw_unique_identifier, idpf_key = \
            container.read_raw_unique_identifier()
    for name in tuple(container.obfuscated_fonts):
        try:
            em, cr = name_to_elem_map[name]
        except KeyError:
            container.obfuscated_fonts.pop(name)
            continue
        em.set('Algorithm', IDPF_OBFUSCATION)
        cr.set('URI', container.name_to_href(name))
        container.obfuscated_fonts[name] = (IDPF_OBFUSCATION, idpf_key)
    container.commit_item('META-INF/encryption.xml')


def collect_properties(container):
    for item in container.opf_xpath(
            '//opf:manifest/opf:item[@href and @media-type]'):
        mt = item.get('media-type') or ''
        if mt.lower() not in base.OEB_DOCS:
            continue
        name = container.href_to_name(item.get('href'), container.opf_name)
        if name is None:  # href does not point into the book
            continue
        try:
            root = container.parsed(name)
        except KeyError:
            continue
        root = ensure_namespace_prefixes(root, {'epub': const.EPUB_NS})
        properties = set()
        container.replace(name, root)  # Ensure entities are converted
        if base.xpath(root, '//svg:svg'):
            properties.add('svg')
        if base.xpath(root, '//h:script'):
            properties.add('scripted')
        if base.xpath(root, '//mathml:math'):
            properties.add('mathml')
        if base.xpath(root, '//epub:switch'):
            properties.add('switch')
        if properties:
            add_properties(item, *tuple(properties))


def add_lang_attributes(container):
    # The lang attribute is not valid in the XHTML 1.1 used by EPUB 2, so
    # files may only have xml:lang, add lang as well for software that only
    # looks at it
    for name, mt in container.mime_map.items():
        if mt.lower() not in base.OEB_DOCS:
            continue
        root = container.parsed(name)
        lang = root.get(base.tag('xml', 'lang'))
        if lang and not root.get('lang'):
            root.set('lang', lang)
            container.dirty(name)


guide_epubtype_map = {
    'acknowledgements': 'acknowledgments',
    'other.afterword': 'afterword',
    'other.appendix': 'appendix',
    'other.backmatter': 'backmatter',
    'bibliography': 'bibliography',
    'text': 'bodymatter',
    'other.chapter': 'chapter',
    'colophon': 'colophon',
    'other.conclusion': 'conclusion',
    'other.contributors': 'contributors',
    'copyright-page': 'copyright-page',
    'cover': 'cover',
    'dedication': 'dedication',
    'other.division': 'division',
    'epigraph': 'epigraph',
    'other.epilogue': 'epilogue',
    'other.errata': 'errata',
    'other.footnotes': 'footnotes',
    'foreword': 'foreword',
    'other.frontmatter': 'frontmatter',
    'glossary': 'glossary',
    'other.halftitlepage': 'halftitlepage',
    'other.imprint': 'imprint',
    'other.imprimatur': 'imprimatur',
    'index': 'index',
    'other.introduction': 'introduction',
    'other.landmarks': 'landmarks',
    'other.loa': 'loa',
    'loi': 'loi',
    'lot': 'lot',
    'other.lov': 'lov',
    'notes': '',
    'other.notice': 'notice',
    'other.other-credits': 'other-credits',
    'other.part': 'part',
    'other.preamble': 'preamble',
    'preface': 'preface',
    'other.prologue': 'prologue',
    'other.rearnotes': 'rearnotes',
    'other.subchapter': 'subchapter',
    'title-page': 'titlepage',
    'toc': 'toc',
    'other.volume': 'volume',
    'other.warning': 'warning',
}
epubtype_guide_map = {v: k for k, v in guide_epubtype_map.items() if v}


def epubtype_for_guide_type(gtype):
    if gtype.lower().startswith(CUSTOM_GUIDE_TYPE_PREFIX):
        return gtype[len(CUSTOM_GUIDE_TYPE_PREFIX):] or None
    return guide_epubtype_map.get(gtype.lower())


def guide_type_for_epubtype(epubtype):
    # Conversion keeps only known guide types, so use a custom type for the
    # rest
    gtype = epubtype_guide_map.get(epubtype)
    return (gtype if gtype in KNOWN_GUIDE_TYPES else
            CUSTOM_GUIDE_TYPE_PREFIX + epubtype)


def create_nav(container, toc, landmarks, previous_nav=None):
    lang = get_book_language(container)
    if lang == 'und':
        lang = None
    if landmarks:
        for entry in landmarks:
            entry['type'] = epubtype_for_guide_type(entry['type'])
            if (entry['type'] == 'cover' and
                    container.mime_map.get(entry['dest'], '').lower() in
                    base.OEB_DOCS):
                container.apply_unique_properties(entry['dest'],
                                                  'calibre:title-page')
    commit_nav_toc(container, toc, lang=lang, landmarks=landmarks,
                   previous_nav=previous_nav)


def epub_2_to_3(container, report, previous_nav=None, remove_ncx=True,
                set_package_lang=True):
    upgrade_metadata(container.opf)
    collect_properties(container)
    add_lang_attributes(container)
    toc = get_toc(container)
    toc_name = find_existing_ncx_toc(container)
    if toc_name and remove_ncx:
        container.remove_item(toc_name)
        container.opf_xpath('./opf:spine')[0].attrib.pop('toc', None)
    landmarks = get_landmarks(container)
    for guide in container.opf_xpath('./opf:guide'):
        guide.getparent().remove(guide)
    create_nav(container, toc, landmarks, previous_nav)
    container.opf.set('version', '3.0')
    if set_package_lang:
        # The default language of the OPF, only valid in EPUB 3
        set_package_language(container)
    if fix_font_mime_types(container):
        container.refresh_mime_map()
    migrate_obfuscated_fonts(container)
    container.dirty(container.opf_name)


def upgrade_book(container, report, remove_ncx=True):
    if (container.book_type not in ('epub', 'kepub') or
            container.opf_version_parsed.major >= 3):
        report('No upgrade needed')
        return False
    epub_2_to_3(container, report, remove_ncx=remove_ncx)
    report('Updated EPUB from version 2 to 3')
    return True


if __name__ == '__main__':
    from ebook_convert.ebooks.oeb.polish.container import get_container
    from ebook_convert.logging import default_log
    default_log.filter_level = default_log.DEBUG
    inbook = sys.argv[-1]
    ebook = get_container(inbook, default_log)
    if upgrade_book(ebook, print):
        outbook = (inbook.rpartition('.')[0] + '-upgraded.' +
                   inbook.rpartition('.')[-1])
        ebook.commit(outbook)
        print('Upgraded book written to:', outbook)
