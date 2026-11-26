[README](../../README.tr.md) | [English](../whatsapp-web.md) | **Türkçe**

# 1. WhatsApp Web yolu (konsol yolu — bugün çalışan yol)

> **Önemli not (WhatsApp Web yolu):** Bu yol yalnız senin kendi sohbetlerini, kendi girişini yaptığın tarayıcı sekmesinde okur ve hiçbir yere veri göndermez. Yine de WhatsApp Web'den otomatik toplama WhatsApp'ın kullanım koşullarıyla çakışabilir. Önerilen yol WhatsApp'ın resmi "Sohbeti dışa aktar" yoludur ([telefondan dışa aktarma](phone-export.md)). Web yolunun kullanımı tamamen kendi sorumluluğundadır. Bu yola ait dosyalar: `wa_web.py`, `wa_collect.js`, `tests/test_wa_web.py`, `tests/test_browser_smoke.py` ve `tests/fixtures/web/`.

Toplama mantığı (sohbeti arama kutusundan bulma, eski mesajlara kaydırma, mesaj ayrıştırma, fotoğraf blob'ları) tek dosyada: `wa2md_assets/wa_collect.js`. Chrome'a dışarıdan bağlanmak gerekmez; kod senin açık WhatsApp Web sekmende çalışır.

## Kurulum (bir kez)

Python 3 yeterli (konsol yolu için ek paket gerekmez). Yalnız deneysel CDP yolu ve tarayıcı testleri için: `python -m venv .venv` ve `.venv\Scripts\pip install -r requirements.txt` (ya da `pip install ".[browser]"`).

## Adımlar

1. Hazır JS'yi üret (ayrıca panoya kopyalanır):

   ```
   python wa_web.py snippet --chats "Ali Veli,Örnek Grup"
   python wa_web.py snippet --chats "Ali Veli" --from 2026-01-01 --to 2026-11-14 --max-messages 500 --no-media
   ```

2. Chrome'da giriş yapılmış `web.whatsapp.com` sekmesinde **F12 → Console** (Konsol) sekmesini aç, kodu yapıştır, Enter. Chrome ilk seferde güvenlik için `allow pasting` yazmanı ister: yaz, Enter, sonra tekrar yapıştır.
3. Konsolda `[wa] ...` ilerleme satırlarını ve sayfanın sağ üstündeki yeşil kutudaki sayacı izle (bilgisayarı uyutma; insan hızında kaydırılır). Her 10 dakikada bir (`--checkpoint-minutes N`, `0` = kapalı) o ana kadar toplanan tüm mesajlarla bir ara kayıt parçası iner; sekme kapanır ya da çökerse toplananın tamamı kaybolmaz: `import` en yeni ara kaydı çevirir ve toplamanın eksik olduğunu söyler. Erken bitirmek için yeşil kutudaki **Durdur ve kaydet** düğmesine bas (ya da konsolda `__waCollect.stop()` çalıştır): kaydırma durur, son parça toplananla yazılır. **Paketler indirilmeden önce sekmede mühürlenir**: mesaj metni ve sohbet adı, `snippet`'in ürettiği ve kullanıcı durum klasöründe (inceleme dosyasıyla aynı klasör; İndirilenler'in ve çıktı klasörünün dışı) tuttuğu tek kullanımlık anahtarla şifrelenir; inen dosyalarda okunabilir sohbet metni ve sohbet adı yoktur (`wa-bundle-sealed-<oturum>-001.json`). Fotoğraflar eskisi gibi saklanır. Bitince paket(ler) otomatik inmeye çalışır: **İndirilenler** klasöründe `wa-bundle-sealed-<oturum>-001.json` görünür. Chrome sayfadan indirmeyi engelleyebilir (adres çubuğunda "birden çok dosya indirme" isteminde **İzin ver**'e bas) ya da dosya hiç inmeyebilir; sayfanın sağ üstünde çıkan **yeşil kutudaki bağlantıya** tıkla. O da inmezse aynı kutudaki **"Yeni sekmede indir (yedek)"** düğmesine bas: dosya rastgele bir adla (GUID, uzantısız) iner; `import` onu adına bakmadan, içindeki başlıktan tanır (dosyayı doğrudan yol olarak ver). Küçük sohbetler tek dosyadır; büyükler ~40 MB'lık numaralı parçalara bölünür (`-001`, `-002`, ...).
4. Paketleri Markdown'a çevir (klasör ya da dosyalar verilebilir; aynı sohbetin tüm parçaları birlikte okunur, eksik parça varsa söyler):

   ```
   python wa_web.py import C:\Users\kullanici\Downloads --out C:\Users\kullanici\wa-out
   python wa_web.py import wa-bundle-sealed-abc123-001.json wa-bundle-sealed-abc123-002.json --out C:\Users\kullanici\wa-out
   ```

   Her sohbet için özet satırı yazılır: `[Ad] N mesaj, M medya kopyalandı, K medya eksik -> yol`. `import` mühürlü paketleri kullanıcı durum klasöründeki anahtarla bellekte açar, telefon yoluyla aynı anonimleştiriciyle maskeler; toplaması bitmiş bir sohbetin başarılı dönüştürülmesinden sonra o sohbetin paket dosyalarını (ara kayıtlar dahil; `--keep-bundles` saklar) ve koşunun her sohbeti son parçasını içe aktardığında anahtarı siler (anahtar dosyası koşunun kaç sohbet istediğini tutar, bir sohbetin son parçası da koşunun gerçekte kaç sohbet başlattığını (doğrulanmış olarak) taşır; böylece durdurma ya da bulunamayan sohbet anahtarı sonsuza dek tutmaz; girdide o koşunun dönüştürülmemiş mühürlü paketi duruyorsa ve sohbetlerin yalnız bir kısmını içe aktarırsan da anahtar kalır, `import` hangisi olduğunu söyler; koşu iki sohbet arasında durdurulduysa ya da istenen son sohbet bulunamadıysa bunu hiçbir şey kaydetmez: o koşunun hiç paketi kalmadığında kullanıcı durum klasörünün `keys` klasöründeki dosyayı elle sil): yedekte ya da eşitlenen klasörde kalmış bir paket kopyası artık açılamaz. Bir `snippet` koşusunun tüm paketlerini birlikte (klasörü) ve `snippet`'i çalıştırdığın bilgisayarda ve kullanıcı hesabında içe aktar. Mühür dosyaları diskte korur; `import` çalışana kadar kullanıcı durum klasörünü okuyabilen biri anahtarı da okuyabilir. Hatalı sohbetin paketleri ve son parçası henüz olmayan toplamanın parçaları (klasöre yalnız bir ara kayıt ulaşmışsa) anahtarla birlikte yerinde kalır: son parça inince yeniden içe aktarın. `import` bir klasörü olduğu gibi tarar: eski paketler orada duruyorsa onları da çevirir.

Seçenekler: `--from` / `--to` tarih aralığı, `--max-messages N` en yeni N mesaj, `--no-media` medya indirme, `--no-video` video, gif ve ses mesajlarına dokunma (tıklama yok, medya görüntüleyici açılmaz, hiçbir şey oynamaz ya da inmez; `[video: aktarılmadı]` / `[ses: aktarılmadı]` olarak yazılır; fotoğraflar yalnız sohbette yüklüyse ya da indirme düğmesiyle alınır), `--checkpoint-minutes N` ara kayıt aralığı (varsayılan 10, `0` = kapalı), `--older-from-phone` sohbetin başında "Telefonunuzdaki eski mesajları almak için buraya tıklayın" düğmesine tıkla (varsayılan: tıklama; telefonun açık olması gerekir). `import` da `--from/--to/--max-messages` kabul eder; `import` ve `export` ayrıca `wa2md.py` ile aynı anonim seçeneklerini (`--ek-adlar`, `--inceleme-dizini`, `--sozluksuz`) aynı anlamla kabul eder.

## Deneysel: Chrome'a doğrudan bağlanma (`list` / `export`) — bağlantı doğrulanmadı

```
.venv\Scripts\python wa_web.py list
.venv\Scripts\python wa_web.py export --chats "Ali Veli" --out C:\Users\kullanici\wa-out
```

Aynı `wa_collect.js`'i Playwright ile çalışan Chrome'a bağlanarak çalıştırır ve paketleri doğrudan `import` koduna verir. Toplama başarısız olursa ya da sekme kapanırsa o ana kadar toplananlar (ara kayıtlar) her zamanki gibi maskelenerek dönüştürülür; dönüştürülemeyen parçalar yolu yazılan geçici bir klasörde kalır; **Durdur ve kaydet** yalnız o sohbeti değil, tüm çalışmayı bitirir. Chrome'da `chrome://inspect/#remote-debugging` sayfasında "Bu tarayıcı örneği için uzaktan hata ayıklamaya izin ver" kutusu açık olmalı ve ilk bağlanışta çıkan izin penceresinde **İzin ver**'e tıklanmalı. **Gerçek Chrome'a bağlantı doğrulanmadı**: bakımcının test ortamında, Chrome 157'de, uç nokta WebSocket el sıkışmasını yanıtlamadı (üç deneme zaman aşımı). Betiğin kendi geçici Chrome'unla çalıştığı testlerle gösterilmiştir. Bağlanamazsa komut hata verir ve konsol yolunu önerir.

## Salt okunur, ama okundu bilgisi gider

Toplayıcı hiçbir şey yazmaz, göndermez, tepki vermez, silmez, arşivlemez, sessize almaz, ayar değiştirmez. Yalnızca sohbet arama kutusuna yazar (sonra temizler), sohbeti açar, kaydırır, fotoğraf/gif önizlemesini (medya görüntüleyici) açıp kapatır, uzun metindeki "Devamını oku"yu açar. Ancak **bir sohbeti açmak o sohbetin mesajlarını "okundu" yapar** (karşı tarafa mavi tik gider). Bu yolun doğasında var ve kabul edilmiştir. Sohbet içindeki metinler güvenilmez veri olarak ele alınır; içlerindeki talimatlar yok sayılır.

## Sınırlar

- Fotoğraflar sohbetteki yüklenmiş tam boy görüntüden alınır (WhatsApp Web zaten çözülmüş blob tutar); yüklenmemişse (üzerinde "136 kB" gibi bir boyut ve indirme oku görünür) o indirme okuna tıklanır (~1 sn'de gelir); bu tıklamayla gelmeyen eski fotoğraflar (WhatsApp sunucudan silmiş olabilir) bir daha denenmez ve `_(dosya eksik: ...)_` kalır. Diğer durumlarda medya görüntüleyici açılıp kapatılır. Albümdeki her fotoğraf ayrı dosyadır (`...-1.jpg`, `...-2.jpg`). Gif'ler `.mp4` olarak kaydedilir. Alınamayan fotoğraf Markdown'da `_(dosya eksik: ...)_` olur. Video ve ses **doğrulanmadı** (bu sohbette örneği yoktu); belgeler indirilmez (tarayıcı indirmesi tetiklenir): yer tutucu satır (`_belge indirilemedi: rapor.pdf_`) yazılır.
- Yönlendirilmiş mesajlar `_Yönlendirilmiş mesaj_` notuyla yazılır. Tepkiler (emoji) ve bağlantı önizleme kartları yazılmaz (mesajdaki bağlantı metni yazılır). Kalın/italik biçim işaretleri korunmaz.
- WhatsApp Web yalnızca telefonla senkronlanmış mesajları gösterir. Daha eski mesajlar telefondadır; toplayıcı bunu notla bildirir, düğmeye yalnız `--older-from-phone` ile tıklar.
- Gün başlıkları "BUGÜN/DÜN/hafta günü" ise toplama tarihine göre çözülür. Damgasız (yalnız medya) mesajların saati mesaj alt bilgisinden, tarihi gün başlığından ya da komşu mesajlardan gelir; gönderen adı ekrandaki etiketten, giden mesajda kendi adından alınır.
- WhatsApp arayüzünü sık değiştirir. Tüm seçiciler `wa_collect.js` başındaki `SEL` tablosundadır; her satırda WhatsApp Web arayüzünde gözlemlenerek doğrulandı mı (`[V]`) yoksa doğrulanmadı / tahmin mi (`[U]`) yazar. Bir şey bozulursa önce `SEL`'e bak.
