"""Licence guard for the bundled dictionaries (adlar/*.txt): owner rule, data must be CC0, public domain or this
project's own work (MIT); no share-alike or copyleft material. Every file states its licence in its header."""
import glob
import os
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = ("cc0", "public domain", "repository licence", "repo lisansiyla", "licence of this repository")
FORBIDDEN = ("by-sa", "sharealike", "gpl", "odbl", "cc by ")


class DataLicences(unittest.TestCase):
    def test_every_dictionary_header_states_an_allowed_licence(self):
        files = sorted(glob.glob(os.path.join(HERE, "adlar", "*.txt")))
        self.assertTrue(files)
        for path in files:
            with open(path, encoding="utf-8") as fh:
                head = " ".join(ln.lstrip("#").lower().strip() for ln in fh if ln.startswith("#"))
            name = os.path.basename(path)
            self.assertTrue(any(a in head for a in ALLOWED), f"{name}: no allowed licence in the header")
            for bad in FORBIDDEN:
                self.assertNotIn(bad, head, f"{name}: licence marker {bad!r} in the header")

    def test_data_licences_file_lists_every_dictionary(self):
        with open(os.path.join(HERE, "DATA-LICENSES.md"), encoding="utf-8") as fh:
            text = fh.read()
        for path in sorted(glob.glob(os.path.join(HERE, "adlar", "*.txt"))):
            self.assertIn("adlar/" + os.path.basename(path), text)


if __name__ == "__main__":
    unittest.main()
