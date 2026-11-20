# Language packs

Everything in wa2md that depends on a language lives in a **language pack**: the export's own words (system lines,
attachment markers, AM/PM), the name dictionaries, honorifics and titles, contact and filler words, trade-name and
legal-form words, place and listing vocabulary, suffix handling, password and one-time-code keywords, national phone
shapes and identifiers, and every label written into the output. The engine (`wa2md.py`, `wa_web.py`) holds the rules
only; it reads the language data from the active pack and compiles its patterns from it.

Status (issue #2): the interface and the Turkish pack exist; Turkish is the only shipped pack and the default. The
English pack is the next step. Console and help text are not part of a pack: they come from the message table `MSG`
in `wa2md.py`, selected by `--lang` / `WA2MD_LANG`.

## Layout

```
wa2md_lang/__init__.py   LanguagePack and Labels (the interface), load_pack(), check_pack(), DEFAULT_PACK, PACKS
wa2md_lang/tr.py         PACK = LanguagePack(...) for Turkish, LABELS = Labels(...)
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
| phones and identifiers | `phone_glued_words`, `phone_national(b)`, `iban`, `national_id`, `plate` | `[telefon]`, `[iban]`, `[tckn]`, `[plaka]` |
| dictionaries | `dictionary_dir`, `dictionary_files` (`given`, `surname`, `ambiguous`, `places`) | `name_lists()`, `places()` |
| labels | `labels: Labels` | every output string |

`Labels` holds the output strings: the chat label (`chat`, with `{n}`), the person label (`person_word` +
`person_sep` + number, neutral label with `unknown_mark`), the masks (`phone company path email user password code
iban national_id plate`), the media file name, the header words, the notes, the attachment-kind names, the
attachment-list file and its status words, the WhatsApp Web notes and the review-file suffix.

`phone_national` is the only hook: a function that receives the engine's building blocks (`b.dl(...)` digit classes,
`b.DG`, `b.GS`, `b.SEP`, `b.DATE_AHEAD`, `b.GLUED`, ...) and returns the national phone alternatives. The engine adds
the universal shapes (`+<8-15 digits>`, `00 <country code> ...`) and the common bounds.

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
3. Add the code to `PACKS` in `wa2md_lang/__init__.py`.
4. Add tests: the pack contract (`check_pack`) and a decision table for the language's rules (positive and negative
   rows; see `tests/test_nakliye_karar_tablosu.py` for the Turkish one). Do not change expected outputs of the
   Turkish tests: the Turkish pack's output must stay byte-identical.
5. Selecting the pack from the command line (`--packs`, automatic detection) and English output labels by default
   are later steps of issue #2; until then a pack is selected in code with `wa2md.use_pack("<code>")`.

Licence rule for pack data: no GPL or AGPL material; dictionary sources must allow redistribution (the Turkish lists
are built from Wikidata, CC0).

## Still language-specific inside the engine (known, deliberate)

* Internal ids of statistics, origins and review reasons (`"sözlük"`, `"hitap"`, `"gönderen"`, ...). They are not
  output labels but keys; their console display comes from `MSG` / `STAT_LABEL`. Renaming them changes assertions of
  existing tests and is planned together with the switch of the default labels.
* The state folder name `inceleme` and the legacy `REVIEW_DIR`: a path, renamed in the label switch step.
* `MSG` and the help text (console layer, both languages in one table).
* The apostrophe written between a label and a closed-list suffix (`Kişi 1'cüm`): only active when a pack has
  `name_suffixes`.
