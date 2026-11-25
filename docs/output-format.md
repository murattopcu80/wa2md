[README](../README.md) | **English** | [Türkçe](tr/output-format.md)

# Output format

Output: `<out>/<chat-name>/<chat-name>.md` and `<out>/<chat-name>/media/`. The output is anonymized by default: names are replaced by `Chat-N` / `Person N` (with `--lang tr` the Turkish labels `Sohbet-N` / `Kişi N`; see [Language support](language-support.md) and [Anonymization](anonymization.md); turn it off with `--no-anonymize`). The folders with real names in the examples on the [WhatsApp Web](whatsapp-web.md) and [phone export](phone-export.md) pages are produced with `--no-anonymize`. **Media is copied by default, also in anonymous mode, and it is not anonymized**; add `--no-media` for output that you will share (a console warning line reminds you whenever media was copied).

Day heading `## YYYY-MM-DD`, message `**Name** HH:MM`, photo `![](media/file.jpg)`, other files as links, system notes in italics, quoted reply as a `> ` line. On the Web path the media name is `<YYYYMMDD-HHMM>-<short message id>[-n].<extension>`.
