[README](../README.md) | **English** | [Türkçe](tr/data-sources.md)

# Data sources and attribution

The dictionaries in the `adlar/` folder are plain text files that ship with the tool and are read offline (nothing is downloaded at run time):

| File | Content | Source and how it was built | Retrieved |
|---|---|---|---|
| `tr-adlar.txt` | Turkish given names | Wikidata Query Service: given names of Turkish citizens that occur at least twice, plus Turkish given-name items; two names removed by hand | 2026-11-14 |
| `tr-soyadlar.txt` | Turkish surnames | Wikidata Query Service: surnames of Turkish citizens that occur at least twice, plus Turkish surname items | 2026-11-14 |
| `tr-yerler.txt` | Turkish provinces and districts | Wikidata Query Service: province and district items, primary label, cleaned (suffixes and brackets removed) | 2026-11-15 |
| `sozcuk-adlar.txt` | names that are also ordinary words (masked only with context) | Wikidata lexemes and place names (CC0 1.0) plus a hand-compiled part written for this project (MIT, as the code) | 2026-11-14 / 2026-11-15 |
| `en-given.txt` | English given names (5,888) | Wikidata Query Service: given names of UK and US citizens held by at least 5 people (English labels); function words, titles, month/day names and names of listed places removed (`tools/build_en_lists.py`), CC0 1.0 | 2026-11-20 |
| `en-surnames.txt` | US surnames (6,732) | US Census Bureau, *Frequently Occurring Surnames from the 2010 Census* (surnames with at least 5,000 bearers); public domain (work of the US federal government) | 2026-11-20 |
| `en-word-names.txt` | English names that are also ordinary words (371) and Turkish names that are common English words (19) | candidates: given names that are lower-case English lemmas in Wikidata Lexemes (CC0 1.0); reviewed by hand for this project (MIT, as the code) | 2026-11-20 |
| `en-places.txt` | regions (US states, UK nations, Canadian provinces, Australian states, countries) and 104 large cities | hand-compiled for this project from public geographic names (MIT, as the code) | 2026-11-20 |
| `en-given-more.txt` | given names of more origins (2,513; Moroccan, Nigerian, Chinese, Spanish, Polish, Indian, Pakistani, ... citizens) | Wikidata (QLever endpoint): given names held by at least 5 citizens of each listed country (English labels); names of `en-given.txt`, ordinary English words and places removed (`tools/build_en_lists.py`), CC0 1.0 | 2026-11-20 |
| `en-common.txt` | ordinary English words (8,119): used by the surname, sign-off and lower-case rules of the English pack and by the cross-pack rule | Wikidata Lexemes (CC0 1.0): lower-case English lemmas; combined with the lower-case word counts of 54 public-domain Project Gutenberg books (a word must occur in at least 30% of them) and a hand-reviewed list of irregular forms and present-day words (`tools/build_common_lists.py`); compiled for this project (MIT, as the code); nothing share-alike | 2026-11-20 |
| `tr-common.txt` | everyday Turkish words that are also English given names (43): used by the cross-pack rule | hand-compiled for this project (MIT, as the code) by reading through the given-name dictionaries and the Turkish word lists of the project's own rules (`tools/build_common_lists.py`) | 2026-11-20 |

Licence: Wikidata's structured data is CC0 1.0 (public domain, https://www.wikidata.org/wiki/Wikidata:Licensing); the hand-compiled part of `sozcuk-adlar.txt`, the hand review of `en-word-names.txt` and `en-places.txt` are under the licence of this repository; the US Census surname file is public domain; `en-common.txt` and `tr-common.txt` are compiled for this project from CC0 / public-domain sources and hand review (see the table). No file under `adlar/` is under a share-alike licence. The per-file list with source and licence is in `DATA-LICENSES.md`. `tools/build_en_lists.py` rebuilds the English files from the downloaded sources. The exact queries, the filters, the counts and the manual removals are written in the comment lines at the top of each file, so the lists can be rebuilt. The lists are best-effort: they contain no private data, but they are neither complete nor error-free (see [Limitations and responsible use](../README.md#limitations-and-responsible-use)).

**All test data and fixtures in this repository are synthetic** (invented names, numbers from the reserved `0500 000 xx xx` family, `example.*` and `.test` addresses); no real chat or real person was used.

The name, surname, word-name and place lists in the `adlar/` folder were compiled from Wikidata (https://www.wikidata.org) with the Wikidata Query Service. Wikidata's structured data is under CC0 1.0 (public domain): https://www.wikidata.org/wiki/Wikidata:Licensing. The retrieval dates and the queries used are written at the top of each file (`tr-adlar.txt` and `tr-soyadlar.txt`: 2026-11-14; `tr-yerler.txt` and `sozcuk-adlar.txt`: 2026-11-15).
