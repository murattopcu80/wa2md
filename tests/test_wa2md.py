import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, os.path.dirname(HERE))
import wa2md  # noqa: E402

TR = os.path.join(FIX, "android_tr")
EN = os.path.join(FIX, "android_en")
IOS = os.path.join(FIX, "WhatsApp Chat - Mehmet")


_ENV = {}


def setUpModule():
    # these tests assert the Turkish console text: pin the message table to Turkish (English is covered by test_i18n.py)
    _ENV["old_lang"] = os.environ.get("WA2MD_LANG")
    os.environ["WA2MD_LANG"] = "tr"


def tearDownModule():
    if _ENV["old_lang"] is None:
        os.environ.pop("WA2MD_LANG", None)
    else:
        os.environ["WA2MD_LANG"] = _ENV["old_lang"]


def run(*argv):
    o, e = io.StringIO(), io.StringIO()
    with redirect_stdout(o), redirect_stderr(e):
        code = wa2md.main([*argv, "--no-anonim"])  # bu testler gercek adlari dogrular; anonim davranis test_anonim.py'de
    return code, o.getvalue(), e.getvalue()


def make_zip(src_dir, zip_path, extra=None):
    with zipfile.ZipFile(zip_path, "w") as z:
        for n in os.listdir(src_dir):
            z.write(os.path.join(src_dir, n), n)
        for k, v in (extra or {}).items():
            z.writestr(k, v)


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def md(self, chat):
        with open(os.path.join(self.out, chat, chat + ".md"), encoding="utf-8") as f:
            return f.read()

    def test_android_tr(self):
        code, o, _ = run(TR, "--out", self.out)
        self.assertEqual(code, 0)
        md = self.md("Naime")
        self.assertIn("# Naime", md)
        self.assertIn("## 2026-11-14", md)
        self.assertIn("## 2026-11-15", md)
        self.assertIn("**Naime** 13:47", md)
        self.assertIn("Katılımcılar: Naime, Orhan", md)
        self.assertIn("Mesaj sayısı: 7", md)
        self.assertIn("2026-11-14 – 2026-11-15", md)

    def test_multiline(self):
        run(TR, "--out", self.out)
        self.assertIn("Merhaba  \nnasıl gidiyor?", self.md("Naime"))

    def test_system_message(self):
        run(TR, "--out", self.out)
        md = self.md("Naime")
        self.assertIn("_13:46 – Naime grubu oluşturdu_", md)
        self.assertNotIn("**Naime** 13:46", md)

    def test_image_caption(self):
        run(TR, "--out", self.out)
        md = self.md("Naime")
        self.assertIn("![](media/IMG-20261114-WA0001.jpg)  \nBu bir açıklama", md)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "Naime", "media", "IMG-20261114-WA0001.jpg")))

    def test_space_in_name_urlencoded(self):
        run(TR, "--out", self.out)
        self.assertIn("![](media/foto%201.png)", self.md("Naime"))

    def test_non_image(self):
        run(TR, "--out", self.out)
        self.assertIn("[DOC-20261114-WA0002.pdf](media/DOC-20261114-WA0002.pdf)", self.md("Naime"))

    def test_missing_file(self):
        _, o, _ = run(TR, "--out", self.out)
        self.assertIn("_(dosya eksik: IMG-20261114-WA0009.jpg)_", self.md("Naime"))
        self.assertIn("1 medya eksik", o)
        self.assertIn("3 medya kopyalandı", o)

    def test_omitted(self):
        run(TR, "--out", self.out)
        self.assertIn("_(medya dahil edilmemiş)_", self.md("Naime"))

    def test_android_en_ampm(self):
        run(EN, "--out", self.out)
        md = self.md("John Smith")
        self.assertIn("**John** 13:46", md)
        self.assertIn("**Me** 09:05", md)
        self.assertIn("## 2026-11-15", md)  # MM/DD tespit edildi
        self.assertIn("_(medya dahil edilmemiş)_", md)

    def test_ios_tr(self):
        code, o, _ = run(IOS, "--out", self.out)
        md = self.md("Mehmet")
        self.assertIn("![](media/00000012-PHOTO-2026-11-14-13-45-10.jpg)", md)
        self.assertIn("Selam  \nikinci satır  \nüçüncü satır", md)
        self.assertIn("[00000013-AUDIO-2026-11-14-13-47-00.opus](media/", md)
        self.assertIn("_(medya dahil edilmemiş)_", md)
        self.assertIn("2 medya kopyalandı", o)

    def test_invisible_chars_and_bom(self):
        src = os.path.join(self.tmp, "src")
        shutil.copytree(IOS, src)
        p = os.path.join(src, "_chat.txt")
        with open(p, encoding="utf-8") as f:
            t = f.read()
        t = "﻿" + "\n".join("‎" + l.replace("] ", "] ‪", 1) for l in t.split("\n"))
        t = t.replace("<ek:", "‎<ek:")
        with open(p, "w", encoding="utf-8") as f:
            f.write(t)
        run(src, "--out", self.out, "--name", "Mehmet")
        md = self.md("Mehmet")
        self.assertIn("**Mehmet** 13:46", md)
        self.assertIn("![](media/00000012", md)

    def test_zip_input(self):
        z = os.path.join(self.tmp, "WhatsApp Chat with Zed.zip")
        make_zip(TR, z)
        code, o, _ = run(z, "--out", self.out, "--name", "Zed")
        self.assertEqual(code, 0)
        self.assertIn("![](media/IMG-20261114-WA0001.jpg)", self.md("Zed"))
        self.assertTrue(os.path.isfile(os.path.join(self.out, "Zed", "media", "foto 1.png")))

    def test_zip_traversal_safe(self):
        z = os.path.join(self.tmp, "x.zip")
        make_zip(TR, z, {"../evil.jpg": "x", "/abs/evil2.jpg": "x", "sub/dir/ok.jpg": "x"})
        run(z, "--out", self.out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil.jpg")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "Naime", "media", "evil.jpg")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "Naime", "media", "evil2.jpg")))

    def test_directory_of_zips_and_only(self):
        d = os.path.join(self.tmp, "exports")
        os.makedirs(d)
        make_zip(TR, os.path.join(d, "WhatsApp Chat with A.zip"))
        make_zip(IOS, os.path.join(d, "WhatsApp Chat - B.zip"))
        code, o, _ = run(d, "--out", self.out)
        self.assertEqual(sorted(os.listdir(self.out)), ["B", "Naime"])
        shutil.rmtree(self.out)
        run(d, "--out", self.out, "--only", "b, nobody")
        self.assertEqual(os.listdir(self.out), ["B"])
        code, _, e = run(d, "--out", self.out + "2", "--only", "zzz")
        self.assertEqual(code, 1)

    def test_from_to_filters(self):
        run(TR, "--out", self.out, "--from", "2026-11-15")
        md = self.md("Naime")
        self.assertNotIn("## 2026-11-14", md)
        self.assertIn("## 2026-11-15", md)
        self.assertIn("Mesaj sayısı: 1", md)
        shutil.rmtree(self.out)
        run(TR, "--out", self.out, "--to", "2026-11-14")
        self.assertNotIn("## 2026-11-15", self.md("Naime"))

    def test_rerun_skips_identical_media(self):
        run(TR, "--out", self.out)
        _, o, _ = run(TR, "--out", self.out)
        self.assertIn("0 medya kopyalandı", o)

    def test_inputs_untouched(self):
        before = sorted(os.listdir(TR))
        run(TR, "--out", self.out)
        self.assertEqual(before, sorted(os.listdir(TR)))

    def test_errors_turkish(self):
        code, _, e = run(os.path.join(self.tmp, "yok.zip"), "--out", self.out)
        self.assertEqual(code, 2)
        self.assertIn("Girdi bulunamadı", e)
        z = os.path.join(self.tmp, "bos.zip")
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("a.jpg", "x")
        _, _, e = run(z, "--out", self.out)
        self.assertIn("sohbet (.txt) dosyası bulunamadı", e)

    def test_zero_messages_shows_unparsed(self):
        d = os.path.join(self.tmp, "bad")
        os.makedirs(d)
        with open(os.path.join(d, "WhatsApp Chat with Bad.txt"), "w", encoding="utf-8") as f:
            f.write("garip satır 1\ngarip satır 2\ngarip 3\ngarip 4\n")
        code, _, e = run(d, "--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("Hiç mesaj ayrıştırılamadı", e)
        self.assertIn("garip 3", e)
        self.assertNotIn("garip 4", e)

    def test_cli_subprocess(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(HERE), "wa2md.py"),
                            IOS, "--out", self.out], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("mesaj", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
