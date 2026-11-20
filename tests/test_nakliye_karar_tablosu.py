"""3. tur: karar tablosu. Uc inceleme turunun her vakasi bir satirdir: (sinif, katilimcilar, girdi mesajlari,
beklenen cikti satirlari). Sonraki bir degisiklik bu vakalardan birini yeniden acamasin diye tek tabloda toplanir.

Tum sohbetler, adlar, firma adlari, numaralar ve baglantilar uydurmadir (repodaki test adlari ve inceleme metinlerindeki
uydurma adlar). Telefonlar bariz sahtedir.

Beklenen ciktida: '{P:<ad>}' o katilimcinin etiketi; '{L1}', '{L2}' ... katilimci olmayan kisi etiketleri (ayni yer tutucu
ayni etiket, farkli yer tutucular farkli etiket). Girdi mesaji bir dize ise gonderen 'Ali Veli'dir; (gonderen, metin) da
verilebilir. Cok satirli mesaj tek dizede '\\n' ile yazilir; cikti her satiri ayri verir.

Ilkeler (3. tur): 1 sizinti birlestirmeyi durdurur, kuskuda maskelenir; 2 main'in maskeledigi hicbir sey acilmaz (tek
istisna: kanitli guzergahta yer listesindeki katilimci ad parcasi); 3 guclu iletisim kaniti sohbet geneli tek etiket, zayif
kanit yalniz o yerde ve siradan sozcuk testlerinden gecerse; 4 ticari ad varsayilan olarak maskelenir; 5 virgul/alt cizgi/
orta nokta yalniz telefon bicimli gruplamada ayractir, butun obekleri iki haneli dizi telefon degildir."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_nakliye_gruplari import PEOPLE, PHONE, run, setUpModule, tearDownModule  # noqa: E402,F401

HK = PEOPLE + ("Hasan Kaplo",)
BZ = PEOPLE + ("Veli Karasoy Bozova 2",)
VOC = PEOPLE + ("Velko Teker", "Tır Fenna", "Xandor Konya")
KT = PEOPLE + ("Kaplo Tavro",)
NB = ("Ali Veli", "Arvo Kestel", "Kaplo Tavro")          # 'Brin' hicbir listede degil

# (sinif, katilimcilar (None: varsayilan), girdi mesajlari, beklenen cikti satirlari)
ROWS = [
    # ---- N1 (2. inceleme): guzergah kurali katilimci soyadini aciyordu; ilke 2
    ("N1", HK, [f"Kaplo - Tel: {PHONE}"], ["{P:Hasan Kaplo} - Tel: [telefon]"]),
    ("N1", HK, ["Hasan - Kaplo"], ["{P:Hasan Kaplo} - {P:Hasan Kaplo}"]),
    ("N1", HK, ["Kaplo teslim etti"], ["{P:Hasan Kaplo} teslim etti"]),
    ("N1", HK, ["Kaplo çıkış yaptı"], ["{P:Hasan Kaplo} çıkış yaptı"]),
    ("N1", HK, ["Ankara'dan Kaplo'ya mal gönderdim"], ["Ankara'dan {P:Hasan Kaplo}'ya mal gönderdim"]),
    ("N1", HK, ["Şanlıurfa ➡️ Kaplo"], ["Şanlıurfa ➡️ {P:Hasan Kaplo}"]),        # ayni bicim, yer listesinde yok
    ("N1", HK, ["Kaplo yüklemeli"], ["{P:Hasan Kaplo} yüklemeli"]),
    # ---- F3 / bilinen gercek veri bicimi: yer listesindeki parca yalniz kanitli guzergahta kalir
    ("F3", BZ, [("Brin Tamsel", "Şanlıurfa ➡️ Bozova")], ["Şanlıurfa ➡️ Bozova"]),
    ("F3", BZ, [("Brin Tamsel", "Akçakale ➡️Bozova")], ["Akçakale ➡️Bozova"]),
    ("F3", BZ, [("Brin Tamsel", "Bozova yüklemeli")], ["Bozova yüklemeli"]),
    ("F3", BZ, [("Brin Tamsel", "Bozova - Konya")], ["Bozova - Konya"]),
    ("F3", BZ, [("Brin Tamsel", "Bozova'dan Mersin'e")], ["Bozova'dan Mersin'e"]),
    ("F3", BZ, [("Brin Tamsel", "Konya'dan Bozova'ya")], ["Konya'dan Bozova'ya"]),
    ("F3", BZ, [("Brin Tamsel", "Bozova aradı")], ["{P:Veli Karasoy Bozova 2} aradı"]),
    ("F3", BZ, [("Brin Tamsel", "Bozova teslim etti")], ["{P:Veli Karasoy Bozova 2} teslim etti"]),
    ("F3", BZ, [("Brin Tamsel", "Bozova - Tavro")], ["{P:Veli Karasoy Bozova 2} - Tavro"]),   # oteki uc yer degil
    ("F3", BZ, [("Brin Tamsel", f"Şanlıurfa ➡️ Bozova {PHONE}")], ["Şanlıurfa ➡️ {P:Veli Karasoy Bozova 2} [telefon]"]),
    ("F3", BZ, [("Brin Tamsel", "Bozova - Tel: 0500 000 00 00")], ["{P:Veli Karasoy Bozova 2} - Tel: [telefon]"]),
    ("F3", BZ, [("Brin Tamsel", "Karasoy ➡️ Konya")], ["{P:Veli Karasoy Bozova 2} ➡️ Konya"]),
    ("F3", BZ, [("Brin Tamsel", "Veli Bozova'ya gitti")], ["{P:Veli Karasoy Bozova 2}'ya gitti"]),
    # ---- ilke 2: katilimci adinin ilan sozcugu parcasi main gibi maskelenir; yer parcasi yalniz kanitli guzergahta kalir
    ("P2", VOC, ["10 teker, tır, altı teker fazla"], ["10 {P:Velko Teker}, {P:Tır Fenna}, altı {P:Velko Teker} fazla"]),
    ("P2", VOC, ["Konya çıkışlı kırkayak"], ["Konya çıkışlı kırkayak"]),
    ("P2", VOC, ["Konya aradı"], ["{P:Xandor Konya} aradı"]),
    # main bu iki satiri maskeler; ilke 2 acmayi yasaklar (degismemesi beklentisi bu ilkeyle celisir: belgeli sinir)
    ("P2", None, ["CEYHAN KUM 🧱 VAR"], ["{L1} 🧱 VAR"]),                       # main'deki gibi (2. tur F4 kalkti)
    ("P2", None, ["Aydın'dan Mersin'e"], ["{L1}'dan Mersin'e"]),                  # il de olan sozluk adi: main gibi
    ("P2", None, ["araç 34 ABC 123 26 ton"], ["araç [plaka] 26 ton"]),           # plaka main'deki gibi
    ("P2", None, [f"yükleme 08:30 TEL {PHONE}"], ["yükleme 08:30 TEL [telefon]"]),   # 0'li obek telefon basidir
    # ---- N3 (2. inceleme): baglamla bulunan ad baska satira tasinmiyordu; ilke 3 guclu kanit: sohbet geneli tek etiket
    ("N3", None, [f"İrtibat: Dorin Zelvo {PHONE}", ("Brin Tamsel", "Dorin Zelvo yükü aldı mı?")],
     ["İrtibat: {L1} [telefon]", "{L1} yükü aldı mı?"]),
    ("N3", None, [f"İrtibat: Dorin Zelvo {PHONE}\nDorin Zelvo bey yoksa Tavro'yu arayın"],
     ["İrtibat: {L1} [telefon]", "{L1} bey yoksa Tavro'yu arayın"]),
    # 4. tur S3b: hicbir parcasi ad sozlugunde olmayan ad yalniz tam obek olarak yayilir; 4. tur eki (Z2): hitaptan onceki tek
    # parca tam adin etiketini alir
    ("N3", None, [f"İrtibat: Dorin Zelvo {PHONE}", ("Brin Tamsel", "Zelvo bey aradı")], ["İrtibat: {L1} [telefon]", "{L1} bey aradı"]),
    ("N3", None, [f"{PHONE} Dorin Kaplo", ("Brin Tamsel", "Dorin Kaplo yarın yükler")], ["[telefon] {L1}", "{L1} yarın yükler"]),
    ("N3", None, [f"Tel: Alican Taşvelen {PHONE}", ("Brin Tamsel", "alican taşvelen geldi")],
     ["Tel: {L1} [telefon]", "{L1} geldi"]),
    ("N3", None, [f"İrtibat: Dorin Zelvo {PHONE}", f"İrtibat: Dorin Kaplo {PHONE}"],     # ayni ad, farkli kisi
     ["İrtibat: {L1} [telefon]", "İrtibat: {L2} [telefon]"]),
    # guclu ama siradan sozcuk (iyelik eki): yalniz o yerde; ayni bicimde gercek ad sohbet geneli
    ("N3", None, [f"İrtibat: Proje Masası {PHONE}", ("Brin Tamsel", "Proje Masası toplandı")],
     ["İrtibat: {L1} [telefon]", "Proje Masası toplandı"]),
    ("N3", None, [f"İrtibat: Proje Kaplo {PHONE}", ("Brin Tamsel", "Proje Kaplo toplandı")],
     ["İrtibat: {L1} [telefon]", "{L1} toplandı"]),
    # ---- N4 (2. inceleme): imza kurali siradan iki sozcuklu satiri maskeliyordu; ilke 3 zayif kanit + siradan sozcuk testi
    ("N4", None, [f"YÜK VAR\n{PHONE}\nSevgi Saygılarımla"], ["YÜK VAR", "[telefon]", "Sevgi Saygılarımla"]),
    ("N4", None, [f"{PHONE}\nUmut Ediyoruz", ("Brin Tamsel", "umut ediyoruz")], ["[telefon]", "Umut Ediyoruz", "umut ediyoruz"]),
    ("N4", None, [f"{PHONE}\nCan Dostlar"], ["[telefon]", "Can Dostlar"]),
    ("N4", None, [f"{PHONE}\nNur Ola"], ["[telefon]", "Nur Ola"]),
    ("N4", None, [f"{PHONE}\nUmut Kerimsay"], ["[telefon]", "{L1}"]),          # ayni bicim, gercek soyad: maskelenir
    ("N4", None, [f"YÜK VAR\n{PHONE}\n🪪 Aras Kerimsay", ("Brin Tamsel", "Aras Kerimsay aradı mı")],
     ["YÜK VAR", "[telefon]", "🪪 {L1}", "{L1} aradı mı"]),     # gercek veri bicimi; zayif imza: tam obek yayilir (4. tur S7)
    ("N4", None, [f"{PHONE}\n🪪 Aras Kerimsay"], ["[telefon]", "🪪 {L1}"]),        # en kisa bicim: telefon satiri + imza
    ("N4", None, [f"{PHONE}\n🪪 Aras Akdoğan", ("Brin Tamsel", "Aras Akdoğan aradı")],
     ["[telefon]", "🪪 {L1}", "{L1} aradı"]),                                    # listede soyad: guclu (main kurali)
    # ---- N5 (2. inceleme): ilan soyadi kurali fiili soyad sayiyordu; yalniz ad maskelenir
    ("N5", None, [f"Hasan Gelsin\n{PHONE}", ("Brin Tamsel", "hasan gelsin dedi patron")],
     ["{L1} Gelsin", "[telefon]", "{L1} gelsin dedi patron"]),
    ("N5", None, [f"Mehmet Yazıyor:\n{PHONE}"], ["{L1} Yazıyor:", "[telefon]"]),
    ("N5", None, [f"Hasan Aradı\n{PHONE}"], ["{L1} Aradı", "[telefon]"]),
    ("N5", None, [f"KARAYAZ VELİTEPE NAKLİYAT ALİCAN TAŞVELEN\n{PHONE}"], ["[firma] NAKLİYAT {L1}", "[telefon]"]),
    ("N5", None, [f"ALİCAN TAŞVELEN - Konya\n{PHONE}"], ["{L1} - Konya", "[telefon]"]),
    ("N5", None, [f"Hasan Kerimsay\n{PHONE}", ("Brin Tamsel", "Hasan Kerimsay geldi")],
     ["{L1}", "[telefon]", "{L1} geldi"]),                     # imza satiri (zayif): tam obek yayilir (4. tur S7)
    # ---- N8 ve 1. incelemeden acik kalan iletisim bicimleri
    ("N8", None, [f"İrtibat: hasan tavro {PHONE}"], ["İrtibat: {L1} [telefon]"]),
    ("N8", None, [f"İrtibat: hasan bey {PHONE}"], ["İrtibat: {L1} bey [telefon]"]),
    ("B", None, ["Tel (Ofis): Hasan Tavro"], ["Tel (Ofis): {L1}"]),
    ("B", None, ["İRTİBAT ⇒ HASAN TAVRO"], ["İRTİBAT ⇒ {L1}"]),
    ("B", None, ["HASAN TAVRO İRTİBAT"], ["{L1} İRTİBAT"]),
    # ayracsiz iletisim sozcugu + mesajda ilan imi (telefon alt satirda): zayif kanit, yalniz o yerde; ilan imi yoksa sinir
    ("B", None, [f"DORİN ZELVO İRTİBAT\n{PHONE}", ("Brin Tamsel", "Dorin Zelvo geldi")], ["{L1} İRTİBAT", "[telefon]", "Dorin Zelvo geldi"]),
    ("B", None, [f"irtibat Dorin Zelvo\n{PHONE}", "irtibat Dorin Zelvo"], ["irtibat {L1}", "[telefon]", "irtibat Dorin Zelvo"]),
    ("B", None, [f"İletişim Kurun Lütfen\n{PHONE}"], ["İletişim Kurun Lütfen", "[telefon]"]),     # tek sozcuk: listede ad degil
    ("B", None, [f"Tavro Tel: {PHONE}"], ["{L1} Tel: [telefon]"]),
    ("B", None, [f"Gebze Tel: {PHONE}", f"Diğer Tel: {PHONE}", f"Ofis Tel: {PHONE}"],     # yer ve dolgu: ad degil
     ["Gebze Tel: [telefon]", "Diğer Tel: [telefon]", "Ofis Tel: [telefon]"]),
    ("B", None, ["Yetkili Adı Soyadı: Hasan Tavro"], ["Yetkili Adı Soyadı: {L1}"]),
    ("B", None, [f"İrtibat: Ali Bozova {PHONE}"], ["İrtibat: {L1} [telefon]"]),    # yer adi soyad konumunda: maskelenir
    ("B", None, ["WhatsApp Web açılmıyor", "Yetkili Servis", f"Hafta İçi Arayınız {PHONE}"],
     ["WhatsApp Web açılmıyor", "Yetkili Servis", "Hafta İçi Arayınız [telefon]"]),
    ("B", None, [f"Tavro {PHONE}"], ["{L1} [telefon]"]),
    ("B", None, [f"TAVRO GSM {PHONE}"], ["{L1} GSM [telefon]"]),
    ("B", None, [f"Gebze {PHONE}", f"ACİL YÜK {PHONE}", f"Sadece {PHONE}"],
     ["Gebze [telefon]", "ACİL YÜK [telefon]", "Sadece [telefon]"]),
    ("B", HK, [f"İrtibat: Hasan Tavro {PHONE}"], ["İrtibat: {L1} [telefon]"]),      # katilimci adi + baska soyad
    ("C", PEOPLE + ("Plimm",), [f"Xandor Plimm {PHONE}"], ["{P:Plimm} [telefon]"]),
    # ---- N2 (2. inceleme): ilan imi olmayan ticari ad aciktaydi; ilke 4 varsayilan maskeleme
    ("N2", None, ["Kaplo Nakliyat'a yük verdim"], ["[firma] Nakliyat'a yük verdim"]),
    ("N2", None, ["Tavro Nakliyat ödemeyi yapmadı, dikkat edin"], ["[firma] Nakliyat ödemeyi yapmadı, dikkat edin"]),
    ("N2", None, ["Kestel ve Oğulları Nakliyat"], ["[firma] Nakliyat"]),          # soyad katilimci parcasi da olsa
    ("N2", ("Ali Veli", "Brin Tamsel"), ["Kestel ve Oğulları Nakliyat"], ["[firma] Nakliyat"]),
    ("N2", None, ["Kestel Nakliyat"], ["{P:Arvo Kestel} Nakliyat"]),               # yalniz etiket: etiket kalir
    ("N2", None, ["KERİMSAY NAKLİYAT"], ["[firma] NAKLİYAT"]),
    # 4. tur S9: iyelik ekli sektor sozcugu ilan imi ve hukuki bicim yoksa ad tamlamasidir (sinir; ilan iminde maskelenir)
    ("N2", None, ["Gebze Kaplo Lojistiği", f"Gebze Kaplo Lojistiği {PHONE}"], ["Gebze [firma] Lojistiği", "Gebze [firma] Lojistiği [telefon]"]),
    ("N2", None, ["Kaplo Taşımacılık A.Ş. yük arıyor"], ["[firma] Taşımacılık A.Ş. yük arıyor"]),
    ("D", None, [f"ABLA NAKLİYAT\n{PHONE}", f"USTA NAKLİYAT {PHONE}"],             # gercek veri bicimi
     ["[firma] NAKLİYAT", "[telefon]", "[firma] NAKLİYAT [telefon]"]),
    ("D", None, ["KARAYAZ VELİTEPE NAKLİYAT ALİCAN TAŞVELEN"], ["[firma] NAKLİYAT {L1}"]),   # satirda sektor sozcugu: L4 baglami
    ("D", None, ["Dün Hasan Kerimsay geldi"], ["Dün {L1} Kerimsay geldi"]),       # baglam yok: bilinmeyen soyad kalir (sinir)
    ("D", PEOPLE + ("Kaplo Lojistik",), ["Tavro Lojistik aradı"], ["[firma] {P:Kaplo Lojistik} aradı"]),   # sektor parcali katilimci
    # ---- N7: tireli ve kucuk harfli hukuki bicimli ad tek maske
    ("N7", None, ["Kaplo-Tavro Nakliyat Ltd. Şti."], ["[firma] Nakliyat Ltd. Şti."]),
    ("N7", None, ["kaplo nakliyat ltd şti"], ["[firma] nakliyat ltd şti"]),
    ("N7", None, ["kaplo-tavro lojistik a.ş."], ["[firma] lojistik a.ş."]),
    ("N7", None, ["www.ornekfirma-nakliyat.com.tr"], ["www.[firma].com.tr"]),           # alan adi kurali, tire firma degil
    # ---- ilke 4 dislamalari: durdurma listesi (4a), yer listesi (4b), hitap obegi (4c); her biri ayni bicimde gercek ad maskelenir
    ("D4a", None, [f"Şehirler Arası Nakliyat\n{PHONE}"], ["Şehirler Arası Nakliyat", "[telefon]"]),
    ("D4a", None, [f"Uygun Fiyatlı Taşımacılık\n{PHONE}"], ["Uygun Fiyatlı Taşımacılık", "[telefon]"]),
    ("D4a", None, ["Güvenilir Nakliye Hizmeti", "Proje Lojistiği", f"Güvenilir Nakliye Hizmeti {PHONE}"],
     ["Güvenilir Nakliye Hizmeti", "Proje Lojistiği", "Güvenilir Nakliye Hizmeti [telefon]"]),
    ("D4a", None, ["Kerimsay Hızlı Nakliyat", "Uygun Kerimsay Taşımacılık"], ["[firma] Nakliyat", "Uygun [firma] Taşımacılık"]),
    ("D4a", None, ["Ürün Lojistiği", "Satın Alma ve Lojistik ekibi", "Dün Kaplo Nakliyat aradı"],
     ["Ürün Lojistiği", "Satın Alma ve Lojistik ekibi", "Dün [firma] Nakliyat aradı"]),
    ("D4a", None, ["Kestel ve Oğulları Nakliyat"], ["[firma] Nakliyat"]),      # yer adi + aile zinciri: aile adi
    ("D4b", None, ["Konya Nakliyat", "ADANA NAKLİYAT", "Bozova Nakliyat"], ["Konya Nakliyat", "ADANA NAKLİYAT", "Bozova Nakliyat"]),
    ("D4b", None, ["Bozkurt Nakliyat", "Konya Kaplo Nakliyat"], ["[firma] Nakliyat", "Konya [firma] Nakliyat"]),   # ilce ama soyad
    ("D4b", None, ["Ali Bozova Nakliyat", "Kaplo Konya Lojistik"], ["[firma] Nakliyat", "[firma] Lojistik"]),  # addan sonra yer: soyad konumu
    # 4. tur S5: tekil iyelik ekli hitap ('Hocam') guclu sektor sozcugunun onunde firma adidir; cogul bicim hitap obegi kalir
    ("D4c", None, [f"Değerli Abilerim Nakliye\n{PHONE}", "Hocam Nakliyat sordu"],
     ["Değerli Abilerim Nakliye", "[telefon]", "[firma] Nakliyat sordu"]),
    ("D4c", None, ["Abla Nakliyat"], ["[firma] Nakliyat"]),                        # yalin hitap firma adi olabilir
    # zayif tetikleyiciler ilan imi ister; siradan cumleler degismez
    ("D", None, ["Elektrik Şirketi aradı", "Annem Kargo'dan aldı", "HTTP Transport ayarı", "Deploy Pipeline Transport"],
     ["Elektrik Şirketi aradı", "Annem Kargo'dan aldı", "HTTP Transport ayarı", "Deploy Pipeline Transport"]),
    ("D", None, [f"Kaplo Kargo'ya sor {PHONE}", f"Kaplo Transport {PHONE}"], ["[firma] Kargo'ya sor [telefon]", "[firma] Transport [telefon]"]),
    ("D", None, ["evden eve nakliyat", "yük nakliye fiyatı", "Tır Nakliye", "Uygun Nakliye"],
     ["evden eve nakliyat", "yük nakliye fiyatı", "Tır Nakliye", "Uygun Nakliye"]),
    # ---- N6 (ilke 5): virgul/alt cizgi/orta nokta yalniz telefon bicimli gruplamada; iki haneli obekler telefon degil
    ("N6", None, ["Yükleme 05,06,07,08,09 Kasım", "Saatler 00.30, 01.30, 02.30", "05,10,15,20,25 ton", "Gün 05-06-07-08-09"],
     ["Yükleme 05,06,07,08,09 Kasım", "Saatler 00.30, 01.30, 02.30", "05,10,15,20,25 ton", "Gün 05-06-07-08-09"]),
    ("N6", None, ["05,000,000,000 TL", "1,500,000 TL", "05 06 07 Kasım"], ["05,000,000,000 TL", "1,500,000 TL", "05 06 07 Kasım"]),
    ("N6", None, ["0500,000,00,00", "0500_000_00_00", "0500·000·00·00", "0500-00-0000"],    # ayni ayraclarla gercek numara
     ["[telefon]", "[telefon]", "[telefon]", "[telefon]"]),
    # ---- A (1. incelemeden acik): sozcuge yapisik oneksiz numara, genis ayracli ve tus kapakli numara (sifir genislikli
    # karakterli satirlar 6. turda ZM/ZT/ZK siniflarinda)
    ("A", None, ["TEL500 000 00 00", "GSM5000000000", "Tel0500 000 00 00"], ["TEL[telefon]", "GSM[telefon]", "Tel[telefon]"]),
    ("A", None, [f"Hasan Tavro 0500  -  000  -  00  -  00", ("Brin Tamsel", "Hasan Tavro geldi")],
     ["{L1} [telefon]", "{L1} geldi"]),                                           # genis ayracli numara da guclu kanit
    ("A", None, ["\u0130rtibat: Hasan Tavro 0\ufe0f\u20e35\ufe0f\u20e30\ufe0f\u20e30\ufe0f\u20e3 - 0\ufe0f\u20e30\ufe0f\u20e30\ufe0f\u20e3"
                 " - 0\ufe0f\u20e30\ufe0f\u20e3 - 0\ufe0f\u20e30\ufe0f\u20e3"], ["\u0130rtibat: {L1} [telefon]"]),   # tus kapakli
    # ---- F / L9: alan adi ve yol
    ("F", None, ["ornekfirma.panel.nakliyat.com"], ["[firma].panel.nakliyat.com"]),
    ("F", None, ["https://ornekfirmanakliyat.com/a(b)", "(bkz. https://ornekfirmanakliyat.com/ilan/5)"],
     ["https://[firma].com/[yol]", "(bkz. https://[firma].com/[yol])"]),
    ("F", None, ["https://www.ornek-lojistikhaber.com/haber/123"], ["https://www.[firma].com/[yol]"]),   # haber sitesi: kabul (sinir)
    ("F", None, ["www.nakliyat.com", "nakliye.app.example.com", "https://github.com/example-org/nakliye-app/issues/12"],
     ["www.nakliyat.com", "nakliye.app.example.com", "https://github.com/example-org/nakliye-app/issues/12"]),
    ("F", PEOPLE + ("ornekvadi kara hat lojistik sanayi tic ve ltd sti",),           # gercek veri bicimi
     ["https://www.ornekvadi.com/ornek-liste.php?id=70231&sayfa=2"],
     ["https://www.{P:ornekvadi kara hat lojistik sanayi tic ve ltd sti}.com/[yol]"]),
    ("N1", HK, ["Kaplo - Tel: 0500 000 11 11"], ["{P:Hasan Kaplo} - Tel: [telefon]"]),
    # ---- E: onceki incelemelerin kapali bulgulari (kapali kalmali)
    ("E", None, ["İRTİBAT İÇİN: Dorin Kaplo"], ["İRTİBAT İÇİN: {L1}"]),
    ("E", None, ["Telefon Numarası", "Cep Telefonu Faturası", "İletişim Bilgileri", f"Tel No: {PHONE}"],
     ["Telefon Numarası", "Cep Telefonu Faturası", "İletişim Bilgileri", "Tel No: [telefon]"]),
    ("E", None, [f"Dorin Kaplo Tel: {PHONE}"], ["{L1} Tel: [telefon]"]),
    ("E", None, ["Kaplo Ltd.Şti.", "Kaplo Nak. Ltd. Şti.", "Kaplo Nakliyattan", "Kaplo Nakliyeci"],
     ["[firma] Ltd.Şti.", "[firma] Nak. Ltd. Şti.", "[firma] Nakliyattan", "[firma] Nakliyeci"]),
    ("E", None, ["ORNEKFIRMANAKLİYAT.COM", f"ORNEKFIRMANAKLİYAT.COM {PHONE}"], ["[firma].COM", "[firma].COM [telefon]"]),
    ("E", None, ["０５００－０００－００－００"], ["[telefon]"]),
    ("E", None, ["web.whatsapp.com/channel/0029VaXyZ12AbCdEfGhIjK3l", "https://web.whatsapp.com/channel/0029VaXyZ12AbCdEfGhIjK3l"],
     ["web.whatsapp.com/channel/[kullanıcı]", "https://web.whatsapp.com/channel/[kullanıcı]"]),
    # ---- NT: degismemesi beklenen siradan bicimler (ilan imi olmadan ve ilan iminde)
    ("NT", None, ["Şehirler Arası Nakliyat", "Uygun Fiyatlı Taşımacılık", "Değerli Abilerim Nakliye"],
     ["Şehirler Arası Nakliyat", "Uygun Fiyatlı Taşımacılık", "Değerli Abilerim Nakliye"]),
    ("NT", None, ["🌐 www.ornekpazar.com", "ornekbulut.tr", "🔆ANTALYA ÇORAP 🔆"], ["🌐 www.ornekpazar.com", "ornekbulut.tr", "🔆ANTALYA ÇORAP 🔆"]),
    ("NT", None, [f"🌐 www.ornekpazar.com\nornekbulut.tr\n🔆ANTALYA ÇORAP 🔆\n{PHONE}"],
     ["🌐 www.ornekpazar.com", "ornekbulut.tr", "🔆ANTALYA ÇORAP 🔆", "[telefon]"]),
    # ==== 4. tur: 3. incelemenin bulgulari (B2, S3-S11; B1 sifir genislikli karakter satirlari 6. turda ZM/ZK'da)
    # ---- B2: sektor sozcugune tireyle bagli ad (main'de de aciktaydi)
    ("B2", None, ["Tavro-Nakliyat ödeme yaptı", "VELMOR-LOJİSTİK LTD. ŞTİ.", "Velmor-Lojistik A.Ş. teklif verdi",
                  f"Velmor-Nakliyat {PHONE}", "Velmor\u2010Nakliyat ödeme", "Velmor\u2011Lojistik ödeme"],
     ["[firma]-Nakliyat ödeme yaptı", "[firma]-LOJİSTİK LTD. ŞTİ.", "[firma]-Lojistik A.Ş. teklif verdi", "[firma]-Nakliyat [telefon]",
      "[firma]\u2010Nakliyat ödeme", "[firma]\u2011Lojistik ödeme"]),
    ("B2", None, ["www.ornekfirma-nakliyat.com.tr", "Konya-Nakliyat geldi", "Adana - Nakliyat", "Kaplo Tavro-Nakliyat geldi"],
     ["www.[firma].com.tr", "Konya-Nakliyat geldi", "Adana - Nakliyat", "[firma]-Nakliyat geldi"]),
    # ---- S3: iletisim adinin yayilmasi: parcalarindan biri ad sozlugundeyse parcalari da (sozlukte olmayan parca yalniz buyuk
    # harfli bicimiyle); hicbiri degilse yalniz tam obek, buyuk harfli bicimiyle; birim adi kisi degil
    ("S3", None, [f"Tel: Sıcak Çorba {PHONE}", "sıcak çorba içtik", "Sıcak hava var", "çorba soğudu"],
     ["Tel: {L1} [telefon]", "sıcak çorba içtik", "Sıcak hava var", "çorba soğudu"]),
    ("S3", None, [f"İrtibat: Mavi Kapak {PHONE}", "Mavi araba geldi", ("Brin Tamsel", "Mavi Kapak aradı")],
     ["İrtibat: {L1} [telefon]", "Mavi araba geldi", "{L1} aradı"]),
    ("S3", None, [f"Kapıda Ödeme irtibat {PHONE}", "kapıda ödeme olur mu"], ["{L1} irtibat [telefon]", "kapıda ödeme olur mu"]),
    ("S3", None, [f"İrtibat: Muhasebe Birimi {PHONE}", "birimi değişti", f"Tel: Satış Departmanı {PHONE}", "Satış Departmanı aradı",
                  f"İrtibat: Gündüz Ekibi {PHONE}", "Gündüz Ekibi geldi"],
     ["İrtibat: Muhasebe Birimi [telefon]", "birimi değişti", "Tel: Satış Departmanı [telefon]", "Satış Departmanı aradı",
      "İrtibat: Gündüz Ekibi [telefon]", "Gündüz Ekibi geldi"]),
    ("S3", None, [f"İrtibat: Dorin Zelvo {PHONE}", ("Brin Tamsel", "Dorin Zelvo yükü aldı mı?"), "DORİN ZELVO geldi"],
     ["İrtibat: {L1} [telefon]", "{L1} yükü aldı mı?", "{L1} geldi"]),
    ("S3", None, [f"İrtibat: Nurettin Göksoylu {PHONE}", ("Brin Tamsel", "Göksoylu bey aradı"), "Nurettin geldi"],
     ["İrtibat: {L1} [telefon]", "{L1} bey aradı", "{L1} geldi"]),
    ("S3", None, [f"irtibat: tahsin kıvrak {PHONE}", ("Brin Tamsel", "Tahsin Kıvrak geldi"), "tahsin kıvrak geldi", "Kıvrak aradı"],
     ["irtibat: {L1} [telefon]", "{L1} geldi", "{L1} geldi", "{L1} aradı"]),
    # ---- S7: zayif kanitli imza tam obek olarak, yalniz buyuk harfli bicimiyle sohbet geneli; tek parcalari yayilmaz
    ("S7", None, [f"YÜK VAR\n{PHONE}\n🪪 Aras Kerimsay", ("Brin Tamsel", "Aras Kerimsay aradı mı"), "Kerimsay geldi"],
     ["YÜK VAR", "[telefon]", "🪪 {L1}", "{L1} aradı mı", "Kerimsay geldi"]),
    ("S7", None, [f"{PHONE}\nDeniz Velmor", ("Brin Tamsel", "Deniz Velmor aradı"), "DENİZ VELMOR geldi", "Velmor geldi",
                  "deniz kenarı"],
     ["[telefon]", "{L1}", "{L1} aradı", "{L1} geldi", "Velmor geldi", "deniz kenarı"]),
    ("S7", None, [f"{PHONE}\nUmut Kasdan", ("Brin Tamsel", "Umut Kasdan aradı"), "umut ediyoruz", "Kasdan geldi"],
     ["[telefon]", "{L1}", "{L1} aradı", "umut ediyoruz", "Kasdan geldi"]),
    # ayni obegi ad kurali (main: soyad eki) da buluyorsa onun karari kazanir: her bicimiyle yayilir
    ("S7", None, [f"{PHONE}\n🪪 Aras Velmoroğlu", ("Brin Tamsel", "aras velmoroğlu aradı")], ["[telefon]", "🪪 {L1}", "{L1} aradı"]),
    # ---- S6: telefonun onundeki iletisim kanali sozcugu (yanlis yazimlari da) alan etiketidir, ad degil
    ("S6", None, ["Vatsap:0500 000 00 00", "Watsap: 0500 000 00 00", "Whatsap 0500 000 00 00", "Wp: 0500 000 00 00",
                  "Wtsp 0500 000 00 00", "Telegram: 0500 000 00 00", "Tlf 0500 000 00 00", "Gsm: 0500 000 00 00",
                  "Cep 0500 000 00 00", "Mobil: 0500 000 00 00", "Sabit: 0500 000 00 00", "Ofis 0500 000 00 00",
                  "Büro: 0500 000 00 00", "Faks: 0500 000 00 00", "Dahili 0500 000 00 00", "Hat: 0500 000 00 00",
                  "Numara: 0500 000 00 00"],
     ["Vatsap:[telefon]", "Watsap: [telefon]", "Whatsap [telefon]", "Wp: [telefon]", "Wtsp [telefon]", "Telegram: [telefon]",
      "Tlf [telefon]", "Gsm: [telefon]", "Cep [telefon]", "Mobil: [telefon]", "Sabit: [telefon]", "Ofis [telefon]",
      "Büro: [telefon]", "Faks: [telefon]", "Dahili [telefon]", "Hat: [telefon]", "Numara: [telefon]"]),
    ("S6", None, [f"Tavro Tel: {PHONE}", f"Hasan: {PHONE}", f"Vatsap: Dorin Zelvo {PHONE}"],
     ["{L1} Tel: [telefon]", "{L2}: [telefon]", "Vatsap: {L3} [telefon]"]),
    # ---- S11: sozluk adinin ardindaki siradan sozcuk (fiil) soyad degildir: yalniz ad maskelenir
    ("S11", None, [f"Mehmet Bekliyor {PHONE}", f"İrtibat: Hasan Gelecek {PHONE}", f"İrtibat: Proje Masası {PHONE}"],
     ["{L1} Bekliyor [telefon]", "İrtibat: {L2} Gelecek [telefon]", "İrtibat: {L3} [telefon]"]),
    # ---- S5: tekil iyelik ekli hitap + guclu sektor sozcugu firma adidir; cogul ya da hitap sifatli bicim hitap obegidir
    ("S5", None, ["DAYIM NAKLİYAT", "USTAM NAKLİYAT", f"Dayım Nakliyat {PHONE}", "Değerli Abilerim Nakliye fiyatları düştü",
                  "Değerli Dayım Nakliye fiyatları düştü"],
     ["[firma] NAKLİYAT", "[firma] NAKLİYAT", "[firma] Nakliyat [telefon]", "Değerli Abilerim Nakliye fiyatları düştü",
      "Değerli Dayım Nakliye fiyatları düştü"]),
    # ---- S4: hukuki bicim varken durdurma listesinin nitelemeleri ve yer adlari ayirt edici sozcuktur
    ("S4", None, ["Ekspres Lojistik A.Ş.", "Global Taşımacılık Ltd. Şti.", "Kurumsal Nakliyat San. Tic. Ltd. Şti.",
                  "Konya Lojistik A.Ş."],
     ["[firma] Lojistik A.Ş.", "[firma] Taşımacılık Ltd. Şti.", "[firma] Nakliyat San. Tic. Ltd. Şti.", "[firma] Lojistik A.Ş."]),
    ("S4", None, ["Dün Ekspres Lojistik A.Ş. aradı", "Ekspres Lojistik geldi", "Konya Lojistik geldi"],
     ["Dün [firma] Lojistik A.Ş. aradı", "Ekspres Lojistik geldi", "Konya Lojistik geldi"]),
    # ---- S9: genel niteleme (durdurma listesi) ve zayif alan adi ticari ad degil; 5. tur: iyelik/birim dislamasi kalkti (T5MB3)
    ("S9", None, ["Festival Lojistiği", "Kermes Nakliyesi", "Mahalle Nakliyecisi", "transport.example.com"],
     ["Festival Lojistiği", "Kermes Nakliyesi", "Mahalle Nakliyecisi", "transport.example.com"]),
    ("S9", None, ["Kaplo Nakliyat'a yük verdim", "Tavro Nakliyat ödemeyi yapmadı, dikkat edin", "Kestel ve Oğulları Nakliyat",
                  f"Tavro Lojistiği {PHONE}", "Kaplo Lojistiği Ltd. Şti.", "Kaplo Nakliyatı aradı", f"ornekfirmatransport.com {PHONE}"],
     ["[firma] Nakliyat'a yük verdim", "[firma] Nakliyat ödemeyi yapmadı, dikkat edin", "[firma] Nakliyat",
      "[firma] Lojistiği [telefon]", "[firma] Lojistiği Ltd. Şti.", "[firma] Nakliyatı aradı", "[firma].com [telefon]"]),
    # ---- S8: yukleme sozcugu yalniz kisinin ozne olamayacagi bicimde guzergah kaniti; 'indirme/yükleme yaptı' kisidir
    ("S8", PEOPLE + ("Selim Tarsus",), ["Tarsus indirme yaptı", "Tarsus yükleme yaptı", "Tarsus yüklemeli", "Tarsus çıkışlı",
                                        "Adana - Tarsus"],
     ["{P:Selim Tarsus} indirme yaptı", "{P:Selim Tarsus} yükleme yaptı", "Tarsus yüklemeli", "Tarsus çıkışlı", "Adana - Tarsus"]),
    # ---- S10: telefon bicimleri (main'de de aciktaydi); ilke 5 korumalari degismez
    ("S10", None, ["(0500)  -  000  -  00  -  00", "0500 ... 000 ... 00 ... 00", "0850 000 00 00", "0800 000 00 00",
                   "Tel: 0850 000 00 00"],
     ["[telefon]", "[telefon]", "[telefon]", "[telefon]", "Tel: [telefon]"]),
    ("S10", None, ["15,11,2026 08,30", "15_11 16_11", "05 06 07 08 09 10 11", "45.000 TL", "26 ton", "15.11.2026", "08:30",
                   "Saat 08 ... 09 ... 10", "0,850 TL", "08 11 2026 tarihli"],
     ["15,11,2026 08,30", "15_11 16_11", "05 06 07 08 09 10 11", "45.000 TL", "26 ton", "15.11.2026", "08:30",
      "Saat 08 ... 09 ... 10", "0,850 TL", "08 11 2026 tarihli"]),
    # ==== 4. tur eki
    # ---- Z2: hicbir parcasi ad sozlugunde olmayan iletisim adinin tek parcasi hitaptan once / Sayın'dan sonra tam adin etiketi
    ("Z2", None, [f"İrtibat: Dorin Zelvo {PHONE}", ("Brin Tamsel", "Zelvo bey aradı"), ("Brin Tamsel", "Dorin hanım yazdı"),
                  ("Brin Tamsel", "Zelvo usta geldi"), ("Brin Tamsel", "Sayın Zelvo")],
     ["İrtibat: {L1} [telefon]", "{L1} bey aradı", "{L1} hanım yazdı", "{L1} usta geldi", "Sayın {L1}"]),
    ("Z2", None, [("Brin Tamsel", "Zelvo abi aradı"), f"İrtibat: Dorin Zelvo {PHONE}"], ["{L1} abi aradı", "İrtibat: {L1} [telefon]"]),
    ("Z2", None, [f"İrtibat: Dorin Zelvo {PHONE}", ("Brin Tamsel", "Zelvo geldi")], ["İrtibat: {L1} [telefon]", "Zelvo geldi"]),  # S3b
    ("Z2", None, [f"İrtibat: Dorin Zelvo {PHONE}", f"İrtibat: Tarvo Zelvo {PHONE}", ("Brin Tamsel", "Zelvo bey aradı")],
     ["İrtibat: {L1} [telefon]", "İrtibat: {L2} [telefon]", "Kişi ? bey aradı"]),     # iki adda ortak parca: notr etiket
    ("Z2", None, ["Tel: Sıcak Çorba 0500 000 11 22", ("Brin Tamsel", "sıcak çorba içtik"), ("Brin Tamsel", "Sıcak hava var"),
                  ("Brin Tamsel", "çorba soğudu")], ["Tel: {L1} [telefon]", "sıcak çorba içtik", "Sıcak hava var", "çorba soğudu"]),
    ("Z2", None, ["Zelvo bey aradı"], ["Zelvo bey aradı"]),               # ogrenilmis ad yok: main gibi (satir basi supheli)
    ("Z2", None, ["dün Zelvo bey aradı"], ["dün {L1} bey aradı"]),        # main gibi (cumle ortasi hitap)
    # ==== 5. tur (T5: dorduncu bagimsiz inceleme)
    # ---- T5MB3: iyelik ekli sektor sozcugu ticari ad kurar; tek dislama durdurma listesi (genel niteleme)
    ("T5MB3", None, ["Kaplo Lojistiği ödeme yapmadı", "Tavro Nakliyesi geldi mi", "Kaplo Nakliyecisi aradı", "Festival Lojistiği",
                     "Kermes Nakliyesi", "Mahalle Nakliyecisi", "Gebze Kaplo Lojistiği", "Kaplo Lojistik ekibi geldi"],
     ["[firma] Lojistiği ödeme yapmadı", "[firma] Nakliyesi geldi mi", "[firma] Nakliyecisi aradı", "Festival Lojistiği",
      "Kermes Nakliyesi", "Mahalle Nakliyecisi", "Gebze [firma] Lojistiği", "[firma] Lojistik ekibi geldi"]),
    # belgeli sinir (fazla maske): birim sozcugu oncesindeki genel sozcuk da firma sayilir
    ("T5MB3", None, ["Yazılım Lojistik ekibi", "Gönüllü Lojistik ekibi"], ["[firma] Lojistik ekibi", "[firma] Lojistik ekibi"]),
    # ---- T5SF1: ad ile sektor sozcugu arasindaki her tire bicimi (telefon ayraciyla ayni sinif)
    ("T5SF1", None, ["KAPLO\u2013LOJİSTİK LTD. ŞTİ.", f"Kaplo\u2212Nakliyat {PHONE}", "Kaplo\u2012Nakliyat", "Kaplo\u2014Nakliyat",
                     "Kaplo\uff0dNakliyat", "Kaplo\ufe63Nakliyat", "Kaplo-Nakliyat"],
     ["[firma]\u2013LOJİSTİK LTD. ŞTİ.", "[firma]\u2212Nakliyat [telefon]", "[firma]\u2012Nakliyat", "[firma]\u2014Nakliyat",
      "[firma]\uff0dNakliyat", "[firma]\ufe63Nakliyat", "[firma]-Nakliyat"]),
    ("T5SF1", None, ["Konya\u2013Nakliyat", "ADANA \u2013 MERSİN"], ["Konya\u2013Nakliyat", "ADANA \u2013 MERSİN"]),
    # ---- T5SF2: tekil iyelik ekli hitap + kucuk harfli sektor sozcugu ilan imi ister; buyuk harfli sektor sozcugu istemez
    ("T5SF2", None, ["Dayım nakliyat işine girdi", "Hocam lojistik dersi veriyor", "DAYIM NAKLİYAT", "USTAM NAKLİYAT",
                     f"Dayım Nakliyat {PHONE}", "Hocam Nakliyat sordu"],
     ["Dayım nakliyat işine girdi", "Hocam lojistik dersi veriyor", "[firma] NAKLİYAT", "[firma] NAKLİYAT",
      "[firma] Nakliyat [telefon]", "[firma] Nakliyat sordu"]),
    # ---- T5N1: iki ogrenilmis adda ortak parca notr etiket alir
    ("T5N1", None, [f"Tel: Hasan Kaplo {PHONE}", "Tel: Hüseyin Kaplo 0500 000 00 01", "bugün Kaplo bey geldi"],
     ["Tel: {L1} [telefon]", "Tel: {L2} [telefon]", "bugün Kişi ? bey geldi"]),
    # ---- T5N2: sonra yeniden gecen (zayif kanitli) imza tek etiket
    ("T5N2", None, [f"Selamlar\nKemal Tunç\n{PHONE}", "Kemal Tunç yine geldi"], ["Selamlar", "{L1}", "[telefon]", "{L1} yine geldi"]),
    # ---- T5N4: belgeli sinir: genel posta ana makinesinin alt alani (arac genel ana makine listesi tutmaz)
    ("T5N4", None, ["nakliyat.gmail.com"], ["nakliyat.[firma].com"]),
    # ---- T5N5: ayraclar arasinda bosluk olan telefon (S10 korumalari degismez)
    ("T5N5", None, ["0500 - - 000 00 00", "0500 . . 000 00 00", "Tel: 0500 - - 000 00 00"], ["[telefon]", "[telefon]", "Tel: [telefon]"]),
    ("T5N5", None, ["Saat 08 . . 09 . . 10", "15 . . 11 . . 2026", "05 - - 06 - - 07"],
     ["Saat 08 . . 09 . . 10", "15 . . 11 . . 2026", "05 - - 06 - - 07"]),
    # ---- T5N6: telefon satirinda kanal etiketinden sonraki ad (6. tur: ad sozlugu parcasi iceren aday, bkz. T6O)
    ("T5N6", None, [f"Tel: {PHONE} Ofis Hasan Kaplo"], ["Tel: [telefon] Ofis {L1}"]),
    ("T5N6", None, [f"{PHONE} Ofis: Hasan Tavro", f"{PHONE} Sadece WhatsApp", f"{PHONE} Ofis Gebze"],
     ["[telefon] Ofis: {L1}", "[telefon] Sadece WhatsApp", "[telefon] Ofis Gebze"]),
    # ==== 6. tur: sifir genislikli karakter (U+200B, U+200C, U+200D, U+2060) ve yumusak tire kapsam disindadir:
    # ad ve metinde main'deki gibi kalir (silinmez, bosluk olmaz; ad eslesmesinde sozcuk siniridir)
    # ---- ZM: beklenen cikti ayni girdide main'in (onceki surum) ciktisidir. 'main:' notlu satirda dalin baska kurali (iletisim
    # alani, ticari ad) ek maske koyar; main'in maskeledigi her sey yine maskelidir. Ilk dort obek besinci incelemenin
    # bulgulari, dort karakterin her biriyle: yer adi parcasindan sonraki soyad, bolunmus adlardan sonraki soyad, buyuk harfe
    # yapisik soyad, tire ve hukuki bicim yanindaki ad
    ("ZM", None, ["Yetkili: İsta\u200bnbul Kaya"], ["Yetkili: {L1}\u200bnbul {L2}"]),   # main: yalniz soyad
    ("ZM", None, ["E\u200bmine ile Deni\u200bz Kader geldi"], ["E\u200bmine ile Deni\u200bz {L1} geldi"]),
    ("ZM", None, ["Kelvor\u200bYılmaz geldi", "Yetkili\u200bKelvor\u200bYılmaz"], ["Kelvor\u200b{L1} geldi", "Yetkili\u200bKelvor\u200b{L1}"]),
    ("ZM", None, ["Mehmet\u200b-\u200bYılmaz", "Tic. Ltd. Şti.\u200bHüseyin", "LTD ŞTİ\u200bDemir"],
     ["{L1}\u200b-\u200b{L2}", "Tic. Ltd. Şti.\u200b{L3}", "LTD ŞTİ\u200b{L4}"]),
    ("ZM", None, ["Yetkili: İsta\u200cnbul Kaya"], ["Yetkili: {L1}\u200cnbul {L2}"]),   # main: yalniz soyad
    ("ZM", None, ["E\u200cmine ile Deni\u200cz Kader geldi"], ["E\u200cmine ile Deni\u200cz {L1} geldi"]),
    ("ZM", None, ["Kelvor\u200cYılmaz geldi", "Yetkili\u200cKelvor\u200cYılmaz"], ["Kelvor\u200c{L1} geldi", "Yetkili\u200cKelvor\u200c{L1}"]),
    ("ZM", None, ["Mehmet\u200c-\u200cYılmaz", "Tic. Ltd. Şti.\u200cHüseyin", "LTD ŞTİ\u200cDemir"],
     ["{L1}\u200c-\u200c{L2}", "Tic. Ltd. Şti.\u200c{L3}", "LTD ŞTİ\u200c{L4}"]),
    ("ZM", None, ["Yetkili: İsta\u200dnbul Kaya"], ["Yetkili: {L1}\u200dnbul {L2}"]),   # main: yalniz soyad
    ("ZM", None, ["E\u200dmine ile Deni\u200dz Kader geldi"], ["E\u200dmine ile Deni\u200dz {L1} geldi"]),
    ("ZM", None, ["Kelvor\u200dYılmaz geldi", "Yetkili\u200dKelvor\u200dYılmaz"], ["Kelvor\u200d{L1} geldi", "Yetkili\u200dKelvor\u200d{L1}"]),
    ("ZM", None, ["Mehmet\u200d-\u200dYılmaz", "Tic. Ltd. Şti.\u200dHüseyin", "LTD ŞTİ\u200dDemir"],
     ["{L1}\u200d-\u200d{L2}", "Tic. Ltd. Şti.\u200d{L3}", "LTD ŞTİ\u200d{L4}"]),
    ("ZM", None, ["Yetkili: İsta\u2060nbul Kaya"], ["Yetkili: {L1}\u2060nbul {L2}"]),   # main: yalniz soyad
    ("ZM", None, ["E\u2060mine ile Deni\u2060z Kader geldi"], ["E\u2060mine ile Deni\u2060z {L1} geldi"]),
    ("ZM", None, ["Kelvor\u2060Yılmaz geldi", "Yetkili\u2060Kelvor\u2060Yılmaz"], ["Kelvor\u2060{L1} geldi", "Yetkili\u2060Kelvor\u2060{L1}"]),
    ("ZM", None, ["Mehmet\u2060-\u2060Yılmaz", "Tic. Ltd. Şti.\u2060Hüseyin", "LTD ŞTİ\u2060Demir"],
     ["{L1}\u2060-\u2060{L2}", "Tic. Ltd. Şti.\u2060{L3}", "LTD ŞTİ\u2060{L4}"]),
    # onceki turlarin sifir genislikli vakalari: buyuk/kucuk harf, katilimci parcasi, ad icinde, noktalama ve il adi yaninda
    ("ZM", None, ["Mehmet\u200bYılmaz aradı", "mehmet\u200cyılmaz aradı", "MEHMET\u200dYILMAZ ARADI"],
     ["{L1}\u200b{L2} aradı", "{L1}\u200cyılmaz aradı", "{L1}\u200dYILMAZ ARADI"]),
    ("ZM", None, ["selam\u200bArvo", "selam\u2060arvo geldi", "SELAM\u200cARVO", "selam\u200dkestel geldi"],
     ["selam\u200b{P:Arvo Kestel}", "selam\u2060{P:Arvo Kestel} geldi", "SELAM\u200c{P:Arvo Kestel}", "selam\u200d{P:Arvo Kestel} geldi"]),
    ("ZM", ("Ali Veli", "Arvo", "Brin Tamsel"), ["selam\u200bArvo", "selam\u200barvo", "SELAM\u200bARVO"],
     ["selam\u200b{P:Arvo}", "selam\u200b{P:Arvo}", "SELAM\u200b{P:Arvo}"]),
    ("ZM", None, ["tamam\u00adtamsel", "yarın\u2060brin gelir", "tamam\u200dtamsel\u200cgeldi"],
     ["tamam\u00ad{P:Brin Tamsel}", "yarın\u2060{P:Brin Tamsel} gelir", "tamam\u200d{P:Brin Tamsel}\u200cgeldi"]),
    ("ZM", None, ["selam\u200bar\u200bvo", "selam\u200bali\u200bveli", "ar\u200bvo geldi"],
     ["selam\u200bar\u200bvo", "selam\u200b{P:Ali Veli}\u200b{P:Ali Veli}", "ar\u200bvo geldi"]),
    ("ZM", None, ["selam\u200bmehmet", "33\u200bMehmet geldi"], ["selam\u200b{L1}", "33\u200b{L1} geldi"]),
    ("ZM", None, ["selam\u200bgeldi", "yük\u200dteslim", "tamam\u00adolur", "dorse\u2060yola çıktı"],
     ["selam\u200bgeldi", "yük\u200dteslim", "tamam\u00adolur", "dorse\u2060yola çıktı"]),
    ("ZM", None, ["A\u200bLİ geldi", "ALİ geldi", "MER\u200bSİN", "T\u200bON"], ["A\u200bLİ geldi", "{P:Ali Veli} geldi", "MER\u200bSİN", "T\u200bON"]),
    ("ZM", None, ["KAPLO NAKLİ\u200bYAT LTD. ŞTİ."], ["KAPLO NAKLİ\u200b[firma] LTD. ŞTİ."]),   # main: maske yok (ticari ad kurali)
    ("ZM", None, ["Meh\u200bmet geldi", "Meh\u00admet geldi", "Meh\u200cmet geldi", "Meh\u200dmet geldi", "Meh\u2060met geldi"],
     ["Meh\u200bmet geldi", "Meh\u00admet geldi", "Meh\u200cmet geldi", "Meh\u200dmet geldi", "Meh\u2060met geldi"]),   # sinir (issue)
    ("ZM", None, ["İrtibat: Ha\u200dsan Tav\u200cro 0500 000 00 00"],
     ["İrtibat: {L1}\u200dsan Tav\u200cro [telefon]"]),                          # main: yalniz telefon (iletisim alani)
    ("ZM", PEOPLE + ("KAP\u200bLO TAVRO",), ["Kaplo geldi", "KAP\u200bLO geldi", "Tavro geldi"],
     ["Kaplo geldi", "{P:KAP\u200bLO TAVRO} geldi", "{P:KAP\u200bLO TAVRO} geldi"]),
    ("ZM", None, ["Mehmet\u200b, Yılmaz geldi", "(Mehmet\u200b) aradı", "Mehmet.\u200bYılmaz", "Hasan\u200c: geldi", "Naime!\u200dgeldi"],
     ["{L1}\u200b, {L2} geldi", "({L1}\u200b) aradı", "{L1}.\u200bYılmaz", "{L3}\u200c: geldi", "{L4}!\u200dgeldi"]),
    ("ZM", None, ["KAYSERI - Ada\u200bna", "İstanbul\u200bKaya geldi", "Adana\u200bMehmet aradı"],
     ["KAYSERI - {L1}\u200bna", "İstanbul\u200b{L2} geldi", "Adana\u200b{L3} aradı"]),
    ("ZM", None, ["dün Zelvo\u200bbey aradı", "Sayın\u200bZelvo"], ["dün Zelvo\u200bbey aradı", "Sayın\u200bZelvo"]),
    ("ZM", None, ["dün Kap\u200blo Yılmaz geldi", "bugün Vel\u200bko Tunç ile konuştum"],
     ["dün Kap\u200blo {L1} geldi", "bugün Vel\u200bko {L2} ile konuştum"]),
    ("ZM", None, [f"Selamlar\nFen\u200bna Yılmaz\n{PHONE}"], ["Selamlar", "Fen\u200bna {L1}", "[telefon]"]),
    ("ZM", None, [f"Mehmet Yılmaz\u200b{PHONE}"], ["{L1}\u200b[telefon]"]),
    ("ZM", None, ["Ali\u200c\u0641\u0627\u0631\u0633\u06cc"], ["{P:Ali Veli}\u200c\u0641\u0627\u0631\u0633\u06cc"]),
    # ---- ZT: tek istisna: telefonun icinde rakamlar (ve ayraclar) arasindaki sifir genislikli karakter ve yumusak tire
    # telefonu bolmez (main bunlarin cogunu acik birakir); telefondan sonraki karakter maskeye girmez, iki haneli obekler
    # ve tarih telefon olmaz
    ("ZT", None, ["0500\u200b000\u200b00\u200b00", "0500\u00ad000\u00ad00\u00ad00", "0500\u2060000 00 00"],
     ["[telefon]", "[telefon]", "[telefon]"]),
    ("ZT", None, ["0500\u200d000\u200d00\u200d00", "0500\u200c000\u200c00\u200c00", "Tel: 0\u200c500 000 00 00"],
     ["[telefon]", "[telefon]", "Tel: [telefon]"]),
    ("ZT", None, ["0532\u200b111 22 33", "0500\u200b 000 00 00", "0500 \u2060000 00 00", "+90\u200c500 000 00 00",
                  "Tel: 0500\u200d-\u200d000 00 00", "0500\u00ad000 00 00"],
     ["[telefon]", "[telefon]", "[telefon]", "[telefon]", "Tel: [telefon]", "[telefon]"]),
    ("ZT", None, ["Hasan Tavro 0500\u200b000 00 00", ("Brin Tamsel", "Hasan Tavro geldi")],
     ["{L1} [telefon]", "{L1} geldi"]),                                          # main: telefon ve soyad acik
    ("ZT", None, ["0500 000 00 00\u200bgeldi", "0500 000 00 00\u200b5", "05\u200b06\u200b07\u200b08 Kasım", "15\u200b.11.2026"],
     ["[telefon]\u200bgeldi", "[telefon]\u200b5", "05\u200b06\u200b07\u200b08 Kasım", "15\u200b.11.2026"]),
    # ---- ZK: emoji ZWJ dizileri, bayrak, tus kapagi, ten rengi, Devanagari ve Farsca metin bayt bayt ayni kalir
    ("ZK", None, ["👨\u200d💻 iş", "🇹🇷 bayrak", "1\ufe0f\u20e3 tuş", "👍🏽 tamam", "\u0928\u092e\u0938\u094d\u0924\u0947\u200d\u0915",
                  "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645"],
     ["👨\u200d💻 iş", "🇹🇷 bayrak", "1\ufe0f\u20e3 tuş", "👍🏽 tamam", "\u0928\u092e\u0938\u094d\u0924\u0947\u200d\u0915",
      "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645"]),
    ("ZK", None, ["\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645"], ["\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645"]),
    ("ZK", None, ["👨\u200d👩\u200d👧 aile", "abc500 000 00 00"], ["👨\u200d👩\u200d👧 aile", "abc500 000 00 00"]),
    ("ZK", None, ["\u06f1\u06f2\u200c\u0645"], ["\u06f1\u06f2\u200c\u0645"]),
    # ---- T6O (6. tur): kanal etiketinden sonraki aday yalniz ad sozlugu parcasi icerirse maskelenir, yalniz o yerde (sohbete
    # yayilmaz); sozlukte olmayan aday main'deki gibi kalir (belgeli sinir)
    ("T6O", None, [f"{PHONE} Ofis Saatleri 9-18", f"Tel: {PHONE} Mobil Uygulama", "Uygulama çalışmıyor"],
     ["[telefon] Ofis Saatleri 9-18", "Tel: [telefon] Mobil Uygulama", "Uygulama çalışmıyor"]),
    ("T6O", None, [f"{PHONE} Ofis: Hasan Tavro", ("Brin Tamsel", "Tavro geldi"), ("Brin Tamsel", "Hasan Tavro geldi")],
     ["[telefon] Ofis: {L1}", "Tavro geldi", "{L1} Tavro geldi"]),
    ("T6O", None, [f"Tel: {PHONE} Ofis Kaplo", f"{PHONE} Ofis: Kaplo Tavro"], ["Tel: [telefon] Ofis Kaplo", "[telefon] Ofis: Kaplo Tavro"]),
    # ---- T7F1 (7. tur): katilimci ad parcasi iceren ogrenilmis ad main gibi her bicimiyle tek etiket (main: ayni ciktilar);
    # parcalari S3'teki gibi (yalniz hitap/Sayın yaninda); hicbir listede olmayan ad yalniz buyuk harfli (main hic maskelemez)
    ("T7F1", KT, [f"Kaplo Karasoy {PHONE}", ("Brin Tamsel", "kaplo karasoy geldi")], ["{L1} [telefon]", "{L1} geldi"]),
    ("T7F1", KT, ["İrtibat: Kaplo Karasoy", ("Brin Tamsel", "kaplo karasoy geldi")], ["İrtibat: {L1}", "{L1} geldi"]),
    ("T7F1", KT, [f"İrtibat: Kaplo Karasoy {PHONE}", ("Brin Tamsel", "Kaplo karasoy geldi")],
     ["İrtibat: {L1} [telefon]", "{L1} geldi"]),
    ("T7F1", KT, ["İrtibat: Kaplo Karasoy", ("Brin Tamsel", "Kaplo karasoy geldi")], ["İrtibat: {L1}", "{L1} geldi"]),
    ("T7F1", KT, [f"Tavro Karasoy {PHONE}", ("Brin Tamsel", "tavro karasoy geldi")], ["{L1} [telefon]", "{L1} geldi"]),
    ("T7F1", None, [f"Brin Karasoy {PHONE}", ("Arvo Kestel", "brin karasoy geldi")], ["{L1} [telefon]", "{L1} geldi"]),
    ("T7F1", None, ["İrtibat: Brin Karasoy", ("Arvo Kestel", "Brin karasoy geldi")], ["İrtibat: {L1}", "{L1} geldi"]),
    ("T7F1", NB, [f"Brin Karasoy {PHONE}", ("Arvo Kestel", "brin karasoy geldi"), ("Arvo Kestel", "Brin Karasoy geldi")],
     ["{L1} [telefon]", "brin karasoy geldi", "{L1} geldi"]),
    ("T7F1", KT, [f"Kaplo Karasoy {PHONE}", ("Brin Tamsel", "Karasoy geldi"), ("Brin Tamsel", "Sayın Karasoy"),
                  ("Brin Tamsel", "hüseyin karasoy geldi")],
     ["{L1} [telefon]", "{L1} geldi", "Sayın {L1}", "{L2} {L1} geldi"]),
    ("T7F1", KT, [f"Kaplo Karasoy {PHONE}", ("Brin Tamsel", "KAPLO KARASOY geldi"), ("Brin Tamsel", "Karasoy geldi"),
                  ("Brin Tamsel", "karasoy geldi")],
     ["{L1} [telefon]", "{L1} geldi", "Karasoy geldi", "karasoy geldi"]),      # main gibi: parca tek basina yayilmaz
    # ---- T7F2 (7. tur): ad sozlugunde de olan kanal etiketi sozcugu ':' almadan adin ilk parcasidir (tek etiket, yalniz o
    # yerde); ':' ya da ardinda etiket sozcugu varsa etiket kalir
    ("T7F2", None, [f"{PHONE} Sabit Işıkçı", f"{PHONE} Sabit Hat"], ["[telefon] {L1}", "[telefon] Sabit Hat"]),
    ("T7F2", None, [f"{PHONE} Ofis: Hasan Tavro"], ["[telefon] Ofis: {L1}"]),
    ("T7F2", None, [f"{PHONE} Ofis Saatleri 9-18", f"Tel: {PHONE} Mobil Uygulama", "Uygulama çalışmıyor"],
     ["[telefon] Ofis Saatleri 9-18", "Tel: [telefon] Mobil Uygulama", "Uygulama çalışmıyor"]),
    ("T7F2", None, [f"Sabit: {PHONE}", f"Sabit hat {PHONE}"], ["Sabit: [telefon]", "Sabit hat [telefon]"]),
    # ---- T7F3 (7. tur): ad ile telefon arasindaki telefon/isaret emojisi, ok, '|', '*' bosluk gibi ayractir (main ve 6. tur:
    # ad acik); yer adi ve ilan sozcugu yine ad olmaz
    *[("T7F3", None, [f"Kaplo Tavro {s} {PHONE}", f"Ahmet Tavro {s} {PHONE}", f"{PHONE} {s} Kaplo Tavro"],
       [f"{{L1}} {s} [telefon]", f"{{L2}} {s} [telefon]", f"[telefon] {s} {{L1}}"])
      for s in ("📞", "👉", "☎️", "📲", "➡️", "→", ">", "|", "*")],
    ("T7F3", None, [f"Kaplo Tavro: ☎️ {PHONE}", f"{PHONE} ☎ Kaplo Tavro"], ["{L1}: ☎️ [telefon]", "[telefon] ☎ {L1}"]),
    ("T7F3", None, [f"ADANA 📞 {PHONE}", f"TIR ARANIYOR 👉 {PHONE}", f"Mersin ➡️ Adana {PHONE}", f"26 TON | {PHONE}",
                    f"ACİL * {PHONE}"],
     ["ADANA 📞 [telefon]", "TIR ARANIYOR 👉 [telefon]", "Mersin ➡️ Adana [telefon]", "26 TON | [telefon]",
      "ACİL * [telefon]"]),
    # ---- T7E (7. tur eki): kanit bilineni yalniz guclendirir; mesaj sirasi ne olursa olsun main'in her bicimiyle ogrendigi ad
    # dalda da her bicimiyle maskelenir (beklenen cikti main'in maskeledigi her sozcugu maskeler)
    # T7E1: yalniz iletisim kanitiyla (yalniz buyuk harfli) bilinen ad, sonra gelen Sayın kanitiyla her bicimiyle
    ("T7E1", None, [f"Zelvo {PHONE}", "Sayın Zelvo", "zelvo geldi", "Zelvoya sor"],
     ["{L1} [telefon]", "Sayın {L1}", "{L1} geldi", "{L1}'ya sor"]),
    ("T7E1", None, [f"Tel: Dorin Zelvo {PHONE}", "Sayın Dorin Zelvo", "dorin zelvo geldi", "dorin aradı"],
     ["Tel: {L1} [telefon]", "Sayın {L1}", "{L1} geldi", "{L1} aradı"]),
    # T7E2: bilinen tam ad ardindaki sozcugu ad kurallarindan saklamaz (hitaptan onceki soyad main gibi ogrenilir)
    ("T7E2", None, ["Sayın Dorin Junvo'ya iletildi", "Dorin Junvo abla nerede", "junvo çıktı"],
     ["Sayın {L1}'ya iletildi", "{L1} abla nerede", "{L2} çıktı"]),
    # T7E3: ayni araliktaki iletisim karari ad kuralinin (hitap) ogrenmesini dusurmez
    ("T7E3", None, [f"Tamam {PHONE} - Bavsur kardeş yükledi", "bugün bavsur aradı", "Bavsurdan haber yok"],
     ["Tamam [telefon] - {L1} kardeş yükledi", "bugün {L1} aradı", "{L1}'dan haber yok"]),
    # T7E4: bilinen ad + listede soyad, tam ad yalniz iletisimle biliniyor olsa da ad-soyad olarak ogrenilir
    ("T7E4", None, [f"Pelsel Kolcak : {PHONE} ve Sayın Pelsel merhaba", "Pelsel Kolcak çıktı", "pelsel kolcak bekliyor"],
     ["{L1} : [telefon] ve Sayın {L1} merhaba", "{L1} çıktı", "{L1} bekliyor"]),
    # T7E5: once uygulanan tek sozcuklu yerel karar ogrenilmis tam adi bolmez
    ("T7E5", None, [f"Bala Morkal {PHONE}", "bala morkal yükü aldı", "Sn Bala Morkal yük hazır"],
     ["{L1} [telefon]", "{L1} yükü aldı", "Sn {L1} yük hazır"]),
    # T7E6: ayni konumda en uzun ad (yalniz buyuk harfli kisa parca uzun tam adi, kisa ad uzun imzayi bolmez)
    ("T7E6", None, [f"Bavko Bozkurt > {PHONE}", f"İrtibat: Hasan Bavko {PHONE}", "Sn. Bavko Bozkurt", "bugün Bavko aradı"],
     ["{L1} > [telefon]", "İrtibat: {L2} [telefon]", "Sn. {L1}", "bugün Kişi ? aradı"]),
    ("T7E6", None, [f"Ankara - Samsun\naçık kasa tır\nTarık Doğuş\n{PHONE}"], ["Ankara - Samsun", "açık kasa tır", "{L1}", "[telefon]"]),
    # T7E7: ticari adin icindeki sozluk adi main gibi ogrenilir (apostrofsuz ekli bicimi de maskelenir)
    ("T7E7", None, [f"Arro Koray Taşımacılık\n{PHONE}", "Arro Korayın sor"], ["[firma] Taşımacılık", "[telefon]", "Arro {L1}'ın sor"]),
    # T7E8: yalniz iletisimle bilinen adin sonuna binen ogrenilmis ad tasan sozcuguyle maskelenir
    ("T7E8", ("Ali Veli", "Pelğa Plimöz", "Sargis Çetinkaya"),
     [f"Sorumlu: Plimöz Brinzo Çetinkaya {PHONE}", "dün Brinzo abiye sor", "Plimöz Brinzo Çetinkaya Lojistik geldi"],
     ["Sorumlu: {L1} [telefon]", "dün {L1} abiye sor", "{L1} {L2} geldi"]),
    # T7E9: main'in kanitindan sonra gelen guclu iletisim kaniti parcalarini yine yayar (sira sonucu degistirmez)
    ("T7E9", None, ["ZEKİYE KIZILTEPE NAKLİYAT", f"{PHONE} 📲 Zekiye Kızıltepe", "kızıltepe beye aradı"],
     ["[firma] NAKLİYAT", "[telefon] 📲 {L1}", "{L1} beye aradı"]),
    # T7E10: once uygulanan ticari ad karari, main'in ogrendigi daha uzun adi (ad, soyad ve buyuk harfli ucuncu sozcuk) bolmez
    ("T7E10", None, ["Kemal Tunç Lojistik yük arıyor", "KEMAL TUNÇ LOJİSTİK"], ["{L1} yük arıyor", "{L1}"]),
    # T7E11: Sayın/@ kaniti, tam ad once baska kanitla ogrenilmis olsa da yalniz iletisimle bilinen ad parcasini her bicimiyle
    # yayar (main'de Sayın ilk kanittir)
    ("T7E11", None, [f"Helra Keskin {PHONE}", "Helra Keskin bekliyor", "Sn Helra Keskin yük hazır", "bugün helra çıktı"],
     ["{L1} [telefon]", "{L1} bekliyor", "Sn {L1} yük hazır", "bugün {L1} çıktı"]),
]


def _template_rx(exp, a):
    """Beklenen satirlari regex'e cevirir -> (regex, L yer tutuculari sirasi)."""
    out, seen = [], []
    for part in re.split(r"(\{P:[^}]+\}|\{L\d+\})", "\n".join(exp)):
        if part.startswith("{P:"):
            out.append(re.escape(a.labels[part[3:-1]]))
        elif re.fullmatch(r"\{L\d+\}", part):
            if part in seen:
                out.append(f"(?P={part[1:-1]})")
            else:
                seen.append(part)
                out.append(rf"(?P<{part[1:-1]}>Kişi \d+)")
        else:
            out.append(re.escape(part))
    return "".join(out), seen


def check(case, row):
    cls, people, msgs, exp = row
    people = people or PEOPLE
    rows = [m if isinstance(m, tuple) else ("Ali Veli", m) for m in msgs]
    out, a = run(rows, people)
    got = "\n".join(out)
    rx, ls = _template_rx(exp, a)
    m = re.fullmatch(rx, got)
    case.assertTrue(m, f"[{cls}] {msgs!r}\n  beklenen: {exp!r}\n  cikti:    {out!r}")
    labs = [m.group(x[1:-1]) for x in ls]
    case.assertEqual(len(set(labs)), len(labs), f"[{cls}] farkli kisi ayni etiketi aldi: {out!r}")
    for x in labs:
        case.assertNotIn(x, a._people, f"[{cls}] katilimci etiketi beklenmiyordu: {out!r}")


class DecisionTable(unittest.TestCase):
    def test_rows(self):
        for row in ROWS:
            with self.subTest(cls=row[0], msgs=row[2]):
                check(self, row)

    def test_every_row_named(self):
        for row in ROWS:
            self.assertRegex(row[0], r"^[A-Z][A-Za-z0-9]*$")


class SpeedGuards(unittest.TestCase):
    """Hiz kisayollari sonucu degistirmez: telefon on denetimi (_PHONE_Q) her telefonu bulur; ilk harfe gore gruplanmis ad
    secenekleri (_first_alt) her adi tek tek denenmis gibi esler."""

    def test_phone_precheck_covers_every_phone(self):
        import wa2md
        rx = re.compile(wa2md._PHONE)
        wide = ["0500  -  000  -  00  -  00", "+90  -  500  -  000  -  00  -  00", "0  -  500  -  000  -  00  -  00",
                "0️⃣5️⃣0️⃣0️⃣  -  0️⃣0️⃣0️⃣ 00 00",
                "(0500)  000  00  00", "0090  -  532  -  000 00 00", "０５００－０００－００－００", PHONE]
        lines = wide + [ln for row in ROWS for m in row[2] for ln in (m[1] if isinstance(m, tuple) else m).split("\n")]
        for ln in lines:
            ln = wa2md.decode(ln.encode("utf-8"))
            if any(m.group(0) for m in rx.finditer(ln)):
                self.assertTrue(wa2md._PHONE_Q.search(ln), ln)

    def test_first_letter_groups_match_like_single_names(self):
        import wa2md
        names = ["Çelik Tavro", "Can", "cemil", "İsmail", "ılgaz", "Işık", "ẞeta", "ßeta Kaplo", "Hasan Tavro", "hasan", "Ömer"]
        rx = re.compile("(?:" + wa2md._first_alt(names) + r")(?!\w)")
        for n in names:
            for form in {n, n.upper(), n.lower(), n.title()}:
                if re.fullmatch(wa2md._name_regex(n), form):
                    self.assertTrue(rx.match(form), form)
                    self.assertEqual(rx.match(form).group(0), form, form)     # en uzun ad kazanir


class ZeroWidthMainParity(unittest.TestCase):
    """6. tur (ZM): sifir genislikli karakter kapsam disindadir; ad ve metinde main'deki gibi islenir. Fikstur
    (fixtures/sifir_genislik_main.json): uydurma, telefonsuz, sifir genislikli karakterli 600 satir (sabit tohumlu uretec;
    katilimci adi parcalari, sozluk adlari, soyadlar, sozlukte olmayan adlar, il adlari, hitap, iletisim ve hukuki bicim
    sozcukleri, noktalama; karakter sozcuk arasinda, sozcuk icinde, noktalama yaninda) ve main'in (onceki surum) bu satirlar icin
    ciktisi. main'in kodu testte ice aktarilamadigindan main araci bir kez calistirilip kaydedildi. Esdeger: (1) dalin
    ciktisi girdinin bazi parcalari maskeyle degistirilmis halidir (sifir genislikli karakterler dahil kalan her karakter
    ayni); (2) main'in maskeledigi her sozcuk (\\w+ dizisi) dalda da maskelidir."""

    FIXTURE = os.path.join(HERE, "fixtures", "sifir_genislik_main.json")
    MASK = re.compile(r"Kişi (?:\d+|\?)|\[[a-zçğıöşü\-]+\]|Sohbet-\d+")

    def masked(self, src, out):
        """out, src'nin bazi parcalari maskelenmis hali -> maskelenen karakter konumlari."""
        parts = self.MASK.split(out)
        m = re.fullmatch("(.+?)".join(re.escape(p) for p in parts), src, re.S)
        self.assertIsNotNone(m, f"cikti girdiden yalniz maskeyle ayrilmali: {src!r} -> {out!r}")
        return {i for g in range(1, len(parts)) for i in range(m.start(g), m.end(g))}

    def test_masks_every_word_main_masks(self):
        with open(self.FIXTURE, encoding="utf-8") as f:
            fx = json.load(f)
        people, sender, words = tuple(fx["katilimcilar"]), fx["gonderen"], 0
        for chat in fx["sohbetler"]:
            got, _ = run([(sender, src) for src, _ in chat], people)
            self.assertEqual(len(got), len(chat))
            for (src, ref), out in zip(chat, got):
                main_m, ours = self.masked(src, ref), self.masked(src, out)
                for w in re.finditer(r"\w+", src):
                    span = set(range(w.start(), w.end()))
                    if span & main_m:
                        words += 1
                        self.assertTrue(span & ours, f"{w.group()!r}: {src!r} -> {out!r}; main: {ref!r}")
        self.assertGreater(words, 350)


class InteractionMainParity(unittest.TestCase):
    """7. tur eki (T7E): kanit bilineni yalniz guclendirir; dal main'in maskeledigi hicbir sozcugu acmaz (tek istisna: kanitli
    guzergahtaki katilimci yer adi parcasi). Fikstur (fixtures/etkilesim_main.json): uydurma, etkilesim agirlikli 300 sohbet
    (sabit tohumlu uretec; dalin onceki surumde main'den az maskeledigi her sohbet dahil) ve her mesaj icin main'in (onceki surum)
    maskeledigi karakter araliklari [mesaj, bas, son, istisna]; main araci bir kez calistirilip kaydedildi."""

    FIXTURE = os.path.join(HERE, "fixtures", "etkilesim_main.json")
    MASK = re.compile(r"Kişi (?:\d+|\?)['\u2019]?|\[[a-zçğıöşü\-]+\]|Sohbet-\d+")

    def masked(self, src, out):
        """out, src'nin bazi parcalari maskelenmis hali -> maskelenen karakter konumlari (etiket ekinin apostrofu dahil)."""
        parts = self.MASK.split(out)
        m = re.fullmatch("(.+?)".join(re.escape(p) for p in parts), src, re.S)
        self.assertIsNotNone(m, f"cikti girdiden yalniz maskeyle ayrilmali: {src!r} -> {out!r}")
        return {i for g in range(1, len(parts)) for i in range(m.start(g), m.end(g))}

    def test_never_masks_less_than_main(self):
        with open(self.FIXTURE, encoding="utf-8") as f:
            fx = json.load(f)
        checked = 0
        for chat in fx["sohbetler"]:
            people, msgs = tuple(chat["k"]), chat["m"]
            out, _ = run([(people[s], t) for s, t in msgs], people)
            got, i = [], 0
            for _, t in msgs:                 # mesaj basina cikti satirlari (cok satirli ilan dahil)
                n = t.count("\n") + 1
                got.append("\n".join(out[i:i + n]))
                i += n
            self.assertEqual(i, len(out))
            masks = {}
            for mi, st, en, exc in chat["t"]:
                if exc:
                    continue
                src = msgs[mi][1]
                if mi not in masks:
                    masks[mi] = self.masked(src, got[mi])
                checked += 1
                self.assertTrue(set(range(st, en)) <= masks[mi], f"{src[st:en]!r}: {src!r} -> {got[mi]!r}")
        self.assertGreater(checked, 15000)


if __name__ == "__main__":
    unittest.main()
