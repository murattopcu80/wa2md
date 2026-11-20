"""Besinci inceleme: (1) kisa parcali cok parcali katilimci adinin kismi bicimleri, (2) anahtar kelimeli
mesajin ardindaki ek basligi, (3) WhatsApp medya adi parola sayilmaz. Tum adlar, sohbetler ve dosya adlari uydurmadir."""
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import _pin  # noqa: E402  (Turkish pack set and labels, issue #2)
import wa2md  # noqa: E402

_ENV = {}
TITLE = "Örnek Bisiklet Grubu"
P = "Volkan Eda Su"          # uc parcali katilimci; orta ve son parca kisa (3 ve 2 harf)
R = "Kaan Ece Er"            # ikinci uc parcali katilimci; son parca siradan sozcuk ('er')
Q = "Nehir Tunç"


def setUpModule():
    _pin.pin()
    _ENV["old"] = os.environ.get("XDG_STATE_HOME")
    _ENV["dir"] = tempfile.mkdtemp(prefix="wa2md-state-")
    os.environ["XDG_STATE_HOME"] = _ENV["dir"]


def tearDownModule():
    if _ENV["old"] is None:
        os.environ.pop("XDG_STATE_HOME", None)
    else:
        os.environ["XDG_STATE_HOME"] = _ENV["old"]
    shutil.rmtree(_ENV["dir"], ignore_errors=True)
    _pin.unpin()


def run(rows, people=(P, R, Q)):
    """rows: [(gonderen, metin)] -> (mesaj metni satirlari (baslik/gonderen satirlari haric), Anonymizer)."""
    rows = [(p, "selam") for p in people] + list(rows)
    text = "".join(f"11/14/26, 9:{i:02d} AM - {s}: {t}\n" for i, (s, t) in enumerate(rows))
    msgs, _ = wa2md.parse(wa2md.decode(text.encode("utf-8")))
    group = wa2md.is_group(msgs, TITLE)
    msgs = wa2md.mark_system_lines(TITLE, msgs, group)
    a = wa2md.Anonymizer(TITLE, msgs, 1, None, group=group)
    out, _, _ = wa2md.render(TITLE, msgs, None, anon=a)
    lines = [ln.strip() for ln in out.split("\n")
             if ln.strip() and not ln.startswith(("#", "- ", "**"))]
    return lines[len(people):], a


class ShortPartCombos(unittest.TestCase):
    """Madde 1: katilimci adinin >=2 parcali her sirali secimi o katilimciya gider; kisa parca yalniz ayni adin baska
    parcasinin yaninda maskelenir."""

    def check(self, line, expect):
        out, a = run([(Q, line)])
        self.assertEqual(out[-1], expect.format(p=a.labels[P], r=a.labels[R]))
        return out[-1], a

    def test_middle_plus_last(self):
        self.check("Eda Su geldi", "{p} geldi")

    def test_first_plus_last(self):
        self.check("Volkan Su geldi", "{p} geldi")

    def test_first_plus_middle(self):
        self.check("Volkan Eda geldi", "{p} geldi")

    def test_dictionary_name_before_first_plus_last(self):
        out, a = run([(Q, "Zeynep Volkan Su geldi")])
        m = re.fullmatch(r"(Kişi \d+) (Kişi \d+) geldi", out[-1])
        self.assertTrue(m, out[-1])
        self.assertEqual(m.group(2), a.labels[P])
        self.assertNotIn(m.group(1), a._people)            # sozluk adi baska kisi, katilimci etiketi degil

    def test_suffix_forms(self):
        self.check("Volkan Su'nun kalemi", "{p}'nun kalemi")
        self.check("Eda Su'ya sor", "{p}'ya sor")
        self.check("Kaan Er'e sor", "{r}'e sor")
        self.check("Ece Er geldi", "{r} geldi")

    def test_lowercase_typed(self):
        self.check("volkan su geldi", "{p} geldi")

    def test_short_words_alone_untouched(self):
        rows = ["su içtim", "Su faturası geldi", "er geç gelir", "ok tamam", "ay sonu geldi", "Su geldi", "Er geldi"]
        out, _ = run([(Q, r) for r in rows])
        self.assertEqual(out[-len(rows):], rows)

    def test_lone_short_part_unchanged(self):
        """Tek basina kisa orta parca (3 harf) katilimci anahtari olmaz (soyad adayi >=4 harf): onceki davranis."""
        out, _ = run([(Q, "Ece bugün yok")])
        self.assertEqual(out[-1], "Ece bugün yok")

    def test_shared_combo_is_neutral(self):
        out, a = run([(Q, "Eda Su geldi")], people=(P, "Ozan Eda Su", Q))
        self.assertEqual(out[-1], "Kişi ? geldi")

    def test_full_name_of_other_participant_wins(self):
        out, a = run([(Q, "Eda Su geldi")], people=(P, "Eda Su", Q))
        self.assertEqual(out[-1], f"{a.labels['Eda Su']} geldi")


class CaptionAfterKeyword(unittest.TestCase):
    """Madde 2: anahtar kelimeli komsu mesajin ardindaki ek basligi parola kurallarina girer (ekin kendi adi degilse)."""

    def test_caption_masked(self):
        out, _ = run([(Q, "şifre"), (Q, "R2.pdf (file attached)\nZorlu61.pdf")])
        self.assertEqual(out[-2:], ["_(dosya eksik: R2.pdf)_", "[parola]"])

    def test_caption_value_masked_again_later(self):
        out, _ = run([(Q, "şifre"), (Q, "R2.pdf (file attached)\nZorlu61.pdf"), (Q, "Zorlu61.pdf oldu mu")])
        self.assertEqual(out[-1], "[parola] oldu mu")

    def test_own_file_name_kept(self):
        out, _ = run([(Q, "şifre"), (Q, "R2.pdf (file attached)\nR2.pdf")])
        self.assertEqual(out[-1], "R2.pdf")

    def test_no_keyword_caption_kept(self):
        out, _ = run([(Q, "R2.pdf (file attached)\nTeklif2024.pdf")])
        self.assertEqual(out[-1], "Teklif2024.pdf")

    def test_plain_word_caption_kept(self):
        out, _ = run([(Q, "şifre"), (Q, "R2.pdf (file attached)\nfatura.pdf")])
        self.assertEqual(out[-1], "fatura.pdf")


class WhatsAppMediaName(unittest.TestCase):
    """Madde 3: WhatsApp'in kendi medya adi (IMG-/VID-/PTT-/DOC-/STK-/AUD-YYYYMMDD-WAnnnn) parola sayilmaz."""
    NAMES = ["IMG-20240101-WA0001.jpg", "VID-20240101-WA0002.mp4", "PTT-20240101-WA0003.opus",
             "DOC-20240101-WA0004.pdf", "STK-20240101-WA0005.webp", "AUD-20240101-WA0006.opus", "IMG-20240101-WA0007"]

    def test_after_keyword_message(self):
        for nm in self.NAMES:
            for kw in ("şifre", "şifre:"):
                with self.subTest(nm=nm, kw=kw):
                    out, _ = run([(Q, kw), (Q, nm)])
                    self.assertEqual(out[-1], nm)

    def test_same_line_value(self):
        out, _ = run([(Q, "şifre: IMG-20240101-WA0001.jpg")])
        self.assertEqual(out[-1], "şifre: IMG-20240101-WA0001.jpg")

    def test_real_secrets_still_masked(self):
        for val in ("Kartal.2024", "IMG-2024-Kartal99.jpg", "Zorlu61"):
            with self.subTest(val=val):
                out, _ = run([(Q, "şifre"), (Q, val)])
                self.assertEqual(out[-1], "[parola]")

    def test_pattern_unit(self):
        for nm in self.NAMES:
            self.assertFalse(wa2md._cred_like(nm, 6), nm)
            self.assertFalse(wa2md._next_line_value(nm) and wa2md._cred_like(nm), nm)
        self.assertTrue(wa2md._cred_like("IMG-2024-Kartal99.jpg", 6))
        self.assertTrue(re.fullmatch(wa2md._WA_MEDIA, "PTT-20261114-WA0123.opus"))


if __name__ == "__main__":
    unittest.main()
