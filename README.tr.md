[English](README.md) | **Türkçe**

# wa2md

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml) ![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg) ![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)

> **Resmî olmayan araç.** wa2md bağımsız bir açık kaynak projedir. WhatsApp ya da Meta ile bağlantılı, onlar tarafından onaylanmış veya desteklenmiş değildir. "WhatsApp" adı burada yalnızca aracın okuduğu sohbet biçimini ve web sayfasını belirtmek için kullanılır.

> **Paylaşmadan önce ÇIKTININ TAMAMINI oku.** Buradaki anonimleştirme sezgiseldir: doğrudan tanımlayıcıları kaldırır ve bazılarını kaçırır ([Bu aracın otomatik bulamadıkları](docs/tr/anonymization.md) bölümüne bak). İnceleme dosyası yardımcıdır, garanti değildir. **Fotoğraflar, videolar ve ses kayıtları olduğu gibi kopyalanır ve anonimleştirilmez** (yüzler, kimlik belgeleri, banka kartları, ad içeren ekran görüntüleri): paylaşmadan önce `--medya-yok` kullan.

WhatsApp sohbetlerini (kişi veya grup) fotoğrafları gömülü Markdown dosyasına çevirir ve varsayılan olarak anonimleştirir. İki girdi yolu var; ikisi de aynı Markdown yazıcısını (`wa2md.write_chat`) kullanır, çıktı biçimi aynıdır. Araç yalnız Python standart kütüphanesini kullanır. Çıktı düzeni ve biçimi: [docs/tr/output-format.md](docs/tr/output-format.md).

## Hızlı başlangıç

```
python wa2md.py "C:\Users\kullanici\Downloads\WhatsApp Chat with Ali Veli.zip" --out C:\Users\kullanici\wa-out
```

Çıktı varsayılan olarak anonimleştirilir. Yalnız Python 3.9+ gerekir (ek paket yok). WhatsApp Web ve telefon dışa aktarması için bkz. "Girdi yolları".

**Bir şey paylaşmadan önce:** fotoğraflar, videolar ve ses kayıtları `media/` klasörüne **olduğu gibi kopyalanır ve anonimleştirilmez** (yüzler, kimlik belgeleri, banka kartları, ad içeren ekran görüntüleri). Bunları dışarıda bırakmak için `--medya-yok` kullan ve Markdown çıktısının tamamını kendin oku:

```
python wa2md.py "C:\Users\kullanici\Downloads\WhatsApp Chat with Ali Veli.zip" --out C:\Users\kullanici\wa-out --medya-yok
```

## Girdi yolları

1. **WhatsApp Web (önerilen):** telefonda dışa aktarma adımı yok. Giriş yapılmış WhatsApp Web sekmesinde bir JavaScript toplayıcı (`wa_collect.js`) çalışır; sonucu `wa_web.py import` Markdown'a çevirir. Kurulum, adımlar, sınırlar ve okundu bilgisi notu: [docs/tr/whatsapp-web.md](docs/tr/whatsapp-web.md).
2. **Telefon dışa aktarması (alternatif):** WhatsApp'ın "Sohbeti dışa aktar" zip'ini ya da klasörünü `wa2md.py` ile çevirir. Ayrıntılar: [docs/tr/phone-export.md](docs/tr/phone-export.md).

## Anonimleştirme

Varsayılan olarak açıktır (kapatmak için `--no-anonim`). Adlar, telefon numaraları, e-posta adresleri, bağlantılar, gizli değerler ve benzeri doğrudan tanımlayıcılar `Chat-N`, `Person N` ve `[phone]` gibi etiketlerle değiştirilir; bir inceleme dosyası metinde kalan şüpheli sözcükleri listeler. Sezgiseldir ve elinden geleni yapar: sohbeti hukuki anlamda anonim yapmaz, bazı şeyleri kaçırır ve medyayı hiçbir zaman anonimleştirmez. Neyi maskelediği, neyi bulamadığı ve sonucun nasıl gözden geçirileceği: [docs/tr/anonymization.md](docs/tr/anonymization.md).

## Dil desteği

Birincil dil İngilizcedir, Türkçe desteklenen dildir. `--lang en|tr` konsol iletilerini ve çıktı etiketlerini seçer; `--packs auto|en|tr|en,tr` sohbet metninde ad bulmak için kullanılan dil paketlerini seçer. Ayrıntılar, İngilizce kuralların sınırları ve dil ekleme: [docs/tr/language-support.md](docs/tr/language-support.md), [docs/language-packs.md](docs/language-packs.md) (İngilizce). Tüm seçenekler ve Türkçe takma adları: [docs/tr/options.md](docs/tr/options.md).

## Yapay zekâya körlemesine çalıştırma

Bir yapay zekâ ajanı gerçek dışa aktarmalar üzerinde `python wa2md.py <girdi-klasörü> --out <çıktı-klasörü>/<YYYYAAGG-SSDD>` komutunu kimin kim olduğunu öğrenmeden çalıştırabilir: konsol yalnız etiket ve sayı gösterir, her çalıştırmada yeni bir çıktı klasörü kullanılır, `--no-anonim` yalnız sahibi içindir. Bu korumanın sınırları (fotoğraflar, `wa_web.py list`): [docs/tr/blind-run.md](docs/tr/blind-run.md).

## Sınırlar ve sorumlu kullanım

- **Tespit elinden geleni yapar (best-effort).** Buradaki anonimleştirme sezgiseldir (sözlükler, kalıplar ve bağlam kuralları). Doğrudan tanımlayıcıları kaldırır; sohbeti hukuki anlamda anonim yapmaz ve hiçbir anonimleştirici her şeyi bulamaz. Sözlükte olmayan adlar, olağandışı yazımlar, lakaplar, yerler, unvanlar ve yalnız bir araya geldiklerinde kişiyi belli eden ayrıntılar kaçar; sıradan sözcükler de bazen yanlışlıkla maskelenir.
- **Paylaşmadan önce çıktının TAMAMINI okuyun.** İnceleme dosyası metinde kalan şüpheli sözcükleri listeler; yardımcıdır, garanti değildir.
- **Medya anonimleştirilmez.** Fotoğraf, video ve ses kayıtları olduğu gibi kopyalanır (yüzler, belgeler, ekran görüntüleri); paylaşacağınız her şey için `--no-media` kullanın.
- **Yalnız işleme hakkınız olan sohbetlerde kullanın.** Sizin ve diğer katılımcıların dönüştürmeye uygun olduğundan emin olun; özgün dosyaları, ham `wa-bundle-*.json` dosyalarını ve çıktıyı özgün sohbet kadar güvende tutun.
- **Kaçanları yalnız uydurma örneklerle bildirin.** Bkz. [CONTRIBUTING.md](CONTRIBUTING.md); kişisel veriyi belgelenen davranışın aksine maskesiz bırakan bir durum güvenlik sorunudur ([SECURITY.md](SECURITY.md)).

## Kurulum (isteğe bağlı)

`python wa2md.py ...` doğrudan depo klasöründen çalışır. Komutların PATH'te olmasını istersen depo klasöründen kur (Python 3.9+, üçüncü taraf bağımlılık yok):

```
pip install .
wa2md --help        # python wa2md.py ile aynı
wa2md-web --help    # python wa_web.py ile aynı (WhatsApp Web yardımcısı)
```

Sözlükler (`adlar/`) ve toplayıcı (`wa2md_assets/wa_collect.js`) birlikte kurulur ve çalışma anında bulunur. Deneysel doğrudan Chrome bağlantısı (`wa2md-web list` / `export`) isteğe bağlı eklentiyi ister: `pip install ".[browser]"` (Playwright). PyPI'ye hiçbir şey yayımlanmaz.

## Test

```
python -m unittest discover -s tests -v
.venv\Scripts\python -m unittest discover -s tests -v
```

İkincisi (venv) ek olarak gerçek-Chrome testlerini çalıştırır: `wa_collect.js`'i gerçek (başlıksız) Chrome'da, gerçek WhatsApp Web DOM yapısını taklit eden uydurma fixture'larda çalıştırır; ayrıca kendi geçici Chrome'unu ayrı profille başlatıp sahte WhatsApp sayfasında CDP `list`/`export` akışını dener. Senin Chrome'una dokunmaz. Venv/Chrome yoksa o testler atlanır.

## Gizlilik

`exports/`, `out/`, `*.zip`, `wa-bundle-*.json` ve `.venv/` `.gitignore` içinde listelidir. Bu, sohbet verisini commit etme riskini azaltır ama ortadan kaldırmaz: başka klasörler ve dosya adları kapsanmaz, `git add -f` bunu geçersiz kılar. Her commit ve push öncesi `git status` ile içeriği kontrol et. Test fixture'ları uydurma veridir.

## Lisans

Kod MIT lisansı altındadır (bkz. `LICENSE`). Bu lisans yalnız koda uygulanır; `adlar/` altındaki veri dosyaları ayrıdır ([docs/tr/data-sources.md](docs/tr/data-sources.md) ve `DATA-LICENSES.md` dosyasına bak: her veri dosyası CC0, kamu malı ya da bu projenin kendi işidir (MIT)).

## Veri kaynakları ve atıf

`adlar/` klasöründeki ad, soyad, sözcük-ad ve yer sözlükleri araçla birlikte gelir, çevrimdışı okunur; Wikidata'dan (CC0 1.0), ABD Nüfus Sayımı'ndan (kamu malı) ve bu proje için yapılan elle incelemeden derlenmiştir; hiçbir dosya paylaşım-aynı-koşulda (share-alike) bir lisans altında değildir. Tüm test verileri ve örnek dosyalar uydurmadır. Dosya başına tablo, lisanslar ve alınma tarihleri: [docs/tr/data-sources.md](docs/tr/data-sources.md).

## Diğer belgeler

- [docs/tr/whatsapp-web.md](docs/tr/whatsapp-web.md), [docs/tr/phone-export.md](docs/tr/phone-export.md): iki girdi yolu
- [docs/tr/anonymization.md](docs/tr/anonymization.md): neyin maskelendiği ve neyin bulunamadığı
- [docs/tr/language-support.md](docs/tr/language-support.md), [docs/language-packs.md](docs/language-packs.md), [docs/tr/options.md](docs/tr/options.md): diller, paketler, seçenek adları
- [docs/tr/blind-run.md](docs/tr/blind-run.md), [docs/tr/output-format.md](docs/tr/output-format.md), [docs/tr/data-sources.md](docs/tr/data-sources.md)
- Bu sayfaların İngilizcesi (`docs/<aynı ad>.md`) için bkz. [README.md](README.md)
