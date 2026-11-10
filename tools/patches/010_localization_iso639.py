"""Load ISO-639 language data from the bundled iso_639-3.json instead of the
msgpack file Calibre generates at build time; no ISO-3166 country data."""

TARGET = 'utils/localization.py'

REPLACEMENTS = [
    (
        '''def _load_iso639() -> ISO639Data:
    global _iso639
    if _iso639 is None:
        ip = P('localization/iso639.calibre_msgpack', allow_user_override=False, data=True)
        from ebook_convert.utils.serialize import msgpack_loads

        _iso639 = msgpack_loads(ip)
        if 'by_3' not in _iso639:
            _iso639['by_3'] = _iso639['by_3t']
    return _iso639
''',
        '''def _load_iso639() -> ISO639Data:
    # ebook-convert: built from the iso-codes JSON shipped in data/, the same
    # way calibre's setup/translations.py builds iso639.calibre_msgpack
    global _iso639
    if _iso639 is None:
        import json

        root = json.loads(P('iso_639-3.json', allow_user_override=False, data=True))
        by_2, by_3, m2to3, m3to2, nm = {}, {}, {}, {}, {}
        codes2, codes3 = set(), set()
        for x in root['639-3']:
            two = x.get('alpha_2')
            threeb = x.get('alpha_3')
            if threeb is None:
                continue
            name = x.get('inverted_name') or x.get('name')
            if not name or name[0] in '!~=/\\'"':
                continue
            if two is not None:
                by_2[two] = name
                codes2.add(two)
                m2to3[two] = threeb
                m3to2[threeb] = two
            codes3.add(threeb)
            by_3[threeb] = name
            nm[name.lower()] = threeb
        _iso639 = {'by_2': by_2, 'by_3': by_3, 'codes2': codes2, 'codes3': codes3, '2to3': m2to3, '3to2': m3to2, 'name_map': nm}
    return _iso639
''',
    ),
    (
        '''    if _iso3166_cache is None:
        from ebook_convert.utils.serialize import msgpack_loads

        _iso3166_cache = msgpack_loads(P('localization/iso3166.calibre_msgpack', allow_user_override=False, data=True))
    return _iso3166_cache
''',
        '''    if _iso3166_cache is None:
        # ebook-convert: no country code data is bundled
        _iso3166_cache = {'names': {}, 'codes': frozenset(), 'three_map': {}}
    return _iso3166_cache
''',
    ),
]
