# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once it has a stable release.

## [Unreleased]

### Added

- Initial public release: converts WhatsApp chat exports (phone export zip or folder, and the WhatsApp Web collector path through `wa_web.py`) to Markdown with media; anonymization of direct identifiers is on by default (person names, phone numbers, e-mail addresses, IBAN, national ID numbers, plates, trade names, domain names, usernames, passwords and one-time codes), with an offline name and place dictionary built from Wikidata (CC0 1.0).
- English as the primary language ([#1](../../issues/1)): English `README.md` and Turkish `README.tr.md`; English option names with the Turkish names kept as aliases (`--no-media`/`--medya-yok`, `--copy-documents`/`--belgeleri-kopyala`, `--extra-names`/`--ek-adlar`, `--review-dir`/`--inceleme-dizini`, `--no-dictionary`/`--sozluksuz`, `--anonymize`/`--anonim`); English console and help messages by default, Turkish with `--lang tr` or `WA2MD_LANG=tr`; a console warning when media is copied in anonymous mode.
- Community files: security policy, contributing guide, code of conduct, issue forms and a pull request template.
- Language packs ([#2](../../issues/2)): the engine reads every language-specific word, pattern and label from a pack (`wa2md_lang/`); Turkish (`tr`) and English (`en`) packs ship.
- English pack: English given names (Wikidata, CC0), US surnames (US Census 2010, public domain), English names that are also ordinary words (masked only with context), titles (`Mr`, `Mrs`, `Dr`, ...), contact words, English trade names and legal forms (`Ltd`, `Inc`, `LLC`, ...), password and one-time-code words, UK/Irish IBAN, month and day names, a place list; `tools/build_en_lists.py` rebuilds the lists. Not yet included: US/UK national ids and card numbers.
- Phones: UK and US/Canada national shapes in the English pack (ungrouped and space-only shapes only after a phone word), extensions, guards against dates, times, prices, measures, versions, coordinates, tracking and card-like numbers; optional `phonenumbers` validation of `+`/`00` candidates (`pip install "wa2md[phone]"`).
- Given names of more origins (`adlar/en-given-more.txt`, Wikidata, CC0) and ordinary-word lists per pack (`adlar/en-common.txt`: Wikidata Lexemes (CC0) and public-domain Project Gutenberg word counts; `adlar/tr-common.txt`: hand-compiled for this project; no share-alike data) for the cross-pack rule: with several packs, a given name of one pack that is an ordinary word of another is a word-name (`ben`, `kim` stay in a Turkish sentence; `Ben called` is masked).
- A console line per chat with the automatically selected packs.
- `--packs auto|en|tr|en,tr` and `WA2MD_PACKS`: packs used to find names in the chat text; `auto` (default) chooses per chat from the chat's own messages. The export's system lines and markers are always read with every pack.

- Review of a65d79e ([#2](../../issues/2)): automatic selection counts only language-only evidence and selects every pack below a 10 % score (third-language chats); in a chat one language clearly dominates, a name of the other pack that is an ordinary word of the dominant language needs strong evidence; surnames after an English given name in short and multi-name lines, possessives, hyphenated/apostrophe surnames, an initial before a listed surname, `Limited` alone and two-line signatures are masked; Turkish mobile numbers are masked with every selection; an IBAN of any country is masked whole as `[iban]` (mod-97 check); an invalid `WA2MD_PACKS` value is a usage error.

### Changed

- **Output labels are English by default** and follow `--lang` / `WA2MD_LANG`: `Chat-N`, `Person N`, `[phone]`, `[company]`, `[path]`, `[email]`, `[user]`, `[password]`, `[code]`, `Participants:`, `attachments.md`, `Chat-N-suspect-names.txt`. **To keep the previous Turkish labels (`Sohbet-N`, `Kişi N`, `[telefon]`, ...) use `--lang tr` or `WA2MD_LANG=tr`**; with `--packs tr --lang tr` the Markdown output is byte-identical to the previous version except that an IBAN of any country is now masked whole as `[iban]`.
- Internal statistics and review-reason ids are English (`dictionary`, `honorific`, `place_unclear`, ...); the console shows them in the selected language as before.
- Test data uses reserved example numbers and names only.

### Fixed

- Turkish: a surname that is also an everyday word (`Açık`, `Beyaz`, `Kısa`, ...) and was found once next to an honorific (`Açık Bey`) no longer turns every ordinary use (`kapı açık`) into a person label; 44 such words were added to the word-name list `adlar/sozcuk-adlar.txt` ([#22](../../issues/22)).

[Unreleased]: ../../commits/main
