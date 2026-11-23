# Licences of the bundled data

The code of wa2md (`wa2md.py`, `wa_web.py`, `wa2md_lang/`, `wa2md_assets/`, `tools/`, `tests/`) is under the MIT licence
(`LICENSE`). The dictionary and word-list files in `adlar/` are data, read offline at run time. Rule of this project:
**bundled data is CC0, public domain, or written by this project (MIT). Nothing under GPL, AGPL or a share-alike
licence (CC BY-SA and similar) is copied in.** Each file's header repeats its source, query or method, date and licence.

| File | Entries | Source | Licence |
|---|---|---|---|
| `adlar/tr-adlar.txt` | 2,190 | Wikidata Query Service (given names of Turkish citizens, given-name items), 2026-11-14 | CC0 1.0 |
| `adlar/tr-soyadlar.txt` | 4,819 | Wikidata Query Service (surnames of Turkish citizens, surname items), 2026-11-14 | CC0 1.0 |
| `adlar/tr-yerler.txt` | 984 | Wikidata Query Service (Turkish provinces and districts), 2026-11-15 | CC0 1.0 |
| `adlar/sozcuk-adlar.txt` | 35 lines | this project's own hand-compiled list (file header), 2026-11-14; surname words added 2026-11-23 (#22) | MIT (as the code) |
| `adlar/en-given.txt` | 5,888 | Wikidata Query Service (given names of UK and US citizens), 2026-11-20 | CC0 1.0 |
| `adlar/en-given-more.txt` | 2,513 | Wikidata via the QLever endpoint (given names of citizens of 16 countries), 2026-11-20; filtered with `en-common.txt` and hand-reviewed word lists in `tools/build_en_lists.py` | CC0 1.0 |
| `adlar/en-surnames.txt` | 6,732 | US Census Bureau, Frequently Occurring Surnames from the 2010 Census | public domain (US federal government work, 17 U.S.C. 105) |
| `adlar/en-word-names.txt` | 390 | candidates from Wikidata Lexemes (English lemmas), reviewed by hand for this project | CC0 1.0 source; the selection is MIT (as the code) |
| `adlar/en-places.txt` | 204 | this project's own hand-compiled list of public geographic names | MIT (as the code) |
| `adlar/en-common.txt` | 8,119 | Wikidata Lexemes (English lemmas, CC0) combined with the lower-case word counts of 54 public-domain Project Gutenberg books (ebook numbers in the file header), plus hand-reviewed lists of this project; `tools/build_common_lists.py` | CC0 / public-domain sources; the compiled list is MIT (as the code) |
| `adlar/tr-common.txt` | 43 | this project's own hand-compiled list (everyday Turkish words that are also English given names), `tools/build_common_lists.py` | MIT (as the code) |

Test fixtures under `tests/fixtures/` are synthetic (invented names and numbers); no real chat or person was used.

The Python packages `phonenumbers` (Apache-2.0) and `playwright` are optional extras that are not bundled.
