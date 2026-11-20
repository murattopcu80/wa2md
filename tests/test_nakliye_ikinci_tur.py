"""2. tur: bagimsiz incelemenin bulgulari (P1-P2, L1-L9, F1-F4) ve basarim korumasi.
Tum sohbetler, adlar, firma adlari, numaralar ve baglantilar uydurmadir; adlar repodaki diger testlerin ve incelemenin
uydurma adlaridir. Telefonlar bariz sahte: 0500 000 00 00 ve bicimleri."""
import os
import re
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_nakliye_gruplari import PEOPLE, PHONE, KEEP_LINE, ad, one, run, setUpModule, tearDownModule  # noqa: E402,F401
import wa2md  # noqa: E402


def lab(out, a):
    """Satirdaki ilk 'Kişi N' etiketi; katilimci degil (iletisim/sozluk bulgusu)."""
    m = re.search(r"Kişi \d+", out)
    assert m, out
    assert m.group(0) not in a._people, out
    return m.group(0)


class P1_FieldLabel(unittest.TestCase):
    """':' ile biten sozcukler alan etiketidir; ad ':'dan sonraki sozcuklerdir (etiket adin yerini yemez)."""

    def test_name_after_label(self):
        for line, tmpl in (("İRTİBAT İÇİN: Dorin Kaplo", "İRTİBAT İÇİN: {}"),
                           ("TEL NO: DORİN KAPLO", "TEL NO: {}"),
                           ("İRTİBAT NO: Dorin Kaplo", "İRTİBAT NO: {}"),
                           ("İletişim İçin: Dorin Kaplo", "İletişim İçin: {}"),
                           ("Yetkili Kişi: Dorin Kaplo", "Yetkili Kişi: {}"),
                           (f"Tel / WhatsApp: Dorin Kaplo {PHONE}", "Tel / WhatsApp: {} [telefon]")):
            out, a = one(line)
            self.assertEqual(out, tmpl.format(lab(out, a)), line)

    def test_label_then_phone(self):
        for line in (f"Tel No: {PHONE}", f"İRTİBAT İÇİN: {PHONE}", f"Telefon Numarası: {PHONE}", f"Yetkili Kişi: {PHONE}"):
            out, _ = one(line)
            self.assertEqual(out, line.replace(PHONE, "[telefon]"), line)

    def test_name_before_colon_then_phone(self):
        out, a = one(f"İrtibat Dorin Kaplo: {PHONE}")
        self.assertEqual(out, f"İrtibat {lab(out, a)}: [telefon]")


class P2_OrdinaryText(unittest.TestCase):
    """Iletisim sozcugunden sonra ad icin ayrac ya da ayni satirda telefon gerekir; dolgu sozcukleri ad degildir; yalniz
    baglamla bulunan (sozluk adi ya da listede soyad olmayan) ad baska satira yayilmaz."""

    def test_unchanged(self):
        for line in ("WhatsApp Web açılmıyor", "Telefon Numarası", "Yetkili Servis", "Cep Telefonu Faturası",
                     "İletişim Bilgileri", f"{PHONE} Sadece WhatsApp", f"Hafta İçi Arayınız {PHONE}", f"Tel No: {PHONE}",
                     "WhatsApp Business Api dokümanı", f"Yetkili Servis {PHONE}", f"{PHONE} Hafta İçi",
                     f"Cep Telefonu {PHONE}", "irtibat Tavro Kaplo"):
            out, _ = one(line)
            self.assertEqual(out, line.replace(PHONE, "[telefon]"), line)

    def test_context_only_not_propagated(self):
        out, a = run([("Ali Veli", f"İrtibat: Proje Masası {PHONE}"), ("Brin Tamsel", "proje masası toplandı"),
                      ("Brin Tamsel", "Proje Masası toplandı"), ("Ali Veli", "WhatsApp: Business Api"),
                      ("Brin Tamsel", "business api dokümanı")])
        self.assertEqual(out[-5], f"İrtibat: {lab(out[-5], a)} [telefon]")      # o geciste maskelenir
        self.assertEqual(out[-4:], ["proje masası toplandı", "Proje Masası toplandı", "WhatsApp: Business Api",
                                    "business api dokümanı"])

    def test_named_run_propagates(self):
        out, a = run([("Ali Veli", f"Tel: Alican Taşvelen {PHONE}"), ("Brin Tamsel", "alican taşvelen geldi")])
        l = lab(out[-2], a)
        self.assertEqual(out[-2:], [f"Tel: {l} [telefon]", f"{l} geldi"])


class L1_NameBeforeContactWord(unittest.TestCase):
    def test_masked(self):
        for line, tmpl in ((f"Dorin Kaplo Tel: {PHONE}", "{} Tel: [telefon]"),
                           (f"DORİN KAPLO GSM {PHONE}", "{} GSM [telefon]"),
                           (f"Dorin Kaplo - İrtibat: {PHONE}", "{} - İrtibat: [telefon]")):
            out, a = one(line)
            self.assertEqual(out, tmpl.format(lab(out, a)), line)

    def test_not_masked(self):
        for line in ("Proje Ekibi Whatsapp grubu", "Yeni Telefon aldım", f"Konya Merkez Tel: {PHONE}", f"Gebze Tel: {PHONE}"):
            out, _ = one(line)
            self.assertEqual(out, line.replace(PHONE, "[telefon]"), line)


class L2_TradeNameForms(unittest.TestCase):
    def test_legal_form_without_sector_word(self):
        for line, exp in (("Kaplo Ltd.Şti.", "[firma] Ltd.Şti."), ("KAPLO LTD.ŞTİ", "[firma] LTD.ŞTİ"),
                          ("Kaplo Nak. Ltd. Şti.", "[firma] Nak. Ltd. Şti."),
                          ("Kaplo Lojistik Hizmetleri Ltd. Şti.", "[firma] Lojistik Hizmetleri Ltd. Şti.")):
            out, _ = one(line)
            self.assertEqual(out, exp, line)

    def test_sector_forms_in_ad(self):
        for line, exp in (("Kaplo Nakliyattan", "[firma] Nakliyattan"), ("Kaplo Nakliyatın aracı", "[firma] Nakliyatın aracı"),
                          ("Kaplo Nakliyeci", "[firma] Nakliyeci"), ("Tavro Kestel Nakliyat", "[firma] Nakliyat"),
                          ("KAPLO NAKLİYATI", "[firma] NAKLİYATI")):
            out, _ = ad(line)
            self.assertEqual(out, exp, line)

    def test_participant_label_alone_stays_label(self):
        out, a = ad("Kestel Nakliyat")
        self.assertEqual(out, a.labels["Arvo Kestel"] + " Nakliyat")

    def test_one_sector_list(self):
        """Ticari ad ve alan adi ayni sektor listesini kullanir (nakliyeci ikisinde de)."""
        self.assertIn("nakliyeci", wa2md._SECTOR_W)
        self.assertTrue(set(wa2md._WEB_KEYS) <= {wa2md._key(w) for w in wa2md._SECTOR_W})


class L3_HonorificFirstWord(unittest.TestCase):
    def test_with_ad_signal(self):
        for line in ("ABLA NAKLİYAT", "USTA NAKLİYAT", "KERİMSAY NAKLİYAT"):
            out, _ = one(f"{line} {PHONE}")
            self.assertEqual(out, "[firma] NAKLİYAT [telefon]", line)
            out, _ = ad(line)
            self.assertEqual(out, "[firma] NAKLİYAT", line)

    def test_without_ad_signal(self):
        for line in ("ABLA NAKLİYAT", "USTA NAKLİYAT", "KERİMSAY NAKLİYAT"):     # 3. tur, ilke 4: varsayilan maskelenir
            out, _ = one(line)
            self.assertEqual(out, "[firma] NAKLİYAT", line)
        out, _ = one("Tamam abi Nakliyat işi")
        self.assertEqual(out, "Tamam abi Nakliyat işi")


class L4_SurnameAfterGivenName(unittest.TestCase):
    def test_masked_in_ad(self):
        for line, exp in (("KARAYAZ VELİTEPE NAKLİYAT ALİCAN TAŞVELEN", "[firma] NAKLİYAT {}"),
                          ("Karayaz Velitepe Nakliyat Alican Taşvelen", "[firma] Nakliyat {}"),
                          ("ALİCAN TAŞVELEN - Konya", "{} - Konya")):
            out, a = ad(line)
            self.assertEqual(out, exp.format(lab(out, a)), line)

    def test_not_surname(self):
        out, a = ad("ALİCAN NAKLİYAT")                        # sektor sozcugu soyad degil: ticari ad
        self.assertEqual(out, "[firma] NAKLİYAT")
        out, a = ad("ALİCAN KONYA")                           # ilan sozcugu soyad degil
        self.assertEqual(out, f"{lab(out, a)} KONYA")
        out, a = one("Alican Taşvelen geldi")                  # ilan imi yok: bilinmeyen soyad eslenmez
        self.assertEqual(out, f"{lab(out, a)} Taşvelen geldi")
        out, a = ad("Alican Taşvelen geldi")                   # soyad konumu degil (ardinda sozcuk)
        self.assertEqual(out, f"{lab(out, a)} Taşvelen geldi")


class L5_SignatureLine(unittest.TestCase):
    def test_signature_next_to_phone_line(self):
        out, a = run([("Ali Veli", f"YÜK VAR\n{PHONE}\n🪪 Aras Kerimsay"), ("Brin Tamsel", "Aras Kerimsay aradı mı")])
        l = lab(out[-2], a)                     # 4. tur S7: zayif imza tam obek olarak, buyuk harfli bicimiyle yayilir
        self.assertEqual(out[-4:], ["YÜK VAR", "[telefon]", f"🪪 {l}", f"{l} aradı mı"])

    def test_control_listed_surname(self):
        out, a = run([("Ali Veli", f"{PHONE}\n🪪 Aras Akdoğan")])
        self.assertEqual(out[-1], f"🪪 {lab(out[-1], a)}")

    def test_not_signature(self):
        out, a = run([("Ali Veli", f"YÜK VAR\n{PHONE}\nKonya Mersin\nTamam Abi\n🪪 Aras Kerimsay")])  # komsu degil
        self.assertEqual(out[-3:], ["Konya Mersin", "Tamam Abi", "🪪 Aras Kerimsay"])
        out, a = run([("Ali Veli", "Aras Kerimsay"), ("Brin Tamsel", PHONE)])                  # baska mesaj
        self.assertEqual(out[-2], "Aras Kerimsay")


class L6_Domains(unittest.TestCase):
    def test_masked(self):
        for line, exp in (("ORNEKFIRMANAKLİYAT.COM", "[firma].COM"), ("ornekfirmanakliyat.COM", "[firma].COM"),
                          ("nakliyat.ornekfirma.com.tr", "nakliyat.[firma].com.tr"),
                          ("www.ornekfirma.nakliyat.com", "www.[firma].nakliyat.com"),
                          ("HTTPS://WWW.ORNEKFIRMA-LOJISTIK.COM.TR", "HTTPS://WWW.[firma].COM.TR")):
            out, _ = one(line)
            self.assertEqual(out, exp, line)

    def test_generic_or_platform_kept(self):
        for line in ("transportation.com", "www.nakliyat.com", "🌐 www.ornekpazar.com", "ornekbulut.tr", "nakliye.app.example.com",
                     "ornek-lojistikbirligi.org.tr", "ORNEK-LOJISTIKBIRLIGI.ORG.TR"):
            out, _ = one(line)
            self.assertEqual(out, line)


class L7_Phones(unittest.TestCase):
    def test_masked(self):
        for line, exp in (("０５００－０００－００－００", "[telefon]"), ("0500,000,00,00", "[telefon]"),
                          ("0500_000_00_00", "[telefon]"), ("0500·000·00·00", "[telefon]"),
                          ("Tel0500 000 00 00", "Tel[telefon]"), ("ara05000000000", "ara[telefon]"),
                          ("0500−000−00−00", "[telefon]"), ("٠٥٠٠ ٠٠٠ ٠٠ ٠٠", "[telefon]"),
                          ("0049 151 0000 0000", "[telefon]"), ("+49 151 0000 0000", "[telefon]")):
            out, _ = one(line)
            self.assertEqual(out, exp, line)

    def test_numbers_kept(self):
        for line in (KEEP_LINE, "0,5000000000", "1,500,000 TL", "0,5 ton", "12_000 kg", "05_11_2026", "13,60 m",
                     "2.500.000,00 TL", "5,000,000,000 TL", "ref 0012345678", "0012 adet", "m² 120"):
            out, _ = one(line)
            self.assertEqual(out, line)


class L8_WhatsAppLinks(unittest.TestCase):
    def test_masked(self):
        cid = "0029VaXyZ0a1b2C3d4E5f6"
        for line, exp in ((f"web.whatsapp.com/channel/{cid}", "web.whatsapp.com/channel/[kullanıcı]"),
                          (f"https://web.whatsapp.com/channel/{cid}", "https://web.whatsapp.com/channel/[kullanıcı]"),
                          (f"https%3A%2F%2Fwhatsapp.com%2Fchannel%2F{cid}", "https%3A%2F%2Fwhatsapp.com%2Fchannel%2F[kullanıcı]"),
                          (f"l.php?u=https%3A%2F%2Fwww.whatsapp.com%2Fchannel%2F{cid}%3Fx",
                           "l.php?u=https%3A%2F%2Fwww.whatsapp.com%2Fchannel%2F[kullanıcı]%3Fx")):
            out, _ = one(line)
            self.assertEqual(out, exp, line)

    def test_kept(self):
        for line in ("https://web.whatsapp.com/", "https://faq.whatsapp.com/123"):
            out, _ = one(line)
            self.assertEqual(out, line)


class L9_UrlRest(unittest.TestCase):
    PEOPLE = PEOPLE + ("ornekvadi kara hat lojistik sanayi tic ve ltd sti",)

    def test_participant_host(self):
        out, a = one("https://www.ornekvadi.com/ornek-liste.php?id=70231&sayfa=2", people=self.PEOPLE)
        p = a.labels[self.PEOPLE[-1]]
        self.assertEqual(out, f"https://www.{p}.com/[yol]")
        out, a = one("bakın: ornekvadi.com.tr/ilan/5.", people=self.PEOPLE)
        self.assertEqual(out, f"bakın: {p}.com.tr/[yol].")

    def test_firm_host(self):
        out, _ = one("www.ornekfirmanakliyat.com.tr/ilan?id=5#x bakın")
        self.assertEqual(out, "www.[firma].com.tr/[yol] bakın")
        out, _ = one("www.ornekfirmanakliyat.com/")
        self.assertEqual(out, "www.[firma].com/")

    def test_other_links_kept(self):
        for line in ("https://github.com/example-org/proje/issues/12", "instagram.com/p/xyz", "https://docs.python.org/3/library/re.html"):
            out, _ = one(line)
            self.assertEqual(out, line)


class F1_SectorWordNeedsSecondSignal(unittest.TestCase):
    """3. tur, ilke 4: guclu sektor sozcugu (nakliyat, nakliye, lojistik...) ilan imi olmadan da ticari ad kurar ('Kaplo
    Nakliyat' -> '[firma] Nakliyat'); zayif tetikleyici (transport, kargo, şirketi) ilan imi ister; genel nitelemeler
    (durdurma listesi: Güvenilir, Proje) ayirt edici sozcuk degildir, ilanda da."""

    def test_unchanged_without_signal(self):
        for line in ("Elektrik Şirketi aradı", "Annem Kargo'dan aldı", "Güvenilir Nakliye Hizmeti", "Proje Lojistiği",
                     "HTTP Transport ayarı", "Deploy Pipeline Transport", "WhatsApp Web Transport"):
            out, _ = one(line)
            self.assertEqual(out, line)
        out, _ = one("Kaplo Nakliyat")
        self.assertEqual(out, "[firma] Nakliyat")

    def test_masked_with_signal(self):
        out, _ = one(f"Kaplo Nakliyat {PHONE}")
        self.assertEqual(out, "[firma] Nakliyat [telefon]")
        out, _ = ad("Güvenilir Nakliye Hizmeti")
        self.assertEqual(out, "Güvenilir Nakliye Hizmeti")
        out, a = run([("Ali Veli", "Kaplo Nakliyat\nİrtibat: Dorin Kaplo")])
        self.assertEqual(out[-2], "[firma] Nakliyat")


class F2_LabelJoin(unittest.TestCase):
    PEOPLE = PEOPLE + ("Plimm",)

    def test_ordinary_word_not_joined(self):
        out, a = one("dün Review Plimm yaptı", people=self.PEOPLE)
        self.assertEqual(out, f"dün Review {a.labels['Plimm']} yaptı")
        out, a = one("dün Plimm Review yaptı", people=self.PEOPLE)
        self.assertEqual(out, f"dün {a.labels['Plimm']} Review yaptı")

    def test_joined_in_ad(self):
        out, a = one(f"Xandor Plimm {PHONE}", people=self.PEOPLE)
        self.assertEqual(out, f"{a.labels['Plimm']} [telefon]")


class F3_RouteContext(unittest.TestCase):
    PEOPLE = PEOPLE + ("Veli Karasoy Bozova 2",)

    def check(self, line, exp):
        out, a = one(line, sender="Brin Tamsel", people=self.PEOPLE)
        self.assertEqual(out, exp.format(p=a.labels[self.PEOPLE[-1]]), line)

    def test_kept_in_route(self):
        for line in ("Şanlıurfa ➡️ Bozova", "Akçakale ➡️Bozova", "Bozova yüklemeli", "Bozova - Konya", "Bozova çıkışlı tır",
                     "Bozova'dan Mersin'e", "Konya'dan Bozova'ya"):
            self.check(line, line)

    def test_masked_otherwise(self):
        self.check("Bozova aradı", "{p} aradı")
        self.check("Veli Bozova'ya gitti", "{p}'ya gitti")
        self.check("Karasoy ➡️ Konya", "{p} ➡️ Konya")           # soyad bicimli parca guzergahta da maskelenir
        out, _ = one("Veli yüklemeli", sender="Brin Tamsel", people=self.PEOPLE)   # ilk ad parcasi (iki katilimcida: ?)
        self.assertEqual(out, "Kişi ? yüklemeli")


class F4_PlaceAndProduct(unittest.TestCase):
    """3. tur, ilke 2: sozluk adi + listede soyad main'de maskelenir; yer de olan ad + urun sozcugu istisnasi (2. tur F4)
    kaldirildi. 'CEYHAN KUM 🧱 VAR' main'deki gibi 'Kişi N 🧱 VAR' olur (kabul edilen asiri maskeleme)."""

    def test_place_name_and_product(self):
        out, a = one("CEYHAN KUM 🧱 VAR")
        self.assertEqual(out, f"{lab(out, a)} 🧱 VAR")
        out, a = one("Seyhan Kaya geldi")                       # listede soyad: ad-soyad olarak maskelenir
        self.assertEqual(out, f"{lab(out, a)} geldi")


class PinnedNonChanges(unittest.TestCase):
    """Bilerek degismeyenler: sektor sozcugu olmayan platform alan adlari, il + yuk, inceleme dosyasina giden sozcukler."""

    def test_kept(self):
        for line in ("🌐 www.ornekpazar.com", "ornekbulut.tr", "🔆ANTALYA ÇORAP 🔆", "Abacı'dan mısır", "⚖️ ALTUN TONAJ  / 2 ARAÇ"):
            out, _ = one(line)
            self.assertEqual(out, line)
        out, a = one("⚖️ ALTUN TONAJ  / 2 ARAÇ")
        self.assertIn(wa2md._key("Altun"), a.review)


class Performance(unittest.TestCase):
    """Karesel davranis paketi bozmali: alan adi kurali ve etiket katilimi uzun satirda dogrusal (bu turdan once 100k
    karakterde 11 s ve 1.3 s; 2. turda her biri 1 s'nin altinda)."""

    def test_long_lines_linear(self):
        out, a = run([("Ali Veli", "selam")], PEOPLE + ("Plimm",))
        for line in ("nakliyat" * 25000 + " a.example.com", "lojistik-" * 22000 + " a.example.com", "Plimm " + "Abc " * 100000,
                     "Tel: " + "Abc " * 50000, "Kişi 1 ve " * 20000 + "Nakliyat", "Kişi 1.com/x " * 15000):
            t = time.time()
            a.text(line)
            self.assertLess(time.time() - t, 10, line[:20])


if __name__ == "__main__":
    unittest.main()
