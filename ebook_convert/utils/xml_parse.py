import os
import tempfile
import unittest

from lxml import etree, html


# resolving of SYSTEM entities is turned off as entities can cause
# reads of local files, for example:
# <!DOCTYPE foo [ <!ENTITY passwd SYSTEM "file:///etc/passwd" >]>
fs = etree.fromstring
hfs = html.fromstring


class Resolver(etree.Resolver):

    def resolve(self, url, id, context):
        return self.resolve_string('', context)


def create_parser(recover, encoding=None):
    parser = etree.XMLParser(recover=recover, no_network=True, encoding=encoding)
    parser.resolvers.add(Resolver())
    return parser


def create_html_parser(recover, encoding=None):
    parser = html.HTMLParser(recover=recover, no_network=True, encoding=encoding)
    parser.resolvers.add(Resolver())
    return parser


def prepare_for_parsing(string_or_bytes):
    encoding = None
    if isinstance(string_or_bytes, str):
        # libxml2 anyway converts to UTF-8 to parse internally
        # and does so with bugs, see
        # https://bugs.launchpad.net/lxml/+bug/2125756
        string_or_bytes = string_or_bytes.encode('utf-8')
        encoding = 'utf-8'
    return string_or_bytes, encoding


def safe_xml_fromstring(string_or_bytes, recover=True):
    raw, encoding = prepare_for_parsing(string_or_bytes)
    return fs(raw, parser=create_parser(recover, encoding=encoding))


def safe_html_fromstring(string_or_bytes, recover=True):
    raw, encoding = prepare_for_parsing(string_or_bytes)
    return hfs(raw, parser=create_html_parser(recover, encoding=encoding))


def fragment_fromstring(string_or_bytes):
    raw, encoding = prepare_for_parsing(string_or_bytes)
    return html.fragment_fromstring(raw, parser=create_html_parser(True, encoding=encoding))


def document_fromstring(string_or_bytes, ensure_head_body=False):
    raw, encoding = prepare_for_parsing(string_or_bytes)
    return html.document_fromstring(raw, parser=create_html_parser(True, encoding=encoding),
                                    ensure_head_body=ensure_head_body)


def find_tests():

    class TestXMLParse(unittest.TestCase):

        def setUp(self):
            with tempfile.NamedTemporaryFile(delete=False) as tf:
                tf.write(b'external')
                self.temp_file = tf.name

        def tearDown(self):
            os.remove(self.temp_file)

        def test_safe_xml_fromstring(self):
            templ = '<!DOCTYPE foo [ <!ENTITY e {id} "{val}" > ]><r>&e;</r>'
            external = 'file:///' + self.temp_file.replace(os.sep, '/')
            self.assertEqual(etree.fromstring(templ.format(id='SYSTEM',
                                                           val=external)).text,
                             'external')
            for eid, val, expected in (
                ('', 'normal entity', 'normal entity'),
                ('', external, external),

                ('SYSTEM', external, None),
                ('SYSTEM', 'http://example.com', None),

                ('PUBLIC', external, None),
                ('PUBLIC', 'http://example.com', None),
            ):
                got = getattr(etree.fromstring(templ.format(id=eid, val=val)),
                              'text', None)
                self.assertEqual(got, expected)

    return unittest.defaultTestLoader.loadTestsFromTestCase(TestXMLParse)


if __name__ == '__main__':
    from ebook_convert.utils.run_tests import run_tests
    run_tests(find_tests)
