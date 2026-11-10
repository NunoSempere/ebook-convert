# License: GPLv3 Copyright: 2019, Kovid Goyal <kovid at kovidgoyal.net>
import bs4
from ebook_convert.utils import html5

from ebook_convert.ebooks import chardet
from ebook_convert.utils import cleantext


def parse_html(markup):
    if isinstance(markup, str):
        markup = chardet.strip_encoding_declarations(markup)
        markup = chardet.substitute_entites(markup)
    else:
        markup = chardet.xml_to_unicode(markup, strip_encoding_pats=True,
                                        resolve_entities=True)[0]
    markup = cleantext.clean_xml_chars(markup)
    return html5.parse_soup(markup)


def prettify(soup):
    ans = soup.prettify()
    if isinstance(ans, bytes):
        ans = ans.decode('utf-8')
    return ans


def html5_parser(markup='', *a, **kw):
    return parse_html(markup)


def beautiful_soup_parser(markup='', *a, **kw):
    return bs4.BeautifulSoup(markup, 'xml')
