from ebook_convert.utils import icu


def test_sort_key_orders_case_and_accent_insensitively():
    words = ['zebra', 'Apple', 'éclair', 'apple', 'Eclair', 'banana']
    assert sorted(words, key=icu.sort_key) == [
        'apple', 'Apple', 'banana', 'éclair', 'Eclair', 'zebra']
    assert icu.strcmp('a', 'B') < 0
    assert icu.primary_strcmp('e', 'É') == 0
    assert icu.sort_key(None) == ('', '', '')


def test_numeric_sort_key():
    names = ['file10', 'file2', 'file1']
    assert sorted(names, key=icu.numeric_sort_key) == ['file1', 'file2',
                                                       'file10']


def test_partition_by_first_letter():
    groups = icu.partition_by_first_letter(['banana', 'Apple', 'avocado',
                                            'ébène', 'cherry'])
    assert list(groups) == ['A', 'B', 'C', 'É']
    assert groups['A'] == ['Apple', 'avocado']
    assert groups['É'] == ['ébène']


def test_misc_helpers():
    assert icu.ord_string('ab') == (97, 98)
    assert icu.capitalize('hELLO') == 'Hello'
    assert icu.character_name('é') == 'LATIN SMALL LETTER E WITH ACUTE'
    assert icu.character_name_from_code(0x41) == 'LATIN CAPITAL LETTER A'
    assert icu.normalize('é') == 'é'
    assert icu.find('LO', 'hello')[0] == 3
    assert icu.primary_contains('e', 'café')
    assert icu.contractions() == frozenset()
    assert icu.utf16_length('\U0001F600') == 2
