"""son bagimsiz inceleme: sozluk adi + katilimcinin tam adi, ek basligi sayilan tek sozcuk/parola.
Tum adlar, parolalar ve dosya adlari uydurmadir."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import _pin  # noqa: E402  (Turkish pack set and labels, issue #2)
import wa2md  # noqa: E402
from test_ikinci_inceleme import android_tr, body, md  # noqa: E402

PEOPLE = [("Mert Er", "merhaba"), ("Selin Kaya", "selam"), ("Melis Tarnu", "selam")]


def lines(rows):
    out, a = md(android_tr(PEOPLE + [("Selin Kaya", r) for r in rows]))
    return body(out).split("\n")[-2 * len(rows) + 1::2], a


def setUpModule():
    _pin.pin()


def tearDownModule():
    _pin.unpin()


class DictionaryNameBeforeParticipant(unittest.TestCase):
    """Onceki sozluk adi katilimcinin adiyla eslenmez: katilimcinin tam adi kendi etiketiyle, hicbir parcasi kalmaz."""

    def test_no_part_of_participant_survives(self):
        rows = ["Mimar Mert Er ile görüştük", "Selin Mert Er Lisesi", "Mimar Mert Er Caddesi",
                "Mert Er Selin Kaya geldi", "Mimar Mert Er'in ofisi", "dün Zeynep Mert Er'e söyledi",
                "Zeynep Nur Mert Er geldi"]
        got, a = lines(rows)
        mert, selin = a.labels["Mert Er"], a.labels["Selin Kaya"]
        text = "\n".join(got)
        for bad in ("Mert", "Zeynep"):
            self.assertNotIn(bad, text)
        self.assertNotRegex(text, r"\bEr\b")                               # kisa soyad (< 4 harf) da kalmaz
        self.assertEqual(got[0], f"Mimar {mert} ile görüştük")              # 'Mimar' sozcuk anlamli: kurallara gore
        self.assertEqual(got[1], f"{selin} {mert} Lisesi")                   # yer adinin icindeki katilimci da maskeli
        self.assertEqual(got[2], f"Mimar {mert} Caddesi")
        self.assertEqual(got[3], f"{mert} {selin} geldi")                    # iki katilimci yan yana
        self.assertEqual(got[4], f"Mimar {mert}'in ofisi")                   # ekli bicim
        self.assertRegex(got[5], rf"^dün Kişi \d+ {mert}'e söyledi$")        # onceki ad ayri kisi, birlesmez
        self.assertNotIn(f"Kişi {mert[5:]} {mert}", got[5])
        self.assertRegex(got[6], rf"^Kişi \d+ {mert} geldi$")                # Ad + ikinci ad eslesir, katilimci ayri

    def test_dictionary_pair_with_non_participant_third_part_still_works(self):
        got, _ = lines(["Zeynep Mert Xandor geldi", "Deniz Selin Plimko aradı"])
        for bad in ("Zeynep", "Xandor", "Deniz", "Plimko"):                 # tam ad katilimci degil: eski kural
            self.assertNotIn(bad, "\n".join(got))


class FileNameLineVersusPassword(unittest.TestCase):
    """Ekli olmayan mesajda tek sozcuk/rakamli dosya adi parola kurallarindan gecer; siradan sozcuklu ad baslik kalir."""

    def chat(self, rows):
        out, _ = md(android_tr([("Melis Tarnu", "selam"), ("Zarvo Kentel", "selam")] + rows))
        return body(out)

    def test_secret_shaped_file_names_are_masked(self):
        out = self.chat([("Zarvo Kentel", "şifre Kartal2024.docx"),
                         ("Zarvo Kentel", "wifi şifresi"), ("Zarvo Kentel", "Kartal2024.txt"),
                         ("Zarvo Kentel", "Şifre:\nKartal.zip")])
        self.assertNotIn("Kartal", out)
        self.assertEqual(out.count("[parola]"), 3)

    def test_ordinary_file_names_stay(self):
        out = self.chat([("Zarvo Kentel", "şifre listesi.pdf"), ("Zarvo Kentel", "parola politikası.docx")]
                        + [("Melis Tarnu", "tamam")] * 4 + [("Zarvo Kentel", "rapor.pdf")])
        self.assertIn("şifre listesi.pdf", out)
        self.assertIn("parola politikası.docx", out)
        self.assertIn("rapor.pdf", out)                                      # anahtar kelimeli mesajdan uzak

    def test_attachment_message_keeps_its_title_but_not_a_value(self):
        out = self.chat([("Zarvo Kentel", "DOC-20261114-WA0003.pdf (dosya ekli)\nTeklif_2024 Son.pdf"),
                         ("Zarvo Kentel", "a.zip (dosya ekli)\na.zip"),
                         ("Zarvo Kentel", "b.zip (dosya ekli)\nŞifre:\nKartal.zip"),
                         ("Zarvo Kentel", "c.zip (dosya ekli)\nşifre Kartal2024.docx")])
        self.assertIn("Teklif_2024 Son.pdf", out)                            # belgenin ozgun adi: baslik
        self.assertIn("a.zip", out)
        self.assertNotIn("Kartal", out)

    def test_title_rule(self):
        t = wa2md.is_title_line
        self.assertTrue(t("rapor.pdf", {"rapor.pdf"}))
        self.assertTrue(t("şifre listesi.pdf", set()))
        self.assertFalse(t("şifre Kartal2024.docx", set()))
        self.assertFalse(t("Kartal.zip", set()))
        self.assertTrue(t("Teklif_2024.pdf", {"DOC-1.pdf"}))
        self.assertFalse(t("şifre Kartal2024.docx", {"DOC-1.pdf"}))


if __name__ == "__main__":
    unittest.main()
