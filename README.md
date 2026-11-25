**English** | [Türkçe](README.tr.md)

# wa2md

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml) ![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg) ![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)

> **Unofficial tool.** wa2md is an independent open-source project. It is not affiliated with, endorsed by or connected to WhatsApp or Meta. "WhatsApp" is used here only to name the chat format and the web page that the tool reads.

> **Read the ENTIRE output before you share it.** Anonymization here is heuristic: it removes direct identifiers and misses things (see [What this tool does not find automatically](docs/anonymization.md)). The review file is a help, not a guarantee. **Pictures, videos and voice notes are copied as they are and are NOT anonymized** (faces, ID documents, bank cards, screenshots with names): use `--no-media` before sharing.

Converts WhatsApp chats (one-to-one or group) to Markdown files with the photos embedded, and anonymizes them by default. There are two input paths; both use the same Markdown writer (`wa2md.write_chat`), so the output format is the same. The tool uses only the Python standard library. Output layout and format: [docs/output-format.md](docs/output-format.md).

## Quick start

```
python wa2md.py "C:\Users\user\Downloads\WhatsApp Chat with Ali Veli.zip" --out C:\Users\user\wa-out
```

The output is anonymized by default. You need Python 3.9 or later and nothing else.

**Before you share anything:** pictures, videos and voice notes are copied into `media/` **as they are and are NOT anonymized** (faces, ID documents, bank cards, screenshots with names). Run with `--no-media` to leave them out, and read the entire Markdown output yourself:

```
python wa2md.py "C:\Users\user\Downloads\WhatsApp Chat with Ali Veli.zip" --out C:\Users\user\wa-out --no-media
```

## Input paths

1. **WhatsApp Web (recommended):** no export step on the phone. A JavaScript collector (`wa_collect.js`) runs in a logged-in WhatsApp Web tab; `wa_web.py import` turns its result into Markdown. Setup, steps, limits and the read-receipt note: [docs/whatsapp-web.md](docs/whatsapp-web.md).
2. **Phone export (alternative):** converts WhatsApp's own "Export chat" zip or folder with `wa2md.py`. Details: [docs/phone-export.md](docs/phone-export.md).

## Anonymization

On by default (turn it off with `--no-anonymize`). Names, phone numbers, e-mail addresses, links, secrets and similar direct identifiers are replaced by labels such as `Chat-N`, `Person N` and `[phone]`, and a review file lists suspicious words that stayed in the text. It is heuristic and best-effort: it does not make a chat anonymous in the legal sense, it misses things, and media is never anonymized. What it masks, what it does not find and how to review the result: [docs/anonymization.md](docs/anonymization.md).

## Language support

English is the primary language and Turkish is a supported language. `--lang en|tr` selects console messages and output labels; `--packs auto|en|tr|en,tr` selects the language packs used to find names in the chat text. Details, limits of the English rules and how to add a language: [docs/language-support.md](docs/language-support.md), [docs/language-packs.md](docs/language-packs.md). All options and their Turkish aliases: [docs/options.md](docs/options.md).

## Running blind for an AI agent

An AI agent can run `python wa2md.py <input-folder> --out <output-folder>/<YYYYMMDD-HHMM>` on real exports without learning who is who: the console shows only labels and numbers, a new output folder is used on every run, and `--no-anonymize` is for the owner only. The limits of this protection (photos, `wa_web.py list`) are in [docs/blind-run.md](docs/blind-run.md).

## Limitations and responsible use

- **Detection is best-effort.** Anonymization here is heuristic (dictionaries, patterns and context rules). It removes direct identifiers; it does not make a chat anonymous in the legal sense, and no anonymizer finds everything. Names that are not in the dictionaries, unusual spellings, nicknames, places, job titles, and details that identify a person only in combination will be missed, and ordinary words are sometimes masked by mistake.
- **Read the entire output before you share it.** The review file lists suspicious words that stayed in the text; it is a help, not a guarantee.
- **Media is not anonymized.** Photos, videos and voice notes are copied as they are (faces, documents, screenshots); use `--no-media` for anything you share.
- **Use it only on chats you are entitled to process.** Make sure that you and the other participants are fine with the conversion, and keep the originals, the raw `wa-bundle-*.json` files and the output as safe as the original chat.
- **Report misses with invented examples only.** See [CONTRIBUTING.md](CONTRIBUTING.md); a way to leave personal data unmasked contrary to the documented behaviour is a security problem ([SECURITY.md](SECURITY.md)).

## Install (optional)

`python wa2md.py ...` works straight from a checkout. To get commands on your PATH instead, install from the checkout (Python 3.9 or later, no third-party dependency):

```
pip install .
wa2md --help        # same as python wa2md.py
wa2md-web --help    # same as python wa_web.py (WhatsApp Web helper)
```

The dictionaries (`adlar/`) and the collector (`wa2md_assets/wa_collect.js`) are installed with it and found at run time. The experimental direct Chrome connection (`wa2md-web list` / `export`) needs the optional extra: `pip install ".[browser]"` (Playwright). Nothing is published to PyPI.

## Tests

```
python -m unittest discover -s tests -v
.venv\Scripts\python -m unittest discover -s tests -v
```

The second (venv) also runs the real-Chrome tests: it runs `wa_collect.js` in a real (headless) Chrome on invented fixtures that imitate the real WhatsApp Web DOM structure; it also starts its own temporary Chrome with a separate profile and tries the CDP `list`/`export` flow on a fake WhatsApp page. It does not touch your Chrome. If there is no venv/Chrome those tests are skipped.

## Privacy

`exports/`, `out/`, `*.zip`, `wa-bundle-*.json` and `.venv/` are listed in `.gitignore`. That lowers the risk of committing chat data but does not remove it: other folders and file names are not covered, and `git add -f` overrides it. Check `git status` and the contents before every commit and push. The test data and fixtures are synthetic (see [Data sources and attribution](docs/data-sources.md)).

## License

The code is under the MIT license (see `LICENSE`). This license applies only to the code; the data files under `adlar/` are separate (see [docs/data-sources.md](docs/data-sources.md) and `DATA-LICENSES.md`: every data file is CC0, public domain or this project's own work under MIT).

## Data sources and attribution

The name, surname, word-name and place dictionaries in `adlar/` ship with the tool, are read offline and were compiled from Wikidata (CC0 1.0), the US Census (public domain) and hand review for this project; no file is under a share-alike licence. All test data and fixtures are synthetic. The per-file table, licences and retrieval dates: [docs/data-sources.md](docs/data-sources.md).

## More documentation

- [docs/whatsapp-web.md](docs/whatsapp-web.md), [docs/phone-export.md](docs/phone-export.md): the two input paths
- [docs/anonymization.md](docs/anonymization.md): what is masked and what is not found
- [docs/language-support.md](docs/language-support.md), [docs/language-packs.md](docs/language-packs.md), [docs/options.md](docs/options.md): languages, packs, option names
- [docs/blind-run.md](docs/blind-run.md), [docs/output-format.md](docs/output-format.md), [docs/data-sources.md](docs/data-sources.md)
- Turkish versions of these pages (except `language-packs.md`): `docs/tr/<same name>.md`
