"""nakliye grubu ilanlarinda kalan anonimlestirme bosluklari (A-F) ve korunacaklar.
Tum sohbetler, adlar, firma adlari, numaralar ve baglantilar uydurmadir. Telefonlar bariz sahte: 0500 000 00 00 ve
suslu rakamli bicimleri. Adlar repodaki diger testlerin uydurma adlaridir (Ali Veli, Arvo Kestel, Brin Tamsel,
Dorin Kaplo, Fenna Ruskal, Tavro, Xandor Plimm)."""
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import wa2md  # noqa: E402

_ENV = {}
TITLE = "Örnek Nakliye Grubu"
PEOPLE = ("Ali Veli", "Arvo Kestel", "Brin Tamsel")


def setUpModule():
    _ENV["old"] = os.environ.get("XDG_STATE_HOME")
    _ENV["dir"] = tempfile.mkdtemp(prefix="wa2md-state-")
    os.environ["XDG_STATE_HOME"] = _ENV["dir"]


def tearDownModule():
    if _ENV["old"] is None:
        os.environ.pop("XDG_STATE_HOME", None)
    else:
        os.environ["XDG_STATE_HOME"] = _ENV["old"]
    shutil.rmtree(_ENV["dir"], ignore_errors=True)


def run(rows, people=PEOPLE):
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


def one(line, sender="Ali Veli", people=PEOPLE):
    out, a = run([(sender, line)], people)
    return out[-1], a


def ad(line, people=PEOPLE):
    """Ilan imli (ayni mesajda telefon satiri olan) mesajin ilk satiri: yalniz sektor sozcuguyle kurulan ticari ad ikinci
    ilan imi ister (2. tur, F1)."""
    out, a = run([("Ali Veli", line + "\n" + PHONE)], people)
    return out[-2], a


def styled(s, base):
    """ASCII rakamlari verilen Unicode blogunun rakamlarina cevirir (base: o blogun '0' kod noktasi)."""
    return "".join(chr(base + int(c)) if c.isdigit() else c for c in s)


PHONE = "0500 000 00 00"
# Korunacaklar: fiyat, tonaj, olcu, tarih, saat, teker, oda; guzergah ve arac/dorse turleri
KEEP = ["45.000 TL", "26 ton", "13.60", "15.11.2026", "08:30", "10 teker", "2+1", "ADANA - MERSİN", "Adana'dan Mersin'e",
        "Konya çıkışlı", "tır", "kamyon", "kırkayak", "onteker", "lowbed", "tenteli", "damper", "frigo"]
KEEP_LINE = ("ADANA - MERSİN tır 26 ton 45.000 TL, yükleme 15.11.2026 08:30, 13.60 dorse 10 teker 2+1. "
             "Adana'dan Mersin'e kamyon, Konya çıkışlı kırkayak, onteker, lowbed, tenteli, damper, frigo")


class KeepMixin:
    def assertKept(self, out):
        for w in KEEP:
            self.assertIn(w, out)


class A_Phones(unittest.TestCase, KeepMixin):
    """A: suslu/tam genislikli rakamlar, gruplama ve ayractan bagimsiz cep/sabit numara, onek/kuyruk acikta kalmaz."""

    def masked(self, line, expect="[telefon]"):
        out, _ = one(line)
        self.assertEqual(out, expect, line)
        self.assertNotRegex(out.replace("[telefon]", ""), r"\d", line)

    def test_styled_digits(self):
        for base in (0xFF10, 0x1D7CE, 0x1D7D8, 0x1D7E2, 0x1D7EC, 0x1D7F6):    # tam genislikli + 5 matematiksel stil
            self.masked(styled(PHONE, base))
            self.masked(styled("+90 500 000 00 00", base))
            self.masked(styled("0322 000 00 00", base))

    def test_mixed_and_keycap_digits(self):
        self.masked("0500 " + styled("000 00 00", 0x1D7CE))
        self.masked("".join(c + "️⃣" if c.isdigit() else c for c in PHONE))

    def test_any_grouping_and_separator(self):
        for s in ("0500-00-0000", "0500 000 0000", "05000000000", "0500 0000000", "0 500 000 00 00", "0500.000.00.00",
                  "0500/000 00 00", "0500 - 000 00 00", "0500  000  00  00", "0500 000 00 00",
                  "0500 000 00 00", "0500–000–00–00", "+90 (500) 000 00 00", "0090 500 000 00 00",
                  "+90 0500 000 00 00", "500 000 00 00", "(500) 000 00 00", "0322 000 00 00", "0 (322) 000 00 00",
                  "0322-000-0000"):
            self.masked(s)

    def test_no_prefix_left(self):
        """A3: kalibin uzun dizinin yalniz sonunu eslemesi onegi acikta birakiyordu."""
        for s in ("0500 0500 000 00 00", "0 - 5000000000", "0/5000000000", "00 500 000 00 00", "900 500 000 00 00",
                  "(0500) 000 00 00"):
            self.masked(s)

    def test_second_number_after_hyphen(self):
        self.masked(PHONE + "-0500 000 00 01", "[telefon]-[telefon]")
        self.masked("05000000000-05000000001", "[telefon]-[telefon]")

    def test_context_kept(self):
        out, _ = one(f"Tel:{PHONE}'den ara, 2 araç")
        self.assertEqual(out, "Tel:[telefon]'den ara, 2 araç")
        out, _ = one(f"15.11.2026 {PHONE} 26 ton")
        self.assertEqual(out, "15.11.2026 [telefon] 26 ton")

    def test_not_a_phone(self):
        for s in (KEEP_LINE, "05.11.2026 150 km", "1.500.000.000 TL", "500.000.000 TL", "0,5000000000",
                  "5 10 15 20 25 30 35", "0 5 10 15 20 25 30", "13.600 kg 05:30"):   # 0850/0800: 4. tur S10, telefon
            out, _ = one(s)
            self.assertEqual(out, s)
            self.assertNotIn("[telefon]", out)
        out, _ = one(KEEP_LINE)
        self.assertKept(out)


class E_WhatsAppLinks(unittest.TestCase):
    """E: WhatsApp kanal kimligi ve grup davet kodu mevcut sosyal baglanti kuraliyla maskelenir; alan adi ve yol kalir."""

    def test_channel_and_invite(self):
        for raw, exp in (("https://whatsapp.com/channel/0029VaXyZ0a1b2C3d4E5f6", "https://whatsapp.com/channel/[kullanıcı]"),
                         ("www.whatsapp.com/channel/0029VaXyZ0a1b2C3d4E5f6 takip edin",
                          "www.whatsapp.com/channel/[kullanıcı] takip edin"),
                         ("https://chat.whatsapp.com/AbCdEfGhIjK0123456789", "https://chat.whatsapp.com/[kullanıcı]"),
                         ("chat.whatsapp.com/invite/AbCdEfGhIjK0123456789", "chat.whatsapp.com/invite/[kullanıcı]")):
            out, a = one(raw)
            self.assertEqual(out, exp)

    def test_other_links_kept(self):
        for s in ("https://github.com/ornek/proje/issues/12", "https://web.whatsapp.com/", "https://faq.whatsapp.com/123"):
            out, _ = one(s)
            self.assertEqual(out, s)


class A_PlateDoesNotEatPhone(unittest.TestCase):
    """A: saat + kisaltma + telefon ('08:30 TEL 0500 ...') plaka sanilip telefonun kuyrugu acikta kalmiyordu."""

    def test_time_abbrev_phone(self):
        out, _ = one(f"yükleme 08:30 TEL {PHONE}")
        self.assertEqual(out, "yükleme 08:30 TEL [telefon]")

    def test_plate_still_masked(self):
        out, _ = one("araç 34 ABC 123 yolda")
        self.assertEqual(out, "araç [plaka] yolda")


class B_ContactContext(unittest.TestCase):
    """B: iletisim sozcugunun ardindaki ya da ayni satirda maskelenen telefonun yanindaki ad, kisi etiketiyle maskelenir."""

    def label(self, out, a, line):
        m = re.search(r"Kişi (\d+)", out)
        self.assertTrue(m, (line, out))
        self.assertNotIn(m.group(0), a._people, line)          # katilimci degil, yeni kisi
        return m.group(0)

    def test_after_contact_word(self):
        for line, tmpl in ((f"İRTİBAT: Dorin Kaplo {PHONE}", "İRTİBAT: {} [telefon]"),
                           (f"irtibat Tavro Kaplo {PHONE}", "irtibat {} [telefon]"),   # ayrac ya da telefon (P2)
                           ("Yetkili: Fenna Ruskal", "Yetkili: {}"),
                           (f"TEL: DORİN KAPLO {PHONE}", "TEL: {} [telefon]"),
                           (f"İRT. TAVRO - {PHONE}", "İRT. {} - [telefon]"),
                           ("gsm: Tavro", "gsm: {}"),
                           ("Cep - Tavro", "Cep - {}"),
                           ("İletişim: Fenna Ruskal", "İletişim: {}")):
            out, a = one(line)
            self.assertEqual(out, tmpl.format(self.label(out, a, line)), line)

    def test_next_to_masked_phone(self):
        out, a = run([("Ali Veli", f"{PHONE} Alican Taşvelen"), ("Brin Tamsel", "Alican Taşvelen yarın yükler")])
        lab = self.label(out[-2], a, "after")
        self.assertEqual(out[-2:], [f"[telefon] {lab}", f"{lab} yarın yükler"])     # sozluk adi: her yerde maskelenir
        out, a = run([("Ali Veli", f"{PHONE} Dorin Kaplo"), ("Brin Tamsel", "Dorin Kaplo yarın yükler")])
        lab = self.label(out[-2], a, "after")       # 3. tur, ilke 3: telefonun hemen yani guclu kanit, sohbet geneli
        self.assertEqual(out[-2:], [f"[telefon] {lab}", f"{lab} yarın yükler"])
        out, a = one(f"Dorin Kaplo {PHONE}")
        self.assertEqual(out, f"{self.label(out, a, 'before')} [telefon]")
        out, a = one(f"DORİN KAPLO {PHONE}")
        self.assertEqual(out, f"{self.label(out, a, 'before caps')} [telefon]")

    def test_word_meaning_name_masked_not_reviewed(self):
        out, a = one(f"İletişim: Barış {PHONE}")
        self.assertEqual(out, f"İletişim: {self.label(out, a, 'barış')} [telefon]")
        self.assertNotIn(wa2md._key("Barış"), a.review)

    def test_not_masked(self):
        for line in (f"ACİL YÜK {PHONE}", f"ADANA - MERSİN {PHONE}", f"Konya {PHONE}", f"Tel: Merkez Ofis {PHONE}",
                     f"Gebze {PHONE}", "Tel çit lazım", f"{PHONE} tır 26 ton", f"irtibat için {PHONE}",
                     f"{KEEP_LINE} İrtibat: {PHONE}", f"Tel: {PHONE} Konya çıkışlı lowbed"):
            out, _ = one(line)
            self.assertEqual(out, line.replace(PHONE, "[telefon]"), line)


class C_LabelJoin(unittest.TestCase):
    """C: katilimcinin kendi etiketine yapisik kalan ad parcasi etikete katilir (gorunen ad 'Plimm', metinde 'Xandor')."""
    PEOPLE = PEOPLE + ("Plimm",)

    def check(self, line, tmpl):
        out, a = one(line, people=self.PEOPLE)
        self.assertEqual(out, tmpl.format(p=a.labels["Plimm"]), line)

    def test_joined(self):
        self.check("Xandor+Plimm ADANA - MERSİN tır", "{p} ADANA - MERSİN tır")
        self.check("Xandor + Plimm", "{p}")
        self.check("Xandor Plimm", "{p}")                       # ilan altindaki imza satiri
        self.check("Plimm Xandor", "{p}")
        self.check(f"yük için Xandor Plimm arayın {PHONE}", "yük için {p} arayın [telefon]")   # ilan imi (F2)

    def test_not_joined(self):
        self.check("Dün Plimm aradı", "Dün {p} aradı")           # cumle basindaki siradan sozcuk
        self.check("Konya Plimm", "Konya {p}")                   # il adi
        self.check("Selam Plimm", "Selam {p}")
        self.check("Plimm Bey geldi", "{p} Bey geldi")
        self.check("Plimm Nakliyat", "{p} Nakliyat")             # tek maske zaten
        self.check("dün Review Plimm yaptı", "dün Review {p} yaptı")    # ilan imi yok: siradan sozcuk katilmaz (F2)


class D_TradeNames(unittest.TestCase):
    """D: sektor sozcugu ya da hukuki bicim uzerine kurulu firma adinin ayirt edici sozcukleri tek [firma] maskesi."""

    def test_masked(self):
        for line, exp in (("KAPLO LOJİSTİK SAN. TİC. LTD. ŞTİ.", "[firma] LOJİSTİK SAN. TİC. LTD. ŞTİ."),   # hukuki bicim
                          ("Tavro Kaplo Taşımacılık A.Ş. yük arıyor", "[firma] Taşımacılık A.Ş. yük arıyor"),
                          ("Kaplo Ltd. Şti.", "[firma] Ltd. Şti."),
                          ("Kaplo Trans Ltd.Şti.", "[firma] Trans Ltd.Şti.")):
            out, a = one(line)
            self.assertEqual(out, exp, line)
        for line, exp in (("Kaplo Nakliyat", "[firma] Nakliyat"),          # yalniz sektor sozcugu: ilan imi (F1)
                          ("Kardeşler Nakliyat", "[firma] Nakliyat"),
                          ("Kaplo Kargo'ya sor", "[firma] Kargo'ya sor"),
                          ("Gebze Kaplo Transport", "Gebze [firma] Transport")):
            out, a = ad(line)
            self.assertEqual(out, exp, line)

    def test_participant_part_one_mask(self):
        out, _ = ad("Kestel ve Oğulları Nakliyat")
        self.assertEqual(out, "[firma] Nakliyat")
        out, a = one("Kestel Nakliyat")
        self.assertEqual(out, a.labels["Arvo Kestel"] + " Nakliyat")

    def test_not_masked(self):
        for line in ("Konya Nakliyat", "ADANA NAKLİYAT", "yük nakliye fiyatı", "Uygun Nakliye", "evden eve nakliyat",
                     "Konya çıkışlı nakliye", "Tır Nakliye", "Ankara Lojistik Merkezi", KEEP_LINE):
            out, _ = one(line)
            self.assertEqual(out, line)


class OverMasking(unittest.TestCase, KeepMixin):
    """Katilimci adinin ilan sozcugu olan parcasi ('Velko Teker', 'Tır Fenna') 3. turdan beri main gibi maskelenir
    (ilke 2: main'in maskeledigi hicbir sey acilmaz; '10 teker' -> '10 Kişi N' kabul edilen asiri maskelemedir). Tek istisna
    yer listesindeki parcanin kanitli guzergahta kalmasidir ('Konya çıkışlı'). Tam ad ve obur parcalar maskelenir."""
    PEOPLE = PEOPLE + ("Velko Teker", "Tır Fenna", "Xandor Konya")

    def test_vocabulary_parts_masked_place_part_kept_in_route(self):
        out, a = one(KEEP_LINE + ", altı teker fazla", people=self.PEOPLE)
        t, r = a.labels["Velko Teker"], a.labels["Tır Fenna"]
        exp = (KEEP_LINE + ", altı teker fazla").replace(" tır ", f" {r} ").replace("10 teker", f"10 {t}").replace(
            "altı teker", f"altı {t}")
        self.assertEqual(out, exp)
        self.assertIn("Konya çıkışlı", out)
        k = a.labels["Xandor Konya"]
        for line, want in (("Konya aradı", f"{k} aradı"), (f"Konya - Tel: {PHONE}", f"{k} - Tel: [telefon]")):
            out, a = one(line, people=self.PEOPLE)
            self.assertEqual(out, want, line)

    def test_full_and_other_parts_still_masked(self):
        out, a = one("Velko Teker, Tır Fenna, Xandor Konya ve Velko geldi", people=self.PEOPLE)
        self.assertEqual(out, "{} , {} , {} ve {} geldi".replace(" ,", ",").format(
            a.labels["Velko Teker"], a.labels["Tır Fenna"], a.labels["Xandor Konya"], a.labels["Velko Teker"]))


class F_BusinessDomain(unittest.TestCase):
    """F: dar kural: ana bolumunde nakliye sektor sozcugu olan ticari alan adi -> [firma]; baska baglanti okunur kalir."""

    def test_masked(self):
        for line, exp in (("www.kaplonakliyat.com", "www.[firma].com"),
                          ("https://www.kaplo-lojistik.com.tr/iletisim", "https://www.[firma].com.tr/[yol]"),   # L9
                          ("kaplotransport.net adresinden bakın", "[firma].net adresinden bakın"),
                          ("KaploNakliyat.com.tr/ilan?id=5", "[firma].com.tr/[yol]")):
            out, a = one(line)
            self.assertEqual(out, exp, line)

    def test_software_and_other_links_kept(self):
        for line in ("https://github.com/ornek/nakliye-app/issues/12", "https://www.ornekurun.com.tr/ilan/nakliye-12",
                     "demo.ornekurun.com.tr", "https://docs.python.org/3/library/re.html", "www.ornekkargo.com",
                     "lojistikbirligi.org.tr", "https://translate.google.com", "nakliye.app.example.com",
                     "dosya_nakliyat.com.pdf"):
            out, _ = one(line)
            self.assertEqual(out, line)

    def test_email_wins(self):
        out, _ = one("info@kaplonakliyat.com")
        self.assertEqual(out, "[e-posta]")
