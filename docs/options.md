[README](../README.md) | **English** | [Türkçe](tr/options.md)

# Option names and console language

Every option has an English primary name. The old Turkish names are accepted as **aliases**: same destination, same default, same behaviour (existing commands keep working).

| English (primary) | Turkish alias | Meaning | Command |
|---|---|---|---|
| `--no-media` | `--medya-yok` | leave media out of the output | `wa2md.py`; `wa_web.py snippet/import/export` |
| `--no-video` | `--video-yok` | do not open, play or download video, gif or audio messages (no sound); written as `[video: not exported]`; photos kept | `wa_web.py snippet/export` |
| `--copy-documents` | `--belgeleri-kopyala` | when anonymizing, also copy attachments other than image/video/audio (the web collector saves documents either way; this decides whether they are copied into the output) | `wa2md.py`, `wa_web.py import/export` |
| `--extra-names` | `--ek-adlar` | backup name list (`"First Last,Nickname"` or `@file`) | `wa2md.py`; `wa_web.py import/export` |
| `--review-dir` | `--inceleme-dizini` | folder of the suspect-remaining words file | `wa2md.py`; `wa_web.py import/export` |
| `--no-dictionary` | `--sozluksuz` | run even if the name dictionary / place list is missing | `wa2md.py`; `wa_web.py import/export` |
| `--anonymize` / `--no-anonymize` | `--anonim` / `--no-anonim` | anonymization (default ON) | `wa2md.py`; `wa_web.py import/export` |
| `--lang en\|tr` | (new) | language of help, console messages and output labels | both (also accepted after a sub-command) |
| `--packs auto\|en\|tr\|en,tr` | (new) | language packs for finding names in the chat text (default `auto`) | both |

These were already English and did not change: `--out`, `--only`, `--from`, `--to`, `--name`, `--chats`, `--max-messages`, `--older-from-phone`, `--user-data-dir`.

**Console language:** help text, console messages and error messages (and the header of the review file) are English by default. For Turkish use `--lang tr` or the environment variable `WA2MD_LANG=tr` (precedence: `--lang`, then `WA2MD_LANG`, then English; an unknown `WA2MD_LANG` value is ignored). The `[wa]` lines in the browser console and the green box use the same language (the language is baked into the snippet by `snippet`). Python's own `argparse` texts (`usage:`, `error:`) are not translated. The same switch selects the labels inside the output (see [Language support](language-support.md)). The console lines quoted in this README are the English messages.
