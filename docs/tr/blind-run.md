[README](../../README.tr.md) | [English](../blind-run.md) | **Türkçe**

# Yapay zekâya körlemesine çalıştırma

Amaç: bir yapay zekâ ajanı betiği gerçek dışa aktarımlar üzerinde çalıştırsın ama kimin kim olduğunu öğrenmesin.

1. Telefon dışa aktarması zip'lerini sahibin seçtiği bir **girdi klasörüne** koy. Ajana yalnız bu klasörün yolu verilir; ajan klasörü listelemez, açmaz (dosya adları kişi adı içerir).
2. Ajan yalnız şu tek komutu çalıştırır; her çalıştırmada yeni bir **çıktı klasörü** kullanılır, çünkü `Sohbet-N` etiketleri konumsaldır:

   ```
   python wa2md.py <girdi-klasörü> --out <çıktı-klasörü>/<YYYYAAGG-SSDD>
   ```

   Windows, Linux ve macOS'ta çalışır; **Python 3.9 veya üstü** ve yalnız standart kütüphane yeterlidir (3.9 alt sınırı `argparse.BooleanOptionalAction`'dan gelir; betik sözdizimi olarak 3.8'de de ayrışır ama `--anonim`/`--anonymize` bayrağı 3.9 ister). `wa2md.py` için venv/Playwright **gerekmez**; yalnız WhatsApp Web yolundaki deneysel `list`/`export` ve tarayıcı testleri Playwright ister. Konsol çıktısı Türkçe karakter içerdiği için betik stdout/stderr'i UTF-8'e zorlar (ASCII konsolda da çökmez).

3. Ajanın gördüğü: konsolda yalnız etiketler ve sayılar (özet sayımları dahil) (`[Sohbet-1] N mesaj, M medya ... -> yol`, hatalı girdiler `girdi N`; ad, zip/dosya adı, telefon, mesaj metni ve ayrıştırılamayan satırlar yazılmaz), sonra yalnız `Sohbet-N` klasörlerindeki anonim Markdown. İnceleme dosyası (çıktı klasörünün dışında, kullanıcı durum klasöründe yazılır; bkz. [Anonimleştirme](anonymization.md) içindeki "Çalışma sonu özeti") olası gerçek adlar içerir: ajan onu açmaz, yalnız sen bakarsın.
4. `--no-anonim` **yalnız senin içindir** (anonimsiz, gerçek adlı normal çıktı ve ayrıntılı hata tanısı üretir); ajana verilmez. Anonim modda eşleme gösteren/saklayan hiçbir bayrak yoktur.

Sınır: bu yalnız konsolu ve çıktı dosyalarını korur. Fotoğraflar anonimleştirilmez (ajan görüntüden ad aktarmamalıdır); `wa_web.py list` sohbet adlarını yazar, ajan çalıştırmamalıdır.
