"""The pure-Python PalmDOC compressor must match Calibre's reference encoder."""
import random
import unittest

from ebook_convert.ebooks.compression import palmdoc


def test_calibre_palmdoc_suite():
    result = unittest.TextTestRunner(verbosity=0).run(palmdoc.find_tests())
    assert result.wasSuccessful(), result.failures + result.errors


def test_fast_compressor_matches_reference_on_random_records():
    rnd = random.Random(7)
    words = [bytes(rnd.randrange(97, 123) for _ in range(rnd.randrange(1, 9)))
             for _ in range(60)]
    cases = [b' '.join(rnd.choice(words) for _ in range(rnd.randrange(1, 800)))
             for _ in range(20)]
    for alphabet in (1, 2, 3, 5, 40, 256):
        cases += [bytes(rnd.randrange(0, alphabet) for _ in range(rnd.randrange(0, 4100)))
                  for _ in range(5)]
    for data in cases:
        out = palmdoc.compress_doc(data)
        assert out == palmdoc.py_compress_doc(data)
        assert palmdoc.decompress_doc(out) == data
