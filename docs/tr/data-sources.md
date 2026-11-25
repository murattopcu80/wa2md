[README](../../README.tr.md) | [English](../data-sources.md) | **Türkçe**

# Veri kaynakları ve atıf

`adlar/` klasöründeki sözlükler araçla birlikte gelen düz metin dosyalarıdır ve çevrimdışı okunur (çalışma anında hiçbir şey indirilmez):

| Dosya | İçerik | Kaynak ve nasıl derlendi | Alınma |
|---|---|---|---|
| `tr-adlar.txt` | Türkçe kişi adları | Wikidata Query Service: Türkiye vatandaşlarının en az iki kez geçen adları ve Türkçe ad ögeleri; iki ad elle çıkarıldı | 2026-11-14 |
| `tr-soyadlar.txt` | Türkçe soyadları | Wikidata Query Service: Türkiye vatandaşlarının en az iki kez geçen soyadları ve Türkçe soyadı ögeleri | 2026-11-14 |
| `tr-yerler.txt` | Türkiye il ve ilçeleri | Wikidata Query Service: il ve ilçe ögeleri, birincil etiket, temizlenmiş (ekler ve parantezler atıldı) | 2026-11-15 |
| `sozcuk-adlar.txt` | sözcük anlamı da olan adlar (yalnız bağlamla maskelenir) | Wikidata sözcükbirimleri ve yer adları (CC0 1.0) ile bu proje için elle derlenen bölüm (MIT, kodla aynı) | 2026-11-14 / 2026-11-15 |
| `en-given.txt` | İngilizce adlar (5.888) | Wikidata Query Service: en az 5 kişide görülen BK ve ABD vatandaşı adları (İngilizce etiket); işlev sözcükleri, unvanlar, ay/gün adları ve listedeki yer adları çıkarıldı (`tools/build_en_lists.py`), CC0 1.0 | 2026-11-20 |
| `en-surnames.txt` | ABD soyadları (6.732) | ABD Nüfus Bürosu, 2010 Nüfus Sayımı sık soyadları (en az 5.000 kişi); kamu malı | 2026-11-20 |
| `en-word-names.txt` | sözcük anlamı da olan İngilizce adlar (371) ve İngilizcede sıradan sözcük olan Türkçe adlar (19) | adaylar: Wikidata Lexemes'te küçük harfli İngilizce sözcükbirimi olan adlar (CC0 1.0); bu proje için elle gözden geçirildi (MIT) | 2026-11-20 |
| `en-places.txt` | bölgeler (ABD eyaletleri, BK ülkeleri, Kanada ve Avustralya eyaletleri, ülkeler) ve 104 büyük şehir | bu proje için elle derlendi (MIT) | 2026-11-20 |
| `en-given-more.txt` | başka kökenlerden adlar (2.513; Fas, Nijerya, Çin, İspanya, Polonya, Hindistan, Pakistan, ... vatandaşları) | Wikidata (QLever uç noktası): listelenen her ülkenin en az 5 vatandaşında görülen adlar (İngilizce etiketler); `en-given.txt` adları, sıradan İngilizce sözcükler ve yer adları çıkarıldı (`tools/build_en_lists.py`), CC0 1.0 | 2026-11-20 |
| `en-common.txt` | sıradan İngilizce sözcükler (8.119): İngilizce paketin soyadı, kapanış ve küçük harf kuralları ile paketler arası kural için | Wikidata Lexemes (CC0 1.0): küçük harfli İngilizce sözcükbirimleri; kamu malı 54 Project Gutenberg kitabındaki küçük harfli sözcük sayılarıyla (sözcük kitapların en az %30'unda geçmeli) ve elle gözden geçirilen düzensiz biçim ve güncel sözcük listesiyle birleştirildi (`tools/build_common_lists.py`); bu proje için derlendi (MIT, kod gibi); paylaşım-koşullu veri yok | 2026-11-20 |
| `tr-common.txt` | İngilizce ad olan gündelik Türkçe sözcükler (43): paketler arası kural için | bu proje için elle derlendi (MIT, kod gibi): ad sözlükleri ve projenin kendi kurallarındaki Türkçe sözcük listeleri okunarak (`tools/build_common_lists.py`) | 2026-11-20 |

Lisans: Wikidata'nın yapısal verisi CC0 1.0'dır (kamu malı, https://www.wikidata.org/wiki/Wikidata:Licensing); `sozcuk-adlar.txt` içindeki elle derlenen bölüm bu deponun lisansı altındadır. `en-common.txt` ve `tr-common.txt` bu proje için CC0 / kamu malı kaynaklardan ve elle gözden geçirmeyle derlenmiştir (tabloya bak). `adlar/` altındaki hiçbir dosya paylaşım-koşullu (share-alike) lisansta değildir. Dosya dosya kaynak ve lisans listesi `DATA-LICENSES.md` içindedir. Sorgular, süzgeçler, sayılar ve elle çıkarmalar her dosyanın başındaki yorum satırlarında yazılıdır; listeler yeniden üretilebilir. Listeler elinden geleni yapar: özel veri içermezler, ama eksiksiz ya da hatasız değildirler ([Sınırlar ve sorumlu kullanım](../../README.tr.md#sınırlar-ve-sorumlu-kullanım) bölümüne bak).

**Bu depodaki tüm test verileri ve örnek dosyalar uydurmadır** (uydurma adlar, ayrılmış `0500 000 xx xx` ailesinden numaralar, `example.*` ve `.test` adresleri); gerçek bir sohbet ya da gerçek bir kişi kullanılmamıştır.

`adlar/` klasöründeki ad, soyad, sözcük-ad ve yer listeleri Wikidata'dan (https://www.wikidata.org) Wikidata Query Service ile derlenmiştir. Wikidata'nın yapısal verisi CC0 1.0 (kamu malı) kapsamındadır: https://www.wikidata.org/wiki/Wikidata:Licensing. Alınma tarihleri ve kullanılan sorgular her dosyanın başında yazılıdır (`tr-adlar.txt` ve `tr-soyadlar.txt`: 2026-11-14; `tr-yerler.txt` ve `sozcuk-adlar.txt`: 2026-11-15).
