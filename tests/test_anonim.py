"""Anonimlestirme (varsayilan acik) testleri. Tum adlar/numaralar uydurmadir."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import _pin  # noqa: E402  (Turkish pack set and labels, issue #2)
import wa2md  # noqa: E402
import wa_web  # noqa: E402


_ENV = {}


def setUpModule():
    """Inceleme dosyasi varsayilan olarak kullanici durum klasorune gider: testlerde gecici klasor."""
    _pin.pin()
    # these tests assert the Turkish console text: pin the message table to Turkish (English is covered by test_i18n.py)
    _ENV["old_lang"] = os.environ.get("WA2MD_LANG")
    os.environ["WA2MD_LANG"] = "tr"
    _ENV["old"] = os.environ.get("XDG_STATE_HOME")
    _ENV["dir"] = tempfile.mkdtemp(prefix="wa2md-state-")
    os.environ["XDG_STATE_HOME"] = _ENV["dir"]


def tearDownModule():
    if _ENV["old_lang"] is None:
        os.environ.pop("WA2MD_LANG", None)
    else:
        os.environ["WA2MD_LANG"] = _ENV["old_lang"]
    if _ENV["old"] is None:
        os.environ.pop("XDG_STATE_HOME", None)
    else:
        os.environ["XDG_STATE_HOME"] = _ENV["old"]
    shutil.rmtree(_ENV["dir"], ignore_errors=True)
    _pin.unpin()

REAL = ["Zeynep Kaya", "Orhan", "Fatma", "Mavi Ekip", "zeynep@ornek.test", "5000001234", "500 000 12 34",
        "ORHAN", "Orhan Demir"]

CHAT_A = """14.11.2026 10:00 - Zeynep Kaya: Merhaba ben Zeynep Kaya, bu da ORHAN
14.11.2026 10:01 - Orhan: @Orhan yazdı, ben orhan'ım; ıSIRGAN değil
14.11.2026 10:02 - Fatma: Mail: zeynep@ornek.test tel 0500 000 12 34 veya +90 (500) 000 12 34
14.11.2026 10:03 - Zeynep Kaya: Alt satırlar 05.12.2026 saat 10:30 fiyat 1.250,50 TL ve 1.234.567 plaka 34 ABC 123
14.11.2026 10:04 - Mavi Ekip grubu hakkında Fatma geldi
14.11.2026 10:05 - Fatma: https://wa.me/905000001234 ve +44 7700 900123
14.11.2026 10:06 - Orhan: Zeynep_Kaya_foto.jpg (dosya ekli)
"""


def make_export(root, name, text, files=None):
    d = os.path.join(root, name)
    os.makedirs(d)
    with open(os.path.join(d, "WhatsApp Chat with " + name + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)
    for fn, data in (files or {}).items():
        with open(os.path.join(d, fn), "wb") as f:
            f.write(data)
    return d


def run(*argv):
    o, e = io.StringIO(), io.StringIO()
    with redirect_stdout(o), redirect_stderr(e):
        code = wa2md.main(list(argv))
    return code, o.getvalue(), e.getvalue()


class Anonim(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src")
        os.makedirs(self.src)
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def md(self, label="Sohbet-1", out=None):
        with open(os.path.join(out or self.out, label, label + ".md"), encoding="utf-8") as f:
            return f.read()

    def chat_a(self, **kw):
        return make_export(self.src, "Mavi Ekip", CHAT_A, kw.get("files"))

    def test_default_on_both_clis(self):
        self.assertTrue(wa2md.argparse.ArgumentParser)  # noqa
        src = self.chat_a()
        run(src, "--out", self.out)
        self.assertIn("# Sohbet-1", self.md())
        for sub in ("import", "export"):
            a = wa_web.build_parser().parse_args([sub, "x", "--out", "o"] if sub == "import"
                                                 else [sub, "--chats", "x", "--out", "o"])
            self.assertTrue(a.anonim, sub)
            a = wa_web.build_parser().parse_args(([sub, "x"] if sub == "import" else [sub, "--chats", "x"])
                                                 + ["--out", "o", "--no-anonim"])
            self.assertFalse(a.anonim)

    def test_numbering_header_text(self):
        run(self.chat_a(), "--out", self.out)
        md = self.md()
        self.assertIn("Katılımcılar: Kişi 1, Kişi 2, Kişi 3", md)
        self.assertIn("**Kişi 1** 10:00", md)
        self.assertIn("**Kişi 2** 10:01", md)
        self.assertIn("Merhaba ben Kişi 1, bu da Kişi 2", md)          # tam ad + büyük harf
        self.assertIn("Kişi 2 yazdı, ben Kişi 2'ım", md)               # @mention + küçük harf
        self.assertIn("ıSIRGAN değil", md)                              # kelime sınırı
        self.assertIn("Mail: [e-posta] tel [telefon] veya [telefon]", md)
        self.assertIn("Sohbet-1 grubu hakkında Kişi 3 geldi", md)       # grup adı + sistem satırı

    def test_dates_prices_untouched_and_phone_in_link(self):
        run(self.chat_a(), "--out", self.out)
        md = self.md()
        for keep in ("05.12.2026", "10:30", "1.250,50 TL", "1.234.567"):
            self.assertIn(keep, md)
        self.assertIn("https://wa.me/[telefon] ve [telefon]", md)

    def test_suffixes_and_first_names(self):
        a = wa2md.Anonymizer("x", [{"sender": "Naime Tan"}, {"sender": "Burak Er"}, {"sender": "Burak Aslan"}], 1)
        self.assertEqual(a.text("Naime'ye, Naime’nin, NAİME'DEN ve naime tan'a"),
                         "Kişi 1'ye, Kişi 1’nin, Kişi 1'DEN ve Kişi 1'a")
        self.assertEqual(a.text("Burak geldi"), "Kişi ? geldi")          # belirsiz ilk ad: notr etiket (ad okunmaz)
        self.assertEqual(a.text("Burak Er geldi"), "Kişi 2 geldi")

    def test_iban_tckn_plate_and_negatives(self):
        a = wa2md.Anonymizer("x", [{"sender": "Ali"}], 1)
        self.assertEqual(a.text("TR33 0006 1005 1978 6457 8413 26 ve TR330006100519786457841326"), "[iban] ve [iban]")
        self.assertEqual(a.text("kimlik 10000000146 no"), "kimlik [tckn] no")
        self.assertEqual(a.text("34 ABC 123, 06AB1234 ve 81 Z 99"), "[plaka], [plaka] ve [plaka]")
        for keep in ("550+KDV", "10 teker", "14.11.2026", "13:45", "25 ton", "10 TL 50", "12 kg 3", "2026 yılı",
                     "1.234.567,89", "100000 adet"):
            self.assertEqual(a.text(keep), keep, keep)

    def test_no_media_flag(self):
        src = self.chat_a(files={"Zeynep_Kaya_foto.jpg": b"jpgdata"})
        run(src, "--out", self.out, "--medya-yok")
        self.assertFalse(os.path.exists(os.path.join(self.out, "Sohbet-1", "media")))
        self.assertIn("_(medya dahil edilmemiş)_", self.md())
        for sub in ("import", "export"):
            a = wa_web.build_parser().parse_args(([sub, "x"] if sub == "import" else [sub, "--chats", "x"])
                                                 + ["--out", "o", "--medya-yok"])
            self.assertTrue(a.no_media)

    def test_turkish_casing(self):
        a = wa2md.Anonymizer("x", [{"sender": "İpek Işık"}], 1)
        self.assertEqual(a.text("ipek ışık ve İPEK IŞIK, İpek Işık"), "Kişi 1 ve Kişi 1, Kişi 1")

    def test_one_to_one_chat_name_maps_to_person(self):
        a = wa2md.Anonymizer("Orhan", [{"sender": "Ben"}, {"sender": "Orhan"}], 1)
        self.assertEqual(a.text("Orhan geldi"), "Kişi 2 geldi")

    def test_quote_and_system_row(self):
        msgs = [{"dt": __import__("datetime").datetime(2026, 11, 14, 10, 0), "sender": "Orhan Demir",
                 "parts": [("quote", "Fatma Hanım\nselam"), ("text", "tamam")]},
                {"dt": __import__("datetime").datetime(2026, 11, 14, 10, 1), "sender": "Fatma Hanım", "parts": [("text", "x")]},
                {"dt": __import__("datetime").datetime(2026, 11, 14, 10, 2), "sender": None,
                 "parts": [("text", "Orhan Demir, Fatma Hanım'ı ekledi")]}]
        export = wa2md.Export("web", "", b"", {})
        path, _, _, _ = self._write("Grup A", msgs, export)
        with open(path, encoding="utf-8") as f:
            md = f.read()
        self.assertIn("> Kişi 2\n> selam", md)
        self.assertIn("Kişi 1, Kişi 2'ı ekledi", md)
        self.assertNotIn("Orhan", md)
        self.assertNotIn("Fatma", md)

    def _write(self, chat, msgs, export, **kw):
        with redirect_stdout(io.StringIO()):
            return wa2md.write_chat(chat, msgs, export, self.out, anonim=True, **kw)

    def test_no_real_data_on_disk_and_no_mapping(self):
        src = self.chat_a(files={"Zeynep_Kaya_foto.jpg": b"jpgdata", "IMG-1.jpg": b"x"})
        code, o, e = run(src, "--out", self.out)
        self.assertEqual(code, 0)
        n = 0
        for root, dirs, files in os.walk(self.out):
            for name in dirs + files:
                for bad in REAL:
                    self.assertNotIn(bad.lower(), name.lower())
            for name in files:
                if name.endswith(".md"):
                    n += 1
                    with open(os.path.join(root, name), encoding="utf-8") as f:
                        txt = f.read()
                    for bad in REAL:
                        self.assertNotIn(bad.lower(), txt.lower(), bad)
        self.assertEqual(n, 2)          # Sohbet-1.md + ekler.md (ek listesi; anonim adlar)
        self.assertFalse([f for f in os.listdir(self.out) if f.endswith(".json")])
        self.assertEqual(os.listdir(self.out), ["Sohbet-1"])
        self.assertTrue(os.path.isfile(os.path.join(self.out, "Sohbet-1", "media", "medya-1.jpg")))
        self.assertIn("medya-1.jpg", self.md())
        # konsolda gerçek ad / eşleme yok
        for bad in REAL:
            self.assertNotIn(bad.lower(), (o + e).lower(), bad)
        self.assertNotIn(" = ", o)
        # ne çıktıda ne geçici/üst klasörde eşleme yapısı (json) yazılmadı
        for root, _, files in os.walk(self.tmp):
            self.assertFalse([f for f in files if f.endswith(".json")], root)
        self.assertIn("doğrudan tanımlayıcıların kaldırılması", o)
        self.assertIn("anonim SAYILMAZ", o)

    def test_positional_labels_and_rerun_overwrites(self):
        make_export(self.src, "Birinci", "14.11.2026 10:00 - Ali Veli: merhaba\n")
        make_export(self.src, "Ikinci", "14.11.2026 10:00 - Can Er: selam\n")
        run(self.src, "--out", self.out)
        self.assertEqual(sorted(os.listdir(self.out)), ["Sohbet-1", "Sohbet-2"])
        self.assertIn("**Kişi 1**", self.md("Sohbet-2"))
        first = self.md("Sohbet-1")
        run(self.src, "--out", self.out)
        self.assertEqual(sorted(os.listdir(self.out)), ["Sohbet-1", "Sohbet-2"])
        self.assertEqual(self.md("Sohbet-1"), first)

    def test_name_override(self):
        run(self.chat_a(), "--out", self.out, "--name", "Proje-X")
        self.assertIn("# Proje-X", self.md("Proje-X"))

    def test_no_anonim_unchanged(self):
        src = self.chat_a()
        run(src, "--out", self.out, "--no-anonim")
        md = self.md("Mavi Ekip")
        self.assertIn("# Mavi Ekip", md)
        self.assertIn("Katılımcılar: Zeynep Kaya, Orhan, Fatma", md)
        self.assertIn("zeynep@ornek.test", md)
        self.assertEqual(os.listdir(self.out), ["Mavi Ekip"])

    def test_web_import_anonim(self):
        part = {"format": "wa-web-bundle", "version": 1, "session": "s1", "part": 1, "chat": "Ayla Yıldız",
                "final": True, "media": [], "total": 1, "today": "2026-11-16", "opts": {},
                "rows": [{"id": "true_1@c.us_AAAAAAAA", "stamp": "[10:00, 14.11.2026] Ayla Yıldız: ",
                          "text": "ben Ayla Yıldız, tel +90 500 000 12 34"}]}
        with open(os.path.join(self.tmp, "wa-bundle-x-s1-001.json"), "w", encoding="utf-8") as f:
            json.dump(part, f)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            wa_web.import_bundles([self.tmp], self.out, anonim=True)
        md = self.md()
        self.assertIn("ben Kişi 1, tel [telefon]", md)
        self.assertNotIn("Ayla", md)


SECRETS = ["Selin Aydın", "Selin", "Aydın", "Kerem", "Tuna Bey", "5000009876", "0500 000 98 76", "selin@ornek.test",
           "gizli-proje", "Gizli Toplantı", "wa-bundle-selin", "Selin_Aydin"]


FORMS_CHAT = """14.11.2026 10:00 - Güçlü Taşvelen: selam
14.11.2026 10:01 - Ali Kaya: selam
14.11.2026 10:02 - Ali Kaya: Halil geldi, kayak yaptık, maliyet düştü
"""


class NameForms(unittest.TestCase):
    """Bitisik / ASCII-katlanmis / kullanici adi icindeki ad bicimleri (adlar uydurmadir)."""

    def setUp(self):
        msgs, _ = wa2md.parse(FORMS_CHAT)
        self.a = wa2md.Anonymizer("Grup Sohbeti", msgs)   # Kişi 1 = Güçlü Taşvelen, Kişi 2 = Ali Kaya

    def t(self, s):
        return self.a.text(s)

    def test_ascii_folded_and_cased(self):
        self.assertEqual(self.t("Guclu Tasvelen geldi"), "Kişi 1 geldi")
        self.assertEqual(self.t("GUCLU TASVELEN ve güçlü taşvelen"), "Kişi 1 ve Kişi 1")
        self.assertEqual(self.t("@guclu yazdı"), "Kişi 1 yazdı")
        self.assertEqual(self.t("Guclu'nun"), "Kişi 1'nun")
        self.assertEqual(self.t("Tasvelen'na"), "Kişi 1'na")

    def test_concatenated_separated_reversed(self):
        for form in ("GucluTasvelen", "guclutasvelen", "guclu.tasvelen", "guclu_tasvelen", "guclu-tasvelen",
                     "GüçlüTaşvelen", "TasvelenGuclu", "tasvelen.guclu", "GUCLUTASVELEN"):
            with self.subTest(form=form):
                out = self.t(f"bak {form} dedi")
                self.assertEqual(out, "bak Kişi 1 dedi")
        self.assertEqual(self.t("(AliKaya) ve KayaAli"), "(Kişi 2) ve Kişi 2")

    def test_inside_tokens_urls_handles(self):
        self.assertEqual(self.t("https://github.com/GucluTasvelen/proje/pull/3"),
                         "https://github.com/Kişi-1/proje/pull/3")
        self.assertEqual(self.t("bkz GucluTasvelen/repo#11"), "bkz Kişi-1/repo#11")
        self.assertEqual(self.t("bkz user/repo#12 ve @aliKaya"), "bkz user/repo#12 ve @Kişi-2")
        self.assertEqual(self.t("mail guclu.tasvelen99 x"), "mail Kişi-199 x")
        self.assertEqual(self.t("[x](https://ornek.test/ali_kaya)"), "[x](https://ornek.test/Kişi-2)")
        self.assertEqual(self.t("guclu.tasvelen@ornek.test"), "[e-posta]")
        self.assertEqual(self.t("Guclu_Tasvelen_foto.jpg"), "Kişi-1_foto.jpg")

    def test_surname_alone(self):
        self.assertEqual(self.t("Tasvelen geldi, taşvelen'nun"), "Kişi 1 geldi, Kişi 1'nun")
        self.assertEqual(self.t("Kaya dedi"), "Kişi 2 dedi")
        # ad tek basina (Guclu) benzersiz oldugundan zaten maskelenir; kisa soyad (<4) yok
        msgs, _ = wa2md.parse("14.11.2026 10:00 - Ece Su: a\n14.11.2026 10:01 - Can Er: b\n")
        a = wa2md.Anonymizer("x", msgs)
        self.assertEqual(a.text("su ve er"), "su ve er")
        self.assertEqual(a.text("Ece geldi"), "Kişi 1 geldi")

    def test_three_part_name_subsequences(self):
        msgs, _ = wa2md.parse("14.11.2026 10:00 - Güçlü Taşvelen Asp: a\n14.11.2026 10:01 - Ali Kaya: b\n")
        a = wa2md.Anonymizer("x", msgs)
        for form in ("GucluTasvelen", "tasvelen_asp", "TasvelenAsp", "AspTasvelen", "guclu.tasvelen", "GucluTasvelenAsp",
                     "gucluasp", "GüçlüTaşvelen"):
            with self.subTest(form=form):
                self.assertEqual(a.text(f"https://g.test/{form}/repo#11"), "https://g.test/Kişi-1/repo#11")
        self.assertEqual(a.text("Güçlü Taşvelen geldi"), "Kişi 1 geldi")
        self.assertEqual(a.text("tasvelen asp ve Asp Taşvelen"), "Kişi 1 ve Kişi 1")
        self.assertEqual(a.text("Asp geldi"), "Asp geldi")     # tek ara parca etiket: maskelenmez (soyad degil, 3 harf)

    def test_suffix_whitelist_without_apostrophe(self):
        for w, exp in (("güçlücüm", "Kişi 1'cüm"), ("guclucum", "Kişi 1'cum"), ("GÜÇLÜCÜĞÜM", "Kişi 1'CÜĞÜM"),
                       ("gucluya", "Kişi 1'ya"), ("guclunun", "Kişi 1'nun"), ("guclucigima", "Kişi 1'cigima"),
                       ("Gucludan", "Kişi 1'dan"), ("Kayaya", "Kişi 2'ya"), ("kayalar", "Kişi 2'lar"),
                       ("@guclucuk", "Kişi 1'cuk")):
            with self.subTest(w=w):
                self.assertEqual(self.t(f"selam {w}!"), f"selam {exp}!")

    def test_suffix_negatives_and_collisions(self):
        for w in ("Gucluluk", "kayalik", "kayakçı", "Guclusuz", "Tasvelensu"):
            with self.subTest(w=w):
                self.assertEqual(self.t(w), w)
        # kisa ad (<4 harf) ek almaz
        msgs, _ = wa2md.parse("14.11.2026 10:00 - Ece Su: a\n14.11.2026 10:01 - Can Er: b\n")
        a = wa2md.Anonymizer("x", msgs)
        out = a.text("Ecem ve suya")      # 'Ecem' Ece'nin eki degil; sozlukte ayri ad (Kişi 1 olmaz)
        self.assertTrue(out.endswith(" ve suya") and "Kişi 1" not in out and "Ecem" not in out, out)
        # kacinilmaz carpisma: ad+ek yaygin bir sozcuge esitse maskelenir (Dilek -> dilekler, Kara -> karaca)
        msgs, _ = wa2md.parse("14.11.2026 10:00 - Dilek Yilmaz: a\n")
        self.assertEqual(wa2md.Anonymizer("x", msgs).text("dilekler tutuldu"), "Kişi 1'ler tutuldu")

    def test_one_word_participant_sharing_first_name(self):
        msgs, _ = wa2md.parse("14.11.2026 10:00 - Güçlü: a\n14.11.2026 10:01 - Güçlü Taşvelen Asp: b\n")
        a = wa2md.Anonymizer("x", msgs)       # Kişi 1 = tek sozcuklu "Güçlü", Kişi 2 = coklu parca
        for w in ("Güçlü", "guclu", "GÜÇLÜ", "Guclu"):
            self.assertEqual(a.text(f"selam {w}!"), "selam Kişi 1!")
        for w, sx in (("güçlü", "cüm"), ("guclu", "cum"), ("Güçlü", "cüğüm"), ("GUCLU", "yu"), ("guclu", "nun")):
            with self.subTest(w=w, sx=sx):
                self.assertEqual(a.text(f"ah {w}{sx}, {w}'{sx}"), f"ah Kişi 1'{sx}, Kişi 1'{sx}")
        self.assertEqual(a.text("Güçlü Taşvelen"), "Kişi 2")

    def test_ambiguous_without_one_word_participant_uses_neutral_label(self):
        msgs, _ = wa2md.parse("14.11.2026 10:00 - Selim Kaya: a\n14.11.2026 10:01 - Selim Demir: b\n")
        a = wa2md.Anonymizer("x", msgs)
        self.assertEqual(a.text("Selim geldi, selim'e, Selime, SELIMCIGIM"), "Kişi ? geldi, Kişi ?'e, Kişi ?'e, Kişi ?'CIGIM")
        self.assertEqual(a.text("Selim Kaya"), "Kişi 1")
        self.assertEqual(a.text("Kaya geldi"), "Kişi 1 geldi")

    def test_middle_name_parts_are_surname_candidates(self):
        msgs, _ = wa2md.parse("14.11.2026 10:00 - Güçlü Taşvelen Asp: a\n14.11.2026 10:01 - Ece Demir Yan: b\n")
        a = wa2md.Anonymizer("Nakliye Ekibi", msgs, group=True)
        self.assertEqual(a.text("Taşvelen geldi, tasvelen'na, TASVELENNUN, Tasvelencum"),
                         "Kişi 1 geldi, Kişi 1'na, Kişi 1'NUN, Kişi 1'cum")
        self.assertEqual(a.text("Demir ve demire"), "Kişi 2 ve Kişi 2'e")
        self.assertEqual(a.text("Asp Yan ve asp"), "Asp Yan ve asp")      # <4 harfli parcalar tek basina maskelenmez
        self.assertEqual(a.text("Nakliye Ekibi nakliye ekibi", title=True), "Sohbet-1 Sohbet-1")   # grup adi tam ad
        # kurum/genel ifade olan grup adi metinde dokunulmaz (sohbet etiketiyle degistirilmez)
        self.assertEqual(a.text("Nakliye Ekibi nakliye ekibi"), "Nakliye Ekibi nakliye ekibi")
        self.assertEqual(a.text("ekibin nakliyesi"), "ekibin nakliyesi")
        # bire bir sohbette baslik karsidaki kisinin adidir: metinde de maskelenir (hic yazmamis olsa da)
        b = wa2md.Anonymizer("Velo Tarsk", msgs[:1], group=False)
        self.assertEqual(b.text("Velo Tarsk yarın gelir, Tarsk'a da söyle"), "Kişi 2 yarın gelir, Kişi 2'a da söyle")

    def test_shared_middle_part_is_neutral(self):
        msgs, _ = wa2md.parse("14.11.2026 10:00 - Ali Yilmaz Kaya: a\n14.11.2026 10:01 - Ece Kaya: b\n")
        a = wa2md.Anonymizer("x", msgs)
        self.assertEqual(a.text("Yilmaz geldi"), "Kişi 1 geldi")
        self.assertEqual(a.text("Kaya geldi, kayaya"), "Kişi ? geldi, Kişi ?'ya")

    def test_negatives_no_substring_for_single_parts(self):
        s = "kayak maliyet kayalık Guclulla"
        self.assertEqual(self.t(s), s)
        # Halil / Alihan katilimci degil; ad sozlugunden ayri kisi olarak maskelenir (katilimci etiketi almaz)
        out = self.t("Halil kayak Alihan")
        self.assertNotIn("Halil", out)
        self.assertNotIn("Kişi 1", out)
        self.assertNotIn("Kişi 2", out)
        self.assertEqual(self.t("balıkçı tuna"), "balıkçı tuna")

    def test_ambiguous_surname_not_masked(self):
        msgs, _ = wa2md.parse("14.11.2026 10:00 - Ece Yildiz: a\n14.11.2026 10:01 - Can Yildiz: b\n")
        a = wa2md.Anonymizer("x", msgs)
        self.assertEqual(a.text("Yildiz geldi"), "Kişi ? geldi")
        self.assertEqual(a.text("EceYildiz"), "Kişi 1")

    def test_chat_name_same_treatment(self):
        msgs, _ = wa2md.parse(FORMS_CHAT)
        a = wa2md.Anonymizer("Mavi Ekip", msgs, chat_no=3, group=True)
        # sohbet adi yalniz sohbeti tanimlayan yerde (sistem satiri, dosya adi: title=True) maskelenir
        self.assertEqual(a.text("MaviEkip ve mavi_ekip ve Mavi Ekip, github.com/EkipMavi", title=True),
                         "Sohbet-3 ve Sohbet-3 ve Sohbet-3, github.com/Sohbet-3")
        self.assertEqual(a.text("Mavi Ekip ile mavi ekip"), "Mavi Ekip ile mavi ekip")    # kurum adi: metinde degil
        # kisi adli grup basligi metinde de maskelenir (Ailesi, sozluk adi ya da katilimci ad parcasi)
        p = wa2md.Anonymizer("Taşvelen Ailesi", msgs, chat_no=3, group=True)
        self.assertEqual(p.text("Taşvelen Ailesi toplantısı"), "Sohbet-3 toplantısı")
        p = wa2md.Anonymizer("Halil ve Arkadaşları", msgs, chat_no=3, group=True)
        self.assertEqual(p.text("Halil ve Arkadaşları yarın"), "Sohbet-3 yarın")

    def test_media_name_uses_matcher(self):
        self.assertEqual(self.a.media_name("guclu-tasvelen.jpg"), "medya-1.jpg")
        self.assertEqual(self.a.media_name("IMG-0001.jpg"), "IMG-0001.jpg")

    def test_regression_output_has_no_name_forms(self):
        tmp = tempfile.mkdtemp()
        try:
            text = FORMS_CHAT + (
                "14.11.2026 10:03 - Ali Kaya: github.com/GucluTasvelen/repo#11 ve guclu.tasvelen ve TasvelenGuclu\n"
                "14.11.2026 10:04 - Güçlü Taşvelen: guclu_tasvelen_foto.jpg (dosya ekli) AliKaya ali-kaya\n")
            src = make_export(os.path.join(tmp, "s") if os.makedirs(os.path.join(tmp, "s")) is None else "", "Mavi Ekip",
                              text, {"guclu_tasvelen_foto.jpg": b"x"})
            out = os.path.join(tmp, "out")
            code, o, e = run(src, "--out", out)
            blob = o + e
            for dp, _, fs in os.walk(out):
                blob += dp + "\n" + " ".join(fs) + "\n"
                for f in fs:
                    if f.endswith(".md"):
                        with open(os.path.join(dp, f), encoding="utf-8") as fh:
                            blob += fh.read()
            low = wa2md._key(blob)
            for bad in ("guclutasvelen", "tasvelenguclu", "guclu.tasvelen", "guclu_tasvelen", "guclu-tasvelen",
                        "guclu tasvelen", "alikaya", "ali-kaya", "kayaali", "tasvelen"):
                self.assertNotIn(bad, low)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


SURNAME_WORDS_CHAT = """14.11.2026 10:00 - Velko Darsun: Açık Bey merhaba
14.11.2026 10:01 - Brin Tamsel: dükkan açık mı
14.11.2026 10:02 - Velko Darsun: kapı açık kalmış
14.11.2026 10:03 - Brin Tamsel: Beyaz Hanım aradı, beyaz araba mı
14.11.2026 10:04 - Velko Darsun: Kısa Hanım aradı, kısa bir not
14.11.2026 10:05 - Brin Tamsel: Mehmet Bey geldi, mehmet nerede
14.11.2026 10:06 - Velko Darsun: Açık olan pencereyi kapat. Sayın Ayşe Açık, Ayşe Açık'a sor
"""


class SurnameWords(unittest.TestCase):
    """Issue #22: a surname that is also an everyday word (Açık, Beyaz, Kısa; adlar/sozcuk-adlar.txt) is masked only
    where the context marks it as a name (honorific, full name); the ordinary word stays (invented chat)."""

    def setUp(self):
        msgs, _ = wa2md.parse(SURNAME_WORDS_CHAT)
        self.a = wa2md.Anonymizer("Velko Darsun", msgs)   # Kişi 1 = Velko Darsun, Kişi 2 = Brin Tamsel
        self.out = [self.a.text(" ".join(v for k, v in wa2md.message_parts(m) if k == "text")) for m in msgs]

    def test_ordinary_word_stays_after_an_honorific(self):
        self.assertEqual(self.out[0], "Kişi 3 Bey merhaba")
        self.assertEqual(self.out[1], "dükkan açık mı")
        self.assertEqual(self.out[2], "kapı açık kalmış")
        self.assertEqual(self.out[3], "Kişi 4 Hanım aradı, beyaz araba mı")
        self.assertEqual(self.out[4], "Kişi 5 Hanım aradı, kısa bir not")

    def test_given_name_still_spreads_in_lower_case(self):
        self.assertEqual(self.out[5], "Kişi 6 Bey geldi, Kişi 6 nerede")

    def test_sentence_start_stays_and_full_name_is_masked(self):
        self.assertEqual(self.out[6], "Açık olan pencereyi kapat. Sayın Kişi 7, Kişi 7'a sor")


class Credentials(unittest.TestCase):
    """Parola / gizli anahtar maskeleme (sezgisel). Tum degerler uydurmadir."""

    def anon(self, chat, who="Ali Veli"):
        msgs, _ = wa2md.parse(chat)
        return wa2md.Anonymizer("Grup Alfa", msgs), msgs

    def render(self, chat):
        a, msgs = self.anon(chat)
        md, _, _ = wa2md.render("x", msgs, None, anon=a)
        return md

    def test_inline_keyword_values(self):
        a = wa2md.Anonymizer("Grup Alfa", [{"sender": "Ali Veli"}])
        cases = {
            "şifre: Mavi-Kus99": "şifre: [parola]",
            "Şifresi=abc123xyz ok": "Şifresi=[parola] ok",
            "parola Zx9!qwe7": "parola [parola]",
            "password - Ab12cd34": "password - [parola]",
            "kullanıcı adı ve şifre: test ankara34": "kullanıcı adı ve şifre: [parola] ankara34",
            "pin 4821 yaz": "pin [parola] yaz",
            "PIN: 7788": "PIN: [parola]",
            "api key: Zk3j9Qm": "api key: [parola]",
            "SIFRE: Deneme_77.": "SIFRE: [parola].",
        }
        for src, exp in cases.items():
            with self.subTest(src=src):
                self.assertEqual(a.text(src), exp)

    def test_keyword_without_value_stays(self):
        a = wa2md.Anonymizer("Grup Alfa", [{"sender": "Ali Veli"}])
        for s in ("şifreyi unuttum", "Şifre değişti", "parolayı yeniledim ve pin yok", "pass the salt please",
                  "şifre: yok", "token ne zaman gelir", "anahtar teslim 550+KDV", "giriş bilgilerini gönderdim"):
            with self.subTest(s=s):
                self.assertEqual(a.text(s), s)

    def test_next_line_and_next_message(self):
        md = self.render("14.11.2026 10:00 - Ali Veli: Giriş şifre:\n"
                         "Deneme-123x\n"
                         "teşekkürler\n"
                         "14.11.2026 10:01 - Veli Can: wifi şifresi nedir\n"
                         "14.11.2026 10:02 - Veli Can: Kopek99x\n"
                         "14.11.2026 10:03 - Ali Veli: tamam\n"
                         "14.11.2026 10:04 - Ali Veli: Tesekkurler\n"
                         "14.11.2026 10:05 - Veli Can: merhaba1\n")
        self.assertIn("Giriş şifre:", md)
        self.assertNotIn("Deneme-123x", md)
        self.assertIn("teşekkürler", md)
        self.assertNotIn("Kopek99x", md)
        self.assertIn("tamam", md)
        self.assertIn("Tesekkurler", md)          # yalniz buyuk harfle baslayan sozcuk parola sayilmaz
        self.assertIn("merhaba1", md)             # kisa mesaj penceresi (3 mesaj) disinda

    def test_neighbour_window_any_sender_before_and_after(self):
        md = self.render("14.11.2026 10:00 - Ali Veli: Veli.8080\n"
                         "14.11.2026 10:01 - Ali Veli: şifrem\n"
                         "14.11.2026 10:02 - Veli Can: bilgisayar şifren ne\n"
                         "14.11.2026 10:03 - Ali Veli: 808080\n"
                         "14.11.2026 10:04 - Veli Can: pin girdin mi\n"
                         "14.11.2026 10:05 - Ali Veli: 4821\n"
                         "14.11.2026 10:06 - Ali Veli: tamam\n"
                         "14.11.2026 10:07 - Veli Can: whatsapp web açık mı\n"
                         "14.11.2026 10:08 - Ali Veli: 312051\n"
                         "14.11.2026 10:09 - Ali Veli: 2 3\n"
                         "14.11.2026 10:10 - Veli Can: Deneme.9x yapalım\n"
                         "14.11.2026 10:11 - Ali Veli: 1500\n")
        self.assertNotIn("8080", md)
        self.assertNotIn("808080", md)
        self.assertNotIn("4821", md)
        self.assertNotIn("312051", md)
        self.assertIn("[kod]", md)
        self.assertIn("1500", md)                 # pin penceresi 3 mesajla sinirli: 4 haneli sayi sonraki mesajda kalir
        self.assertIn("Deneme.9x yapalım", md)    # anahtar kelime yok (pencere disi): dokunulmaz

    def test_next_line_with_trailing_words(self):
        md = self.render("14.11.2026 10:00 - Ali Veli: Bütün şifreleri\n"
                         "Tavrex.8080 yapalım\n"
                         "hepimiz bilelim\n")
        self.assertIn("Bütün şifreleri", md)
        self.assertNotIn("8080", md)
        self.assertIn("yapalım", md)
        self.assertIn("hepimiz bilelim", md)

    def test_random_looking_token_and_repeat_in_quote(self):
        md = self.render("14.11.2026 10:00 - Ali Veli: kJUOrvClK01CqiIySZTL bu şifreyi yaptığına emin misin\n"
                         "14.11.2026 10:01 - Veli Can: Bütün şifreleri\n"
                         "Tavrex.8080 yapalım\n"
                         "14.11.2026 10:02 - Ali Veli: > Veli Can: Tavrex.8080\n"
                         "tamam\n")
        self.assertNotIn("kJUOrvClK01CqiIySZTL", md)
        self.assertNotIn("8080", md)
        self.assertIn("bu şifreyi yaptığına emin misin", md)
        a = wa2md.Anonymizer("Grup Alfa", [{"sender": "Ali Veli"}])
        self.assertEqual(a.text("dosya 20261018-1208-8E6F9D58.jpg ve MediaFileName2026Ab.jpg"),
                         "dosya 20261018-1208-8E6F9D58.jpg ve MediaFileName2026Ab.jpg")

    def test_secret_shapes(self):
        a = wa2md.Anonymizer("Grup Alfa", [{"sender": "Ali Veli"}])
        for s in ("ghp_" + "a1B2" * 6, "github_pat_" + "Ab1_" * 8, "sk-" + "Qw3rTy" * 4, "AKIA" + "A1B2C3D4E5F6G7H8",
                  "eyJhbGciOi.eyJzdWIiOiIx.SflKxwRJSM", "0123456789abcdef" * 2, "0123456789abcdef0123456789abcdef01234567",
                  "Zm9vYmFyMTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3A="):
            with self.subTest(s=s[:8]):
                self.assertEqual(a.text(f"bak {s} bitti"), "bak [parola] bitti")
        self.assertEqual(a.text("Authorization: Bearer abcDEF123456xyz"), "Authorization: Bearer [parola]")

    def test_one_time_codes(self):
        a = wa2md.Anonymizer("Grup Alfa", [{"sender": "Ali Veli"}])
        self.assertEqual(a.text("doğrulama kodu: 482913"), "doğrulama kodu: [kod]")
        self.assertEqual(a.text("Onay kodunuz 7391, kimseyle paylaşmayın"), "Onay kodunuz [kod], kimseyle paylaşmayın")
        self.assertEqual(a.text("kod 12.11.2026 ve 1500 TL"), "kod 12.11.2026 ve 1500 TL")
        self.assertEqual(a.text("1234 adet"), "1234 adet")

    def test_negatives_stay_intact(self):
        a = wa2md.Anonymizer("Grup Alfa", [{"sender": "Ali Veli"}])
        for s in ("fiyat 550+KDV", "25 ton yük", "12.11.2026 saat 10:30", "https://ornek.test/a/b?x=1",
                  "bkz #62 ve user/repo#12", "commit 1a2b3c4 ve abcdef0123", "Tamamlandı, Teşekkürler",
                  "https://github.com/x/y/commit/" + "0123456789abcdef" * 2 + "01234567"):
            with self.subTest(s=s):
                self.assertEqual(a.text(s), s)


class BlindConsole(unittest.TestCase):
    """Varsayilan bayraklarla gercek CLI: stdout+stderr'de ad, dosya adi, telefon ya da mesaj metni yok."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "in")
        self.out = os.path.join(self.tmp, "out")
        os.makedirs(self.src)
        import zipfile
        txt = ("14.11.2026 10:00 - Selin Aydın: gizli-proje için Kerem'e 0500 000 98 76 yaz\n"
               "14.11.2026 10:01 - Kerem: tamam selin@ornek.test Gizli Toplantı\n")
        with zipfile.ZipFile(os.path.join(self.src, "WhatsApp Chat with Selin Aydın.zip"), "w") as z:
            z.writestr("_chat.txt", txt)
            z.writestr("Selin_Aydin_5000009876.jpg", b"x")
        with zipfile.ZipFile(os.path.join(self.src, "WhatsApp Chat with Tuna Bey.zip"), "w") as z:
            z.writestr("_chat.txt", "bu satir bicimsiz Tuna Bey gizli-proje\nbir daha Kerem\n")
        with open(os.path.join(self.src, "WhatsApp Chat with Kerem.zip"), "wb") as f:
            f.write(b"not a zip Kerem")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, script, *argv):
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), script), *argv],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout + r.stderr

    def assert_blind(self, text):
        low = text.lower()
        for sec in SECRETS:
            self.assertNotIn(sec.lower(), low, sec)

    def test_wa2md_default_console_has_no_names(self):
        code, text = self.cli("wa2md.py", self.src, "--out", self.out)
        self.assertEqual(code, 0, text)
        self.assert_blind(text)
        self.assertIn("[Sohbet-1]", text)
        self.assertIn("girdi", text)                       # hatali girdiler girdi N olarak anilir
        self.assertIn("Ayrıştırılamayan satır sayısı: 2", text)

    def test_diagnostics_only_with_no_anonim_and_removed_flags_rejected(self):
        _, text = self.cli("wa2md.py", self.src, "--out", self.out, "--no-anonim")
        self.assertIn("bu satir bicimsiz", text)
        for flag in (["--esleme-goster"], ["--esleme-dosyasi", "x.json"], ["--tanilama"]):
            code, text = self.cli("wa2md.py", self.src, "--out", self.out, *flag)
            self.assertEqual(code, 2, flag)
            self.assertIn("unrecognized arguments", text)
        for sub in (["import", "x"], ["export", "--chats", "x"]):
            for flag in ("--esleme-goster", "--tanilama", "--esleme-dosyasi=y"):
                code, _ = self.cli("wa_web.py", *sub, "--out", self.out, flag)
                self.assertEqual(code, 2, (sub, flag))
        self.assertFalse(os.path.exists(os.path.join(self.out, "x.json")))

    def test_ascii_console_does_not_crash(self):
        """Linux/Windows sunucu konsolu ASCII/cp1252 olsa da Turkce metin cokmemeli (stdout UTF-8'e zorlanir)."""
        import subprocess
        for enc in ("ascii", "cp1252"):
            env = dict(os.environ, PYTHONIOENCODING=enc, PYTHONUTF8="0")
            r = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "wa2md.py"), self.src, "--out",
                                self.out], capture_output=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
            self.assertNotIn(b"Traceback", r.stderr)
            self.assertIn("doğrudan tanımlayıcıların".encode("utf-8"), r.stdout)

    def test_only_does_not_echo_names(self):
        code, text = self.cli("wa2md.py", self.src, "--out", self.out, "--only", "zzz-yok")
        self.assertEqual(code, 1)
        self.assert_blind(text)

    def test_wa_web_import_console_has_no_names(self):
        bdir = os.path.join(self.tmp, "bundles")
        os.makedirs(bdir)
        good = {"format": "wa-web-bundle", "version": 1, "session": "s1", "part": 1, "chat": "Selin Aydın", "final": True,
                "media": [], "total": 1, "today": "2026-11-16", "opts": {},
                "rows": [{"id": "true_1@c.us_AAAAAAAA", "stamp": "[10:00, 14.11.2026] Selin Aydın: ",
                          "text": "gizli-proje 0500 000 98 76"}]}
        with open(os.path.join(bdir, "wa-bundle-selin-s1-001.json"), "w", encoding="utf-8") as f:
            json.dump(good, f)
        with open(os.path.join(bdir, "wa-bundle-selin-s2-001.json"), "w", encoding="utf-8") as f:
            f.write('{"format": "wa-web-bundle", Kerem gizli-proje')
        code, text = self.cli("wa_web.py", "import", bdir, "--out", self.out)
        self.assertEqual(code, 0, text)
        self.assert_blind(text)
        self.assertIn("[Sohbet-1]", text)
        self.assertIn("JSON hatası", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
