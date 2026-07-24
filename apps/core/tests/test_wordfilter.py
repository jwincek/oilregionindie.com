"""
Hardened community word filter (issue #91): leetspeak folding, separator
tolerance, and word-boundary anchoring to avoid the Scunthorpe problem.
"""
from django.test import TestCase

from apps.core.models import BlockedWord


class WordFilterTest(TestCase):
    def setUp(self):
        BlockedWord.objects.create(word="molly")

    def _hit(self, text):
        return "molly" in BlockedWord.check_content(text)

    def test_plain_match(self):
        self.assertTrue(self._hit("got any molly tonight"))

    def test_leetspeak_folded(self):
        self.assertTrue(self._hit("got any m0lly"))  # 0 -> o

    def test_symbol_folding(self):
        BlockedWord.objects.create(word="hash")
        self.assertIn("hash", BlockedWord.check_content("h@sh"))  # @ -> a

    def test_separator_gap_evasion(self):
        self.assertTrue(self._hit("m o l l y"))
        self.assertTrue(self._hit("m.o.l.l.y"))
        self.assertTrue(self._hit("m-o-l-l-y"))

    def test_no_match_when_absent(self):
        self.assertFalse(self._hit("just having a coffee"))

    def test_inactive_words_ignored(self):
        BlockedWord.objects.filter(word="molly").update(is_active=False)
        self.assertFalse(self._hit("molly"))

    def test_empty_text(self):
        self.assertEqual(BlockedWord.check_content(""), [])


class ScunthorpeTest(TestCase):
    """Boundary anchoring must not flag innocent substrings."""

    def setUp(self):
        BlockedWord.objects.create(word="ass")

    def test_does_not_match_inner_substring(self):
        self.assertEqual(BlockedWord.check_content("this is a classic case"), [])
        self.assertEqual(BlockedWord.check_content("assassin"), [])

    def test_still_matches_the_actual_word(self):
        self.assertIn("ass", BlockedWord.check_content("don't be an ass"))
        self.assertIn("ass", BlockedWord.check_content("a.s.s"))
