"""Optional 'phonenumbers' validation of phone candidates (issue #2).

Without the package every candidate of the phone pattern is masked. With it, a '+<country> ...' / '00 <country> ...'
candidate whose country code is unknown or whose length is impossible stays text; national shapes of the packs are
masked whatever the package says (the reserved example ranges used here are not 'valid' numbers, only possible ones).
The tests that need the package are skipped when it is not installed (CI installs no optional packages).
All numbers are invented or from reserved example ranges.
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import wa2md  # noqa: E402
import test_decision_table_en as T  # noqa: E402

try:
    import phonenumbers  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False

ALWAYS = [                          # masked with and without the package
    ("call 07700 900123", "call [phone]"),
    ("ring 202-555-0147", "ring [phone]"),
    ("+44 7700 900123 today", "[phone] today"),
    ("+1 202 555 0147 ext. 12", "[phone]"),
    ("00 44 7700 900123", "[phone]"),
]
IMPOSSIBLE = [                      # masked without the package, text with it
    "call +999 123 456 789",
    "call +1 202 555 01",
]


def out(line):
    lines, _ = T.run([(T.H, line)])
    return "\n".join(lines)


class WithoutPackage(unittest.TestCase):
    def test_every_candidate_is_masked(self):
        with mock.patch.object(wa2md, "_phonenumbers", None):
            for line, exp in ALWAYS:
                self.assertEqual(out(line), exp)
            for line in IMPOSSIBLE:
                self.assertEqual(out(line), "call [phone]", line)


@unittest.skipUnless(HAVE, "optional package 'phonenumbers' not installed")
class WithPackage(unittest.TestCase):
    def test_package_is_used(self):
        self.assertIsNotNone(wa2md._phonenumbers)

    def test_national_and_possible_numbers_are_masked(self):
        for line, exp in ALWAYS:
            self.assertEqual(out(line), exp)

    def test_impossible_international_numbers_stay(self):
        for line in IMPOSSIBLE:
            self.assertEqual(out(line), line)


if __name__ == "__main__":
    unittest.main()
