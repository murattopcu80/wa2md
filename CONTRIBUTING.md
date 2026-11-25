# Contributing to wa2md

Thank you for helping. wa2md converts WhatsApp chats to Markdown and masks personal data, so one rule comes before everything else.

## The one rule: invented data only

**Never put real chat content or real personal data into an issue, a pull request, a test, a fixture or a commit message.** This includes real names, phone numbers, e-mail addresses, IBANs, ID numbers, plates, addresses, screenshots and photos, and also text copied from a real chat that you "cleaned up" by hand.

Use invented data instead:

- people: invented names (the tests use made-up names such as `Velko Darsun` or `Brin Tamsel`);
- phone numbers: the `0500 000 xx xx` family (mobile) and `0322 000 00 xx` (landline); for foreign numbers `+44 7700 900123` (Ofcom drama range);
- e-mail and web addresses: `example.com`, `example.org`, `.example`, `.test`; where a rule needs a registrable `.com` / `.tr` name with a specific word in it, use an obviously invented name such as `ornekfirma-nakliyat.com.tr`;
- accounts and handles: `handle_one`, `example-org`.

All test data and fixtures in this repository are synthetic. A pull request that adds real-looking data will be asked to replace it.

## Running the tests

Python 3.9 or later and the standard library are enough:

```
python -m unittest discover -s tests -v
```

To work on a checkout with the commands on your PATH use `pip install -e .`. The browser tests (`tests/test_browser_smoke.py`) are skipped unless the optional `browser` extra (`pip install ".[browser]"`, Playwright) and a Chrome are installed; the rest of the suite does not need them. The suite must pass on Linux, Windows and macOS; the continuous integration runs it on all three.

## Reporting a missed or wrongly masked item

Use the "Anonymization miss or over-masking" issue form. Give the smallest invented example that shows the problem:

1. one or a few lines of an invented chat export (for example `14.11.2026 10:00 - Ali Veli: arayın 0500 000 11 22`);
2. the command you ran;
3. what you expected and what the output shows.

If personal data is left unmasked in a form that the README says is masked, treat it as a security problem and follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Changing the code

- Keep a change small and focused, and add a test that fails without it. Tests that check masking go next to the existing ones in `tests/`; a masking rule that has a decision-table row in `tests/test_nakliye_karar_tablosu.py` gets a new row there.
- Behaviour that the README documents changes together with the README (`README.md`, `README.tr.md` and the topic pages in `docs/` and `docs/tr/`).
- The anonymizer's language-specific parts live in language packs (`wa2md_lang/`, issue #2); see [docs/language-packs.md](docs/language-packs.md) for the interface and how to add a language. Please talk to the maintainers in that issue before a large change to the detection code.

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`, for example `fix(anonymize): mask a number written with thin spaces` or `docs: explain --review-dir`. Types in use: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`. Write the message in English, one logical change per commit, and reference the issue (`refs #12` or `closes #12`).

## Pull requests

Describe what changed and why, and tick the checklist in the pull request template. By contributing you agree that your contribution is licensed under the MIT license of this repository (`LICENSE`).

## Conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
