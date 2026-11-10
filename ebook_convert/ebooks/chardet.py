import codecs
import re

from ebook_convert.utils import entities


_encoding_pats = (
    # XML declaration
    r'<\?[^<>]+encoding\s*=\s*[\'"](.*?)[\'"][^<>]*>',
    # HTML 5 charset
    r'''<meta\s+charset=['"]([-_a-z0-9]+)['"][^<>]*>(?:\s*</meta>){0,1}''',
    # HTML 4 Pragma directive
    r'''<meta\s+?[^<>]*?content\s*=\s*['"][^'"]*?charset=([-_a-z0-9]+)[^'"]*?['"][^<>]*>(?:\s*</meta>){0,1}''',
)


def compile_pats(binary):
    for raw in _encoding_pats:
        if binary:
            raw = raw.encode('ascii')
        yield re.compile(raw, flags=re.IGNORECASE)


class LazyEncodingPats(object):

    def __call__(self, binary=False):
        attr = 'binary_pats' if binary else 'unicode_pats'
        pats = getattr(self, attr, None)
        if pats is None:
            pats = tuple(compile_pats(binary))
            setattr(self, attr, pats)
        for pat in pats:
            yield pat


lazy_encoding_pats = LazyEncodingPats()
ENTITY_PATTERN = re.compile(r'&(\S+?);')


def strip_encoding_declarations(raw, limit=50*1024, preserve_newlines=False):
    prefix = raw[:limit]
    suffix = raw[limit:]
    is_binary = isinstance(raw, bytes)
    if preserve_newlines:
        if is_binary:
            sub = lambda m: b'\n' * m.group().count(b'\n')
        else:
            sub = lambda m: '\n' * m.group().count('\n')
    else:
        sub = b'' if is_binary else u''
    for pat in lazy_encoding_pats(is_binary):
        prefix = pat.sub(sub, prefix)
    raw = prefix + suffix
    return raw


def replace_encoding_declarations(raw, enc='utf-8', limit=50*1024):
    prefix = raw[:limit]
    suffix = raw[limit:]
    changed = [False]
    is_binary = isinstance(raw, bytes)
    if is_binary:
        if not isinstance(enc, bytes):
            enc = enc.encode('ascii')
    else:
        if isinstance(enc, bytes):
            enc = enc.decode('ascii')

    def sub(m):
        ans = m.group()
        if m.group(1).lower() != enc.lower():
            changed[0] = True
            start, end = m.start(1) - m.start(0), m.end(1) - m.end(0)
            ans = ans[:start] + enc + ans[end:]
        return ans

    for pat in lazy_encoding_pats(is_binary):
        prefix = pat.sub(sub, prefix)
    raw = prefix + suffix
    return raw, changed[0]


def find_declared_encoding(raw, limit=50*1024):
    prefix = raw[:limit]
    is_binary = isinstance(raw, bytes)
    for pat in lazy_encoding_pats(is_binary):
        m = pat.search(prefix)
        if m is not None:
            ans = m.group(1)
            if is_binary:
                ans = ans.decode('ascii', 'replace')
            return ans


def substitute_entites(raw):
    return ENTITY_PATTERN.sub(entities.xml_entity_to_unicode, raw)


substitute_entities = substitute_entites  # for plugins that might use this

# Calibre afb2610676: python has no mac-centraleurope codec
_CHARSET_ALIASES = {"macintosh" : "mac-roman",
                    "x-sjis" : "shift-jis",
                    "mac-centraleurope": "cp1250"}


def detect(bytestring):
    # Calibre ad34b0ea3b / 5d126692f8: normalise the answer so callers can
    # rely on a lower case encoding string and a numeric confidence
    from chardet import detect as implementation
    if isinstance(bytestring, str):
        bytestring = bytestring.encode('utf-8', 'replace')
    try:
        ans = implementation(bytestring)
    except Exception:
        ans = {}
    ans = dict(ans or {})
    enc = ans.get('encoding')
    if enc:
        enc = enc.lower()
        ans['encoding'] = _CHARSET_ALIASES.get(enc, enc)
    else:
        ans['encoding'] = ''
    if ans.get('confidence') is None:
        ans['confidence'] = 0
    return ans


def force_encoding(raw, verbose, assume_utf8=False):
    from ebook_convert.constants_old import preferred_encoding

    try:
        chardet = detect(raw[:1024*50])
    except:
        chardet = {'encoding':preferred_encoding, 'confidence':0}
    encoding = chardet['encoding']
    if (chardet.get('confidence') or 0) < 1:
        if verbose:
            import sys
            print('WARNING: Encoding detection confidence for %s is %d%%' % (
                chardet['encoding'], (chardet.get('confidence') or 0) * 100),
                file=sys.stderr)
        if assume_utf8:
            encoding = 'utf-8'
    if not encoding:
        encoding = preferred_encoding
    encoding = encoding.lower()
    encoding = _CHARSET_ALIASES.get(encoding, encoding)
    if encoding == 'ascii':
        encoding = 'utf-8'
    return encoding


def detect_xml_encoding(raw, verbose=False, assume_utf8=False):
    if not raw or isinstance(raw, str):
        return raw, None
    for x in ('utf8', 'utf-16-le', 'utf-16-be'):
        bom = getattr(codecs, 'BOM_'+x.upper().replace('-16', '16').replace(
            '-', '_'))
        if raw.startswith(bom):
            return raw[len(bom):], x
    encoding = None
    for pat in lazy_encoding_pats(True):
        match = pat.search(raw)
        if match:
            encoding = match.group(1)
            encoding = encoding.decode('ascii', 'replace')
            break
    if encoding is None:
        if assume_utf8:
            # Calibre ad34b0ea3b: chardet confidence is unreliable, so try
            # a strict utf-8 decode first
            try:
                return raw.decode('utf-8'), 'utf-8'
            except UnicodeDecodeError:
                pass
        encoding = force_encoding(raw, verbose, assume_utf8=assume_utf8)
    if encoding.lower().strip() == 'macintosh':
        encoding = 'mac-roman'
    if encoding.lower().replace('_', '-').strip() in (
            'gb2312', 'chinese', 'csiso58gb231280', 'euc-cn', 'euccn',
            'eucgb2312-cn', 'gb2312-1980', 'gb2312-80', 'iso-ir-58'):
        # Microsoft Word exports to HTML with encoding incorrectly set to
        # gb2312 instead of gbk. gbk is a superset of gb2312, anyway.
        encoding = 'gbk'
    try:
        codecs.lookup(encoding)
    except LookupError:
        encoding = 'utf-8'

    return raw, encoding


def xml_to_unicode(raw, verbose=False, strip_encoding_pats=False,
                   resolve_entities=False, assume_utf8=False):
    '''
    Force conversion of byte string to unicode. Tries to look for XML/HTML
    encoding declaration first, if not found uses the chardet library and
    prints a warning if detection confidence is < 100%
    @return: (unicode, encoding used)
    '''
    if not raw:
        return '', None
    raw, encoding = detect_xml_encoding(raw, verbose=verbose,
            assume_utf8=assume_utf8)
    if not isinstance(raw, str):
        raw = raw.decode(encoding, 'replace')

    if strip_encoding_pats:
        raw = strip_encoding_declarations(raw)
    if resolve_entities:
        raw = substitute_entites(raw)

    return raw, encoding
