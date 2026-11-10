from lxml import etree

from ebook_convert import constants as const
from ebook_convert.ebooks.oeb import base
from ebook_convert.utils.localization import canonicalize_lang
from ebook_convert.utils.localization import lang_as_bcp47


def get_book_language(container):
    for lang in container.opf_xpath('//dc:language'):
        raw = lang.text
        if raw:
            code = canonicalize_lang(raw.split(',')[0].strip())
            if code:
                return code


def get_book_language_tag(container):
    # The language of the book as a BCP 47 language tag, for use in the lang
    # attributes of HTML files
    for lang in container.opf_xpath('//dc:language'):
        ans = lang_as_bcp47(lang.text or '')
        if ans:
            return ans
    return None


PACKAGE_LANG = base.tag('xml', 'lang')


def has_package_language(container):
    return bool((container.opf.get(PACKAGE_LANG) or '').strip())


def set_package_language(container, lang=None, replace=False):
    """
    Set the xml:lang attribute of the <package> element of an EPUB 3 OPF,
    which is the default language of the OPF and is required by accessibility
    checkers such as Ace. Defaults to the language of the book. Only set if
    missing, unless ``replace`` is True. Returns True if the OPF was changed.
    Not valid in the OPF of EPUB 2, so callers must check the OPF version.
    """
    lang = lang or get_book_language_tag(container)
    if not lang:
        return False
    current = container.opf.get(PACKAGE_LANG)
    if current == lang or (has_package_language(container) and not replace):
        return False
    container.opf.set(PACKAGE_LANG, lang)
    container.dirty(container.opf_name)
    return True


def set_guide_item(container, item_type, title, name, frag=None):
    ref_tag = base.tag('opf', 'reference')
    href = None
    if name:
        href = container.name_to_href(name, container.opf_name)
        if frag:
            href += '#' + frag

    guides = container.opf_xpath('//opf:guide')
    if not guides and href:
        g = container.opf.makeelement(base.tag('opf', 'guide'),
                                      nsmap={'opf': const.OPF2_NS})
        container.insert_into_xml(container.opf, g)
        guides = [g]

    for guide in guides:
        matches = []
        for child in guide.iterchildren(etree.Element):
            if (child.tag == ref_tag and
                    child.get('type', '').lower() == item_type.lower()):
                matches.append(child)
        if not matches and href:
            r = guide.makeelement(ref_tag, type=item_type,
                                  nsmap={'opf': const.OPF2_NS})
            container.insert_into_xml(guide, r)
            matches.append(r)
        for m in matches:
            if href:
                m.set('title', title)
                m.set('href', href)
                m.set('type', item_type)
            else:
                container.remove_from_xml(m)
    container.dirty(container.opf_name)
