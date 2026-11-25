[README](../../README.tr.md) | [English](../phone-export.md) | **Türkçe**

# 2. Telefondan dışa aktarma (alternatif)

1. WhatsApp'ta sohbeti aç.
2. Android: sağ üst **⋮** → **Diğer** → **Sohbeti dışa aktar**. iOS: üstteki kişi/grup adına dokun → **Sohbeti Dışa Aktar**.
3. **Medyayı dahil et** seçeneğini seç.
4. Çıkan zip dosyasını bilgisayara aktar (e-posta, Drive, kablo vb.).

Not: WhatsApp dışa aktarmayı sınırlar. Medyalı yaklaşık 10.000, medyasız yaklaşık 40.000 son mesaj aktarılır. Daha eski mesajlar dosyada olmaz.

```
python wa2md.py <girdi> [<girdi>...] --out <klasör> [--only "ad1,ad2"] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--name AD]
               [--medya-yok] [--belgeleri-kopyala] [--ek-adlar "Ad Soyad,Ad2" | --ek-adlar @adlar.txt]
               [--inceleme-dizini KLASÖR] [--sozluksuz] [--no-anonim] [--lang tr|en]
```

Girdi: zip dosyası, açılmış klasör veya birden çok zip içeren klasör. Sadece Python 3 gerekir (ek paket yok).

```
python wa2md.py "C:\Users\kullanici\Downloads\WhatsApp Chat with Ali Veli.zip" --out C:\Users\kullanici\wa-out
python wa2md.py C:\Users\kullanici\exports --out C:\Users\kullanici\wa-out --only "ali,veli" --from 2026-01-01 --to 2026-11-14
```

Girdi dosyalarına dokunulmaz; tekrar çalıştırınca sadece kendi `.md` dosyası yazılır, aynı boyuttaki medya atlanır.
