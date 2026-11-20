# Language packs

Everything in wa2md that depends on a language lives in a **language pack**: the export's own words (system lines,
attachment markers, AM/PM), the name dictionaries, honorifics and titles, contact and filler words, trade-name and
legal-form words, place and listing vocabulary, suffix handling, password and one-time-code keywords, national phone
shapes and identifiers, and every label written into the output. The engine (`wa2md.py`, `wa_web.py`) holds the rules
only; it reads the language data from the active pack and compiles its patterns from it.

Status (issue #2): two packs ship, Turkish (`tr`) and English (`en`). Console and help text are not part of a pack:
they come from the message table `MSG` in `wa2md.py`, selected by `--lang` / `WA2MD_LANG`.

## Layout

```
wa2md_lang/__init__.py   LanguagePack and Labels (the interface), load_pack(), check_pack(), merge(), EXPORT_FIELDS,
                         DEFAULT_PACK, PACKS, NEVER
wa2md_lang/tr.py         PACK = LanguagePack(...) for Turkish, LABELS = Labels(...)
wa2md_lang/en.py         PACK = LanguagePack(...) for English, LABELS = Labels(...)
tools/build_en_lists.py  rebuilds adlar/en-*.txt from the downloaded sources
adlar/                   dictionary files (named by the pack: dictionary_dir + dictionary_files)
```

`pyproject.toml` installs `wa2md_lang` and `adlar` next to the modules, so the same lookups work in a checkout and
after `pip install .`.

## The interface

`wa2md_lang.LanguagePack` is a frozen dataclass; every field is required and documented in the source next to its
declaration. Fields are grouped as follows (the field comments say whether a value is *words*, *key form* or a
*regex*, see the module docstring):

| Group | Fields (examples) | Used by |
|---|---|---|
| letters | `fold_i`, `fold_pairs` | `_key` (case- and accent-insensitive keys), `_name_regex` (per-letter classes) |
| export locale | `ampm`, `pm`, `attach_android`, `attach_ios`, `omitted`, `strip_name`, `system_patterns`, `group_only_patterns`, `system_notice`, `event_words`, `web_*` | parser, system-line and group detection, WhatsApp Web path |
| inflection | `name_suffixes` (ordered optional groups; empty for languages without suffixes) | names with an apostrophe-less suffix |
| trade names and domains | `sector_*`, `legal_*`, `kin`, `firm_func`, `firm_stop`, `hon_base`, `web_tld`, `web_*` | `[firma]` rules and business domains |
| names in context | `honorific_after`, `title_before`, `title_stop`, `contact_words`, `filler_words`, `ordinary_words`, `ordinary_suffix`, `institution_*`, `surname_suffix`, ... | evidence rules (honorific, title, contact field, ordinary-word test, landmarks) |
| listings and routes | `listing_places`, `listing_words`, `route_*`, `place_region_kind` | listing vocabulary, route exception |
| secrets | `secret_keywords*`, `otp_*`, `pin_word`, `units`, `secret_stop`, `code_context` | `[parola]`, `[kod]` |
| phones and identifiers | `phone_glued_words`, `phone_national(b)`, `phone_extension`, `iban`, `national_id`, `plate` | `[telefon]`, `[iban]`, `[tckn]`, `[plaka]` |
| dictionaries | `dictionary_dir`, `dictionary_files` (`given`, `surname`, `ambiguous`, `places`) | `name_lists()`, `places()` |
| labels | `labels: Labels` | every output string |

`Labels` holds the output strings: the chat label (`chat`, with `{n}`), the person label (`person_word` +
`person_sep` + number, neutral label with `unknown_mark`), the masks (`phone company path email user password code
iban national_id plate`), the media file name, the header words, the notes, the attachment-kind names, the
attachment-list file and its status words, the WhatsApp Web notes and the review-file suffix.

`phone_national` is the only hook: a function that receives the engine's building blocks (`b.dl(...)` digit classes,
`b.DG`, `b.GS`, `b.SEP`, `b.DATE_AHEAD`, `b.GLUED`, ...) and returns the national phone alternatives. The engine adds
the universal shapes (`+<8-15 digits>`, `00 <country code> ...`), the pack's `phone_extension` (`ext. 204`, `x204`)
and the common bounds. `b.after(words, links)` builds "right after one of these words" lookbehinds (any case) for
shapes that are only a phone after a phone word.

Phone shapes per pack:

* Turkish: unchanged (0/90/+90 numbers in any grouping, fixed shapes, a mobile glued to a contact word, `(322) ...`).
* English: UK national numbers with a separator (`07700 900123`, `07700-900-123`, `020 7946 0123`,
  `0161 496 0123`, `(0161) 496 0123`, `0800 123 4567`) and an ungrouped mobile (`07700900123`); US/Canada
  `(202) 555-0147`, `202-555-0147`, `202.555.0147`, `1-202-555-0147`; after a phone word (`call`, `tel`, `mobile`,
  `my number is`, `call me on`, ...) also `202 555 0147` and ungrouped `2025550147` / `01619460123`. Never inside a
  word or a link, after a decimal point, before a further digit group or before a unit (`250 300 1500 kg`).
* A digit group inside a phone is never a one-time code (`+44 7700 900789 for the gate code`).
* Optional `phonenumbers` package (`pip install "wa2md[phone]"`, Apache-2.0): when it is installed, a `+`/`00`
  candidate is masked only when the package says a number of that length is possible for that country code
  (`is_possible_number`); national shapes of the packs are always masked. Without the package every candidate is
  masked. The tests that need the package skip when it is absent.

## Selection: which packs and which labels

One rule per decision, applied by `wa2md.select_packs(msgs)` for every chat (phone export and WhatsApp Web path; it
is called by `write_chat` and by `Anonymizer`):

* **Chat-text packs** (names, titles, contact words, trade names, secrets, phones, ids): `--packs`, else
  `WA2MD_PACKS`, else `auto`. `wa2md.detect_packs(msgs)` scores each pack by the share of the word tokens of the chat's
  own messages (system lines excluded) that are in its `stopwords` or contain one of its `detect_chars`
  (`wa2md.pack_scores`); a best score below 0.10 (third language, emoji, media) selects every pack, otherwise every
  pack with a score of at least 0.04 and at least 0.35 x the best score is selected. `stopwords` and `detect_chars`
  must be evidence for this language only: no short word and no letter that another common language shares.
* **Dominant language** (`wa2md._dominant`, set for every chat of several packs, also a pinned set): the pack that
  wins at least 3/4 of at least 6 messages that carry a signal. A given name of another pack that is an ordinary
  word of the dominant pack (`name_lists()['xo'][dominant]`) needs strong evidence there; a capital alone is not.
* **Labels** (`Labels`): the label set of the message language (`--lang`, else `WA2MD_LANG`, else English), i.e. the
  labels of the pack whose code is the language (`wa2md.output_labels()`). Labels never depend on the chat-text packs.
* **Export locale** (`EXPORT_FIELDS`: system lines, attachment and omitted markers, AM/PM, chat-name strip patterns,
  WhatsApp Web dividers): always the union of every shipped pack, whatever the selection, because the phone's
  interface language and the chat's language are independent.

`wa2md_lang.merge(codes, labels=lang)` builds the pack set: words and sets are united, regexes are united by their
top-level alternatives (first pack's text first), dictionary files of every pack are read, `phone_national` hooks
are chained, bool switches are on when any pack needs them. `phone_mobile` (national mobile shapes with their own
guards) is active from EVERY shipped pack whatever the selection; a pack names none when its shape would change
another pack's established output (English: UK mobiles in Turkish chats). A selection whose merge changes nothing (Turkish alone
with Turkish labels) returns the Turkish pack object itself, which is how Turkish output stays byte-identical.
Library callers and tests can pin a pack with `wa2md.use_pack(code_or_pack)`; `wa2md.use_pack(None)` returns to the
per-chat rule.

**Cross-pack ordinary words** (one rule in `wa2md.name_lists()`, only when several packs are merged): each pack may
list its ordinary words in a `common` dictionary file (`adlar/en-common.txt`: Wikidata Lexemes (CC0) and word counts of
public-domain Project Gutenberg books; `adlar/tr-common.txt`: the everyday Turkish words that are also English given
names, hand-compiled; both rebuilt by `tools/build_common_lists.py`, sources and method in the file headers and in
`DATA-LICENSES.md`). `en-common.txt` also feeds two single-pack rules of the English pack (a capitalized ordinary word
after a given name is no surname, a lone ordinary word after a closing phrase is no name), so it is a general
ordinary-word list, not only a list of name collisions. A given name of one selected pack that
is an ordinary word of another selected pack and no given name there becomes a word-name (masked only with context,
like `sozcuk-adlar.txt` / `en-word-names.txt`): with `en` + `tr` 34 English given names (`ben`, `kim`, `kira`, `ara`)
and 9 Turkish given names (`can`, `mine`, `said`). Because the merged set reads lower case as a possible name (the
Turkish `lower_case_context`), a given name of a pack without `lower_case_context` that is an ordinary word of that
same pack stays the word in lower case (`300 miles`), as with that pack alone. A single pack is unaffected.

**Console line:** with `auto`, `write_chat` prints one line per chat with the selected codes and counts
(`Language packs (auto, from the chat text): en - 1 of 2`); an explicit selection prints nothing.

## How the engine uses a pack

* `wa2md._P` is the active pack, `wa2md._L` its labels. Every module-level value derived from pack data is built by a
  function decorated with `@_on_pack`; it runs once at import with `DEFAULT_PACK` and again on every
  `wa2md.use_pack(code_or_pack)`, which also reloads the dictionaries and clears the caches that depend on the pack.
  There is one implementation; a pack only parameterises it.
* Patterns that contain output labels (a label is never a name, a name part joins a neighbouring label, a masked
  phone is evidence, masked hosts in URLs) are built from `Labels` in `_build_label_patterns`, so another label set
  works the same way. `tests/test_language_pack.py` proves it: a synthetic label set gives the Turkish output with
  only the labels replaced.
* `check_pack()` (run by `load_pack()` and `use_pack()`) checks that every field is set, every regex compiles, the
  label masks and attachment kinds are complete and the label templates contain their placeholders.

## Adding a language

1. Copy `wa2md_lang/tr.py` to `wa2md_lang/<code>.py` and replace the data; keep every field (use empty sequences,
   `frozenset()`, or a never-matching regex such as `r"(?!)"` where a language has nothing to say).
2. Add the dictionary files to `adlar/` (one entry per line, `#` comment header with source, licence, retrieval
   date and queries, like the Turkish files) and name them in `dictionary_files`.
3. Add the code to `PACKS` in `wa2md_lang/__init__.py` (and to `LANGS` in `wa2md.py` plus the `MSG` texts if the
   console should speak the language). Give the pack `stopwords` and, if it has any, `detect_chars`, so `auto` can
   choose it. Export-locale fields should repeat strings other packs already have only verbatim (the union is taken
   alternative by alternative).
4. Add tests: the pack contract (`check_pack`) and a decision table for the language's rules (positive and negative
   rows; see `tests/test_nakliye_karar_tablosu.py` for the Turkish one). Do not change expected outputs of the
   Turkish tests: the Turkish pack's output must stay byte-identical.
5. Check the mixed case: run a chat in your language exported from an English phone, and an English chat, with the
   default `--packs auto`.

Licence rule for pack data: no GPL or AGPL material; dictionary sources must allow redistribution (the Turkish lists
are built from Wikidata, CC0).

## Still language-specific inside the engine (known, deliberate)

* The state folder name `inceleme` and the legacy `REVIEW_DIR`: a path (open question 4 of issue #2).
* Rule shapes that only one language uses are pack switches or never-matching fields: `lower_case_context` (Turkish
  on: a lower-case word-name next to a known name is masked), `secret_link` (English `is` between a keyword and its
  value), `contraction_suffixes` (English `'t`: `don't` is not `Don` + suffix), `name_suffixes`, `route_from`/`route_to` (Turkish case suffixes).
* `MSG` and the help text (console layer, both languages in one table).
* The apostrophe written between a label and a closed-list suffix (`Kişi 1'cüm`): only active when a pack has
  `name_suffixes`.
