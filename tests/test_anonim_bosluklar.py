"""olculen anonimlestirme bosluklari (A-E), ad sozlugu ve supheli kalan dosyasi.
Tum sohbetler, adlar, numaralar ve dosya adlari uydurmadir. Sozlukte OLMAYAN uydurma adlar (Arvo Kestel, Tavro, ...)
yalniz sistem satiri / hitap / ek ad yoluyla bulunabildiklerini gostermek icin kullanilir."""
import io
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

TITLE = "Örnek Satranç Kulübü"

# Ayni olaylar iki yerelde: Android Ingilizce (M/D/YY, h:mm AM) ve Turkce (GG.AA.YYYY SS:DD)
EN = """11/14/26, 9:00 AM - Ali Veli created group "Örnek Satranç Kulübü"
11/14/26, 9:01 AM - Ali Veli added Arvo Kestel and Brin Tamsel
11/14/26, 9:02 AM - Dorin Kaplo joined using this group's invite link
11/14/26, 9:03 AM - +90 500 000 11 22 left
11/14/26, 9:04 AM - Ali Veli removed Fenna Ruskal
11/14/26, 9:05 AM - Ali Veli changed the subject from "Eski Ekip" to "Örnek Satranç Kulübü"
11/14/26, 9:06 AM - Velko Darsun changed to +90 500 000 33 44
11/14/26, 9:07 AM - Ali Veli: Arvo Kestel'e ve Brin'e selam, Dorin geldi mi? Fenna'yı da ekleyelim
11/14/26, 9:08 AM - Can Er: dün Tavro abi aradı, Hüseyin bey ve mehmet abi de gelecek
11/14/26, 9:09 AM - Can Er: satranç eğitimi cumartesi, Örnek Satranç Kulübü toplantısı da var
11/14/26, 9:10 AM - Ali Veli: DOC-20261114-WA0003.pdf (file attached)
a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6.0.pdf
11/14/26, 9:11 AM - Ali Veli: IMG-20261114-WA0001.jpg (file attached)
11/14/26, 9:12 AM - Can Er: Kisi_karti.vcf (file attached)
11/14/26, 9:13 AM - Can Er: yedek.zip (file attached)
11/14/26, 9:14 AM - Can Er: wifi şifre: Mavi-Kus99
"""
TR = """14.11.2026 09:00 - Ali Veli grubu oluşturdu
14.11.2026 09:01 - Ali Veli, Arvo Kestel ve Brin Tamsel'i ekledi
14.11.2026 09:02 - Dorin Kaplo bu grubun davet bağlantısını kullanarak katıldı
14.11.2026 09:03 - +90 500 000 11 22 ayrıldı
14.11.2026 09:04 - Ali Veli, Fenna Ruskal'ı çıkardı
14.11.2026 09:05 - Ali Veli konuyu "Örnek Satranç Kulübü" olarak değiştirdi
14.11.2026 09:06 - Velko Darsun telefon numarasını değiştirdi
14.11.2026 09:07 - Ali Veli: Arvo Kestel'e ve Brin'e selam, Dorin geldi mi? Fenna'yı da ekleyelim
14.11.2026 09:08 - Can Er: dün Tavro abi aradı, Hüseyin bey ve mehmet abi de gelecek
14.11.2026 09:09 - Can Er: satranç eğitimi cumartesi, Örnek Satranç Kulübü toplantısı da var
14.11.2026 09:10 - Ali Veli: DOC-20261114-WA0003.pdf (dosya ekli)
a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6.0.pdf
14.11.2026 09:11 - Ali Veli: IMG-20261114-WA0001.jpg (dosya ekli)
14.11.2026 09:12 - Can Er: Kisi_karti.vcf (dosya ekli)
14.11.2026 09:13 - Can Er: yedek.zip (dosya ekli)
14.11.2026 09:14 - Can Er: wifi şifre: Mavi-Kus99
"""
FILES = {"DOC-20261114-WA0003.pdf": b"%PDF", "IMG-20261114-WA0001.jpg": b"jpg", "Kisi_karti.vcf": b"BEGIN:VCARD",
         "yedek.zip": b"PK"}
REAL = ["Ali Veli", "Arvo", "Kestel", "Brin", "Tamsel", "Dorin", "Kaplo", "Fenna", "Ruskal", "Velko", "Darsun", "Tavro",
        "Hüseyin", "mehmet", "500 000 11 22", "500 000 33 44", "Mavi-Kus99", "Can Er"]


def run(*argv):
    o, e = io.StringIO(), io.StringIO()
    with redirect_stdout(o), redirect_stderr(e):
        code = wa2md.main(list(argv))
    return code, o.getvalue(), e.getvalue()


class Locales(unittest.TestCase):
    """Her bosluk sinifi Ingilizce ve Turkce yerel bicimde, CLI uzerinden."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def export(self, text, files=FILES):
        d = os.path.join(self.tmp, "src", TITLE)
        os.makedirs(d)
        with open(os.path.join(d, f"WhatsApp Chat with {TITLE}.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        for n, b in files.items():
            with open(os.path.join(d, n), "wb") as f:
                f.write(b)
        return d

    def go(self, text, *flags, files=FILES):
        out = os.path.join(self.tmp, "out")
        code, o, e = run(self.export(text, files), "--out", out, *flags)
        self.assertEqual(code, 0, e)
        with open(os.path.join(out, "Sohbet-1", "Sohbet-1.md"), encoding="utf-8") as f:
            return f.read(), o + e, out

    def each(self):
        """(yerel, metin) ciftleri; her biri temiz bir gecici klasorde calisir (cagiran subTest acar)."""
        for name, text in (("en", EN), ("tr", TR)):
            shutil.rmtree(self.tmp, ignore_errors=True)
            os.makedirs(self.tmp)
            yield name, text

    def test_a_system_line_people_masked_consistently(self):
        for loc, text in self.each():
            with self.subTest(locale=loc):
                md, _, _ = self.go(text)
                for bad in ("Arvo", "Kestel", "Brin", "Tamsel", "Dorin", "Kaplo", "Fenna", "Ruskal", "500 000 11 22",
                            "Velko", "Darsun"):
                    self.assertNotIn(bad, md, bad)
                self.assertIn("Katılımcılar: Kişi 1, Kişi 2", md)          # baslik: yalniz yazanlar
                sys_lines = [l for l in md.split("\n") if l.startswith("_09:0")]
                body = md[md.index("**Kişi 1** 09:07"):]
                # sistem satirinda eklenen ilk kisi, metindeki 'Arvo Kestel'e' ile ayni etiketi alir
                lab = next(l for l in sys_lines if "09:01" in l).split("– ")[1]
                first = lab.split(" ve ")[0].split(" and ")[0].replace("Kişi 1 added ", "").replace("Kişi 1, ", "")
                self.assertTrue(first.startswith("Kişi "), lab)
                self.assertIn(first.rstrip("_") + "'e ve", body)

    def test_b_body_names_honorifics_and_system_people(self):
        for loc, text in self.each():
            with self.subTest(locale=loc):
                md, _, _ = self.go(text)
                body = md[md.index("**Kişi 1** 09:07"):]
                self.assertRegex(body, r"Kişi \d+'e ve Kişi \d+'e selam, Kişi \d+ geldi mi\? Kişi \d+'yı da")
                self.assertRegex(body, r"dün Kişi \d+ abi aradı, Kişi \d+ bey ve Kişi \d+ abi de gelecek")

    def test_c_title_not_substituted_in_text(self):
        for loc, text in self.each():
            with self.subTest(locale=loc):
                md, _, out = self.go(text)
                self.assertIn("# Sohbet-1", md)
                self.assertIn("satranç eğitimi cumartesi, Örnek Satranç Kulübü toplantısı da var", md)
                self.assertNotIn("Sohbet-1 eğitimi", md)
                subject = next(l for l in md.split("\n") if "09:05" in l)
                self.assertIn('"Sohbet-1"', subject)                     # konu degisikligi satiri sohbeti tanimlar
                self.assertNotIn("Örnek", subject)
                self.assertEqual(os.listdir(out), ["Sohbet-1"])            # klasor adi; supheli kalan yok

    def test_d_password_detector_ignores_attachment_titles_and_names(self):
        for loc, text in self.each():
            with self.subTest(locale=loc):
                md, _, out = self.go(text, "--belgeleri-kopyala")
                self.assertIn("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6.0.pdf", md)    # ek basligi parola sayilmaz
                self.assertEqual(md.count("[parola]"), 1)                  # dogru pozitif: 'şifre: [parola]'
                self.assertIn("wifi şifre: [parola]", md)
                media = sorted(os.listdir(os.path.join(out, "Sohbet-1", "media")))
                self.assertEqual(media, sorted(FILES))                     # hicbiri medya-N olmadi

    def test_e_attachments_skipped_by_default_with_manifest(self):
        for loc, text in self.each():
            with self.subTest(locale=loc):
                md, console, out = self.go(text)
                media = os.listdir(os.path.join(out, "Sohbet-1", "media"))
                self.assertEqual(media, ["IMG-20261114-WA0001.jpg"])
                self.assertIn("_(ek kopyalanmadı: Kisi_karti.vcf, kişi kartı)_", md)
                with open(os.path.join(out, "Sohbet-1", "ekler.md"), encoding="utf-8") as f:
                    man = f.read()
                self.assertIn("| IMG-20261114-WA0001.jpg | görüntü | kopyalandı, elle kontrol gerekli |", man)
                for n, kind in (("DOC-20261114-WA0003.pdf", "PDF"), ("Kisi_karti.vcf", "kişi kartı"), ("yedek.zip", "arşiv")):
                    self.assertIn(f"| {n} | {kind} | kopyalanmadı", man)
                self.assertIn("UYARI: ekler: 1 kopyalandı, elle kontrol gerekli (görüntü 1); 3 kopyalanmadı", console)

    def test_no_real_names_anywhere_and_summary(self):
        for loc, text in self.each():
            with self.subTest(locale=loc):
                md, console, out = self.go(text)
                blob = console
                for dp, ds, fs in os.walk(out):
                    blob += " ".join(ds + fs)
                    for f in fs:
                        with open(os.path.join(dp, f), encoding="utf-8", errors="replace") as fh:
                            blob += fh.read()
                for bad in REAL:
                    self.assertNotIn(bad.lower(), blob.lower(), bad)
                self.assertRegex(console, r"maskelenen: gönderen \d+, sistem satırı \d+, hitap \d+, sohbet adı \d+, parola 1")

    def test_no_anonim_copies_everything(self):
        out = os.path.join(self.tmp, "out")
        code, o, e = run(self.export(EN), "--out", out, "--no-anonim")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(os.listdir(os.path.join(out, TITLE, "media"))), sorted(FILES))


def anon(text, chat="Grup Alfa", **kw):
    msgs, _ = wa2md.parse(text)
    return wa2md.Anonymizer(chat, msgs, **kw)


class SystemPeople(unittest.TestCase):
    def test_english_events(self):
        cases = {
            "Ali Veli added Arvo Kestel, Brin Tamsel and Dorin Kaplo": ["Ali Veli", "Arvo Kestel", "Brin Tamsel", "Dorin Kaplo"],
            "~ Fenna joined using this group's invite link": ["Fenna"],
            "Ali Veli added ~\u202fTavro 🃏, ~\u202fBrin Tamsel, and ~\u202fDorin ✨": ["Ali Veli", "Tavro 🃏", "Brin Tamsel",
                                                                              "Dorin ✨"],
            "+90 500 000 11 22 left": ["+90 500 000 11 22"],
            "Ali Veli removed Tavro": ["Ali Veli", "Tavro"],
            "Ali Veli changed this group's icon": ["Ali Veli"],
            "Ali Veli changed the group description": ["Ali Veli"],
            "Your security code with Brin Tamsel changed. Tap to learn more.": ["Brin Tamsel"],
            "You added Arvo": ["Arvo"],
            "Messages and calls are end-to-end encrypted. No one outside of this chat can read them.": [],
            "This message was deleted": [],
        }
        for line, exp in cases.items():
            with self.subTest(line=line):
                self.assertEqual([p for p, _ in wa2md.system_people(line)], exp)

    def test_turkish_events(self):
        cases = {
            "Ali Veli, Arvo Kestel'i ekledi": ["Ali Veli", "Arvo Kestel"],
            "Ali Veli, Brin Tamsel ve Dorin'i ekledi": ["Ali Veli", "Brin Tamsel", "Dorin"],
            "Fenna bu grubun davet bağlantısını kullanarak katıldı": ["Fenna"],
            "+90 500 000 11 22 ayrıldı": ["+90 500 000 11 22"],
            "Ali Veli, Tavro'yu çıkardı": ["Ali Veli", "Tavro"],
            "Ali Veli grubu oluşturdu": ["Ali Veli"],
            "Ali Veli bu grubun simgesini değiştirdi": ["Ali Veli"],
            "Brin Tamsel ile güvenlik kodunuz değişti.": ["Brin Tamsel"],
            "Ali Veli sizi ekledi": ["Ali Veli"],
            "Mesajlar ve aramalar uçtan uca şifrelidir.": [],
        }
        for line, exp in cases.items():
            with self.subTest(line=line):
                self.assertEqual([p for p, _ in wa2md.system_people(line)], exp)

    def test_number_change_keeps_one_pseudonym(self):
        a = anon("11/14/26, 9:00 AM - Can Er: selam\n"
                 "11/14/26, 9:01 AM - +90 500 000 11 22 changed to +90 500 000 33 44\n")
        self.assertEqual(a.text("+90 500 000 11 22 ve +90 500 000 33 44"), "Kişi 2 ve Kişi 2")

    def test_system_person_all_forms_in_body(self):
        a = anon("14.11.2026 09:00 - Ali Veli, Arvo Kestel'i ekledi\n14.11.2026 09:01 - Ali Veli: selam\n")
        self.assertEqual(a.text("Arvo'ya, ARVO KESTEL, kestel'in, ArvoKestel, arvo.kestel"),
                         "Kişi 2'ya, Kişi 2, Kişi 2'in, Kişi 2, Kişi 2")

    def test_emoji_in_contact_name(self):
        a = anon("14.11.2026 09:00 - Ali Veli, Tavro 🚒'yu ekledi\n14.11.2026 09:01 - Ali Veli: Tavro nerede\n")
        self.assertEqual(a.text("Tavro nerede"), "Kişi 2 nerede")
        a = anon("11/14/26, 9:00 AM - Ali Veli added ~\u202fDorin🃏\n11/14/26, 9:01 AM - Ali Veli: selam\n")
        self.assertEqual(a.text("Ali Veli added ~\u202fDorin🃏", title=True), "Kişi 1 added ~\u202fKişi 2")


class Honorifics(unittest.TestCase):
    def setUp(self):
        self.a = anon("14.11.2026 09:00 - Can Er: selam\n", group=True)   # grup: baslik kisi sayilmaz (etiket 2 bos)

    def test_masked_even_if_not_participant(self):
        for hon in ("Bey", "bey", "Hanım", "hanım", "abi", "abla", "hocam", "hoca", "başkan", "başkanım", "kardeş",
                    "kardeşim", "amca", "teyze", "usta", "abi'ye", "beyin"):
            with self.subTest(hon=hon):
                self.assertEqual(self.a.text(f"dün Tavro {hon} geldi"), f"dün Kişi 2 {hon} geldi")
        self.assertRegex(self.a.text("Hüseyin Bey aradı"), r"^Kişi \d+ Bey aradı$")   # sozluk adi: cumle basinda da
        self.assertRegex(self.a.text("yarın deniz abi gelir"), r"^yarın Kişi \d+ abi gelir$")   # belirsiz ad + hitap

    def test_false_positive_guards(self):
        for s in ("Sayın Başkan geldi", "Tamam abi", "Selam hocam", "Günaydın hocam nasılsınız", "Merhaba abla",
                  "Yönetim Kurulu Başkanı aradı", "Dernek Başkanı ile görüştük", "Kolay gelsin usta", "Evet abi",
                  "beyaz araç geldi", "tamam abi"):
            with self.subTest(s=s):
                self.assertEqual(self.a.text(s), s)

    def test_unknown_sentence_initial_goes_to_review(self):
        md = wa2md.render("x", *self._msgs("Tavro abi geldi"))[0]
        self.assertIn("Tavro abi geldi", md)
        a = self._a
        self.assertEqual(a.review[wa2md._key("Tavro")][2], "honorific")

    def _msgs(self, text):
        msgs, _ = wa2md.parse(f"14.11.2026 09:00 - Can Er: {text}\n")
        self._a = wa2md.Anonymizer("x", msgs)
        return msgs, None, "media", self._a


class Dictionary(unittest.TestCase):
    def a(self, text):
        msgs, _ = wa2md.parse("".join(f"14.11.2026 09:{i:02d} - Can Er: {t}\n" for i, t in enumerate(text)))
        a = wa2md.Anonymizer("x", msgs)
        md = wa2md.render("x", msgs, None, anon=a)[0]
        return md, a

    def test_unambiguous_names_any_case(self):
        md, a = self.a(["yarın mehmet gelecek", "Gökhan'a sor", "AYŞEGÜL geldi", "mehmetle konuştum"])
        for bad in ("mehmet", "Gökhan", "AYŞEGÜL"):
            self.assertNotIn(bad, md)
        self.assertRegex(md, r"yarın Kişi \d+ gelecek")
        self.assertRegex(md, r"Kişi \d+'le konuştum")                   # ayni kisi, apostrofsuz ek
        self.assertEqual(a.stats.get("dictionary"), 4)

    def test_ambiguous_words_need_context(self):
        md, a = self.a(["deniz kenarında umut var", "Umut var mı", "dün Deniz aradı", "Umut'a sor", "Deniz Kaya geldi",
                        "12 Ekim'de Türk bayrağı", "güzel bir gün", "Temel Satranç Eğitimi", "bkz. Türk Medeni Kanunu"])
        self.assertIn("deniz kenarında umut var", md)                  # kucuk harf: sozcuk
        self.assertIn("Umut var mı", md)                               # cumle basi: dokunulmaz
        self.assertRegex(md, r"dün Kişi \d+ aradı")                    # cumle ortasinda buyuk harf
        self.assertRegex(md, r"Kişi \d+'a sor")                        # ozel ad kesme eki
        self.assertRegex(md, r"\*\*Kişi 1\*\* 09:04\nKişi \d+ geldi")  # Ad + Soyad
        self.assertIn("12 Ekim'de Türk bayrağı", md)
        self.assertIn("Temel Satranç Eğitimi", md)
        self.assertIn("bkz. Türk Medeni Kanunu", md)
        self.assertIn("güzel bir gün", md)
        self.assertIn(wa2md._key("umut"), a.review)
        self.assertEqual(a.review[wa2md._key("Umut")][2], "lowercase")

    def test_lists_have_source_and_licence(self):
        for fn in ("tr-adlar.txt", "tr-soyadlar.txt", "sozcuk-adlar.txt"):
            with open(os.path.join(os.path.dirname(HERE), "adlar", fn), encoding="utf-8") as f:
                head = f.read(800)
            self.assertIn("Kaynak:", head, fn)
            self.assertTrue("CC0" in head or "repo lisansiyla" in head, fn)
        g, f, a = wa2md.name_lists()
        self.assertGreater(len(g), 1500)
        self.assertGreater(len(f), 3000)
        self.assertTrue({"deniz", "umut", "baris", "kaya"} <= a)


class ExtraNamesAndReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "Grup")
        os.makedirs(self.src)
        with open(os.path.join(self.src, "WhatsApp Chat with Grup.txt"), "w", encoding="utf-8") as f:
            f.write("14.11.2026 09:00 - Can Er: zorbek tuvaq ile Zorbek'e sorduk\n"
                    "14.11.2026 09:01 - Can Er: Umut geldi, umut var\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def md(self, out):
        with open(os.path.join(out, "Sohbet-1", "Sohbet-1.md"), encoding="utf-8") as f:
            return f.read()

    def test_extra_names_comma_and_file(self):
        out = os.path.join(self.tmp, "o1")
        run(self.src, "--out", out, "--ek-adlar", "Zorbek Tuvaq")
        self.assertIn("Kişi 2 ile Kişi 2'e sorduk", self.md(out))
        p = os.path.join(self.tmp, "adlar.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# yorum\nZorbek Tuvaq\n")
        out = os.path.join(self.tmp, "o2")
        code, o, e = run(self.src, "--out", out, "--extra-names", "@" + p)
        self.assertIn("Kişi 2 ile Kişi 2'e sorduk", self.md(out))
        self.assertIn("ek ad 2", o)
        self.assertNotIn("zorbek", (o + e).lower())

    def test_review_file_outside_shareable_output(self):
        out = os.path.join(self.tmp, "o")
        code, o, e = run(self.src, "--out", out)
        self.assertEqual(sorted(os.listdir(out)), ["Sohbet-1"])        # inceleme dosyasi cikti klasorunde DEGIL
        rdir = wa2md.default_review_dir(out)                           # <durum>/wa2md/inceleme/<zaman>-<ozet>
        self.assertTrue(rdir.startswith(os.path.join(os.environ["XDG_STATE_HOME"], "wa2md", "inceleme")))
        p = os.path.join(rdir, "Sohbet-1-supheli-adlar.txt")
        self.assertIn(p, o)                                             # yol sonda yazilir
        with open(p, encoding="utf-8") as f:
            rev = f.read()
        self.assertTrue(rev.startswith("# OLASI GERÇEK ADLAR İÇERİR - PAYLAŞMA"))
        self.assertNotIn("Yeni bilgi içermez", rev)
        rows = [l.split("\t") for l in rev.split("\n") if l and not l.startswith("#")]
        self.assertEqual([r[0] for r in rows], ["Umut"])              # ayni sozcuk tek satir (ilk gorunen bicim)
        self.assertEqual(rows[0][1], "2")
        self.assertIn("şüpheli kalan: 1 sözcük (1 öncelikli), 2 geçiş", o)
        self.assertNotIn("Umut", o + e)                                 # konsolda ad yok
        self.assertIn("zorbek tuvaq", self.md(out))                     # sozlukte yok: yedek secenek gerekir


if __name__ == "__main__":
    unittest.main()
