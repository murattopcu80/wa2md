# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once it has a stable release.

## [Unreleased]

### Added

- Initial public release: converts WhatsApp chat exports (phone export zip or folder, and the WhatsApp Web collector path through `wa_web.py`) to Markdown with media; anonymization of direct identifiers is on by default (person names, phone numbers, e-mail addresses, IBAN, national ID numbers, plates, trade names, domain names, usernames, passwords and one-time codes), with an offline name and place dictionary built from Wikidata (CC0 1.0).
- English as the primary language ([#1](../../issues/1)): English `README.md` and Turkish `README.tr.md`; English option names with the Turkish names kept as aliases (`--no-media`/`--medya-yok`, `--copy-documents`/`--belgeleri-kopyala`, `--extra-names`/`--ek-adlar`, `--review-dir`/`--inceleme-dizini`, `--no-dictionary`/`--sozluksuz`, `--anonymize`/`--anonim`); English console and help messages by default, Turkish with `--lang tr` or `WA2MD_LANG=tr`; a console warning when media is copied in anonymous mode.
- Community files: security policy, contributing guide, code of conduct, issue forms and a pull request template.

### Changed

- The output labels (`Sohbet-N`, `Kişi N`, `[telefon]`, ...) are still Turkish; language packs are planned in [#2](../../issues/2).
- Test data uses reserved example numbers and names only.

[Unreleased]: ../../commits/main
