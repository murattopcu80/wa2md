[README](../../README.tr.md) | [English](../output-format.md) | **Türkçe**

# Çıktı biçimi

Çıktı: `<out>/<sohbet-adı>/<sohbet-adı>.md` ve `<out>/<sohbet-adı>/media/`. Varsayılan olarak anonimleştirilir: adlar yerine varsayılan olarak `Chat-N` / `Person N`, `--lang tr` ile `Sohbet-N` / `Kişi N` yazılır (bkz. [Dil desteği](language-support.md) ve [Anonimleştirme](anonymization.md); kapatmak için `--no-anonim`). [WhatsApp Web](whatsapp-web.md) ve [telefon dışa aktarması](phone-export.md) sayfalarındaki örneklerdeki gerçek adlı klasörler `--no-anonim` ile oluşur. **Medya varsayılan olarak, anonim modda da kopyalanır ve anonimleştirilmez**; paylaşacağın çıktıda `--medya-yok` kullan (medya kopyalandığında konsol her seferinde bir uyarı satırı yazar).

Gün başlığı `## YYYY-MM-DD`, mesaj `**Ad** HH:MM`, fotoğraf `![](media/dosya.jpg)`, diğer dosyalar bağlantı, sistem notları italik, alıntılı yanıt `> ` satırı. Web yolunda medya adı `<YYYYAAGG-SSDD>-<kısa mesaj kimliği>[-n].<uzantı>`.
