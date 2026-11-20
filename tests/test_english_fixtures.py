"""English export fixtures (issue #2): every layout the parser reads, run end to end with the default selection
(automatic packs, English labels). All chats are invented: fixtures/en_android_uk24 (Android, day/month, 24 h,
attached and omitted media), fixtures/en_ios_us12 (iOS, month/day, 12 h with seconds), fixtures/en_ios_group (iOS
group with U+202F before AM/PM and system lines in the group's name) and the older fixtures/android_en."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, os.path.dirname(HERE))
import wa2md  # noqa: E402

REAL = ["Harriet", "Plimm", "Zorbek", "Tuvaq", "Quilby", "Odalys", "Fenwick", "Wendell", "Margaret", "John Smith",
        "Acme", "7700 900123", "555 0132", "482913", "Hunter2Plimm"]

# fixture -> (messages, first datetime, senders in order of appearance)
PARSE = {
    "en_android_uk24": (7, "2026-11-14 09:41", ["Harriet Plimm", "Zorbek Tuvaq"]),
    "en_ios_us12": (6, "2026-11-14 09:41", ["Harriet Plimm", "Zorbek Tuvaq"]),
    "en_ios_group": (9, "2026-11-14 09:00", ["Freight Desk", "Harriet Plimm", "Odalys Fenwick", "Zorbek Tuvaq"]),
    "android_en": (4, "2026-11-14 13:45", ["John", "Me"]),
}


def chat_text(name):
    folder = os.path.join(FIX, name)
    txt = [f for f in os.listdir(folder) if f.endswith(".txt")][0]
    with open(os.path.join(folder, txt), "rb") as f:
        return wa2md.decode(f.read())


class Parse(unittest.TestCase):
    def test_layouts(self):
        for name, (n, first, senders) in PARSE.items():
            with self.subTest(fixture=name):
                msgs, unparsed = wa2md.parse(chat_text(name))
                self.assertEqual(len(msgs), n)
                self.assertEqual(unparsed, [])
                self.assertEqual(msgs[0]["dt"].strftime("%Y-%m-%d %H:%M"), first)
                seen = list(dict.fromkeys(m["sender"] for m in msgs if m["sender"]))
                self.assertEqual(seen, senders)

    def test_pm_and_seconds(self):
        msgs, _ = wa2md.parse(chat_text("en_ios_us12"))
        self.assertEqual(msgs[3]["dt"].strftime("%H:%M:%S"), "21:44:59")

    def test_group_system_lines(self):
        msgs, _ = wa2md.parse(chat_text("en_ios_group"))
        self.assertTrue(wa2md.is_group(msgs, "Freight Desk"))
        marked = wa2md.mark_system_lines("Freight Desk", msgs, True)
        system = [m for m in marked if not m["sender"]]
        self.assertGreaterEqual(len(system), 5)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("WA2MD_LANG", "WA2MD_PACKS", "XDG_STATE_HOME")}
        for k in ("WA2MD_LANG", "WA2MD_PACKS"):
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_STATE_HOME"] = os.path.join(self.tmp, "state")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        wa2md.use_pack(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_fixture(self, name):
        out = os.path.join(self.tmp, name)
        o, e = io.StringIO(), io.StringIO()
        with redirect_stdout(o), redirect_stderr(e):
            code = wa2md.main([os.path.join(FIX, name), "--out", out, "--review-dir", os.path.join(self.tmp, "rv")])
        self.assertEqual(code, 0, e.getvalue())
        with open(os.path.join(out, "Chat-1", "Chat-1.md"), encoding="utf-8") as f:
            return f.read(), o.getvalue()

    def test_no_invented_identifier_leaks_and_labels_are_english(self):
        for name in ("en_android_uk24", "en_ios_us12", "en_ios_group"):
            with self.subTest(fixture=name):
                md, console = self.run_fixture(name)
                for bad in REAL:
                    self.assertNotIn(bad, md)
                self.assertIn("- Participants: Person 1", md)
                self.assertNotIn("Kişi", md)
                self.assertNotIn("Sohbet", md)

    def test_ordinary_words_and_places_stay(self):
        md, _ = self.run_fixture("en_android_uk24")
        self.assertIn("please mark it paid, the bill is due in May", md)
        self.assertIn("Mr. Person", md)
        self.assertIn("[company] Logistics Ltd.", md)
        self.assertIn("[phone]", md)
        md, _ = self.run_fixture("en_ios_group")
        self.assertIn("Chicago → Dallas, 40ft flatbed, $1,250", md)
        self.assertIn("portal password: [password]", md)
        md, _ = self.run_fixture("en_ios_us12")
        self.assertIn("'s phone is dead; the rose bushes are fine", md)
        self.assertIn("my verification code is [code]", md)


if __name__ == "__main__":
    unittest.main()
