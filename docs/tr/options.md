[README](../../README.tr.md) | [English](../options.md) | **Türkçe**

# Seçenek adları ve konsol dili

Her seçeneğin İngilizce birincil adı vardır. Eski Türkçe adlar **takma ad olarak** kabul edilir: aynı hedef, aynı varsayılan, aynı davranış (var olan komutlar çalışmaya devam eder). Bu README'de Türkçe adlar kullanılır; ikisi de geçerlidir.

| İngilizce (birincil) | Türkçe takma ad | Açıklama | Hangi komut |
|---|---|---|---|
| `--no-media` | `--medya-yok` | medyayı çıktıya koyma | `wa2md.py`; `wa_web.py snippet/import/export` |
| `--copy-documents` | `--belgeleri-kopyala` | anonim modda görüntü/video/ses dışındaki ekleri de kopyala | `wa2md.py` |
| `--extra-names` | `--ek-adlar` | yedek ad listesi (`"Ad Soyad,Takma"` ya da `@dosya`) | `wa2md.py`; `wa_web.py import/export` |
| `--review-dir` | `--inceleme-dizini` | şüpheli kalan sözcükler dosyasının klasörü | `wa2md.py`; `wa_web.py import/export` |
| `--no-dictionary` | `--sozluksuz` | ad sözlüğü/yer listesi eksikken de çalış | `wa2md.py`; `wa_web.py import/export` |
| `--anonymize` / `--no-anonymize` | `--anonim` / `--no-anonim` | anonimleştirme (varsayılan AÇIK) | `wa2md.py`; `wa_web.py import/export` |
| `--lang en\|tr` | (yeni) | yardım, konsol iletileri ve çıktı etiketlerinin dili | her ikisi (alt komutlardan sonra da verilebilir) |
| `--packs auto\|en\|tr\|en,tr` | (yeni) | sohbet metninde ad aramak için dil paketleri (varsayılan `auto`) | her ikisi |

Zaten İngilizce olanlar değişmedi: `--out`, `--only`, `--from`, `--to`, `--name`, `--chats`, `--max-messages`, `--older-from-phone`, `--user-data-dir`.

**Konsol dili:** yardım metni, konsol ve hata iletileri (ve inceleme dosyasının başlığı) varsayılan olarak İngilizcedir. Türkçe için `--lang tr` ya da ortam değişkeni `WA2MD_LANG=tr` (öncelik: `--lang`, sonra `WA2MD_LANG`, sonra İngilizce; bilinmeyen `WA2MD_LANG` değeri yok sayılır). Tarayıcı konsolundaki `[wa]` satırları ve yeşil kutu da aynı dili kullanır (dil `snippet` ile koda gömülür). Python'un kendi `argparse` metinleri (`usage:`, `error:`) çevrilmez. Aynı anahtar çıktıdaki etiketleri de seçer (bkz. [Dil desteği](language-support.md)). Aşağıdaki bölümlerde alıntılanan konsol çıktıları `--lang tr` ile görülen Türkçe iletilerdir.
