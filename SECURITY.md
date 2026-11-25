# Security policy

## Supported versions

wa2md has no stable release yet. Security fixes are made on the `main` branch.

## What counts as a vulnerability here

wa2md handles private chats and its main purpose is to remove personal data from them. Besides the usual kinds of vulnerability (for example code execution or path traversal when reading a crafted export or bundle, or writing outside the output folder), **for this tool a vulnerability also includes personal data that is left unmasked contrary to the documented behaviour**: for example a phone number, e-mail address, IBAN, national ID number or a participant name in a form that the README says is masked, but that appears in the output; or a way to make the tool print or store the mapping between real names and labels.

Best-effort misses that the README and [docs/anonymization.md](docs/anonymization.md) list under "What this tool does not find automatically" are not vulnerabilities; please report them as an "Anonymization miss or over-masking" issue instead (that form is public, so use invented data only).

## How to report

Report privately through GitHub's private vulnerability reporting: open the **Security** tab of this repository and choose **Report a vulnerability** ([direct link](../../security/advisories/new)). Please do not open a public issue for a vulnerability.

**Never send real chat content or real personal data**, not even in a private report. Reproduce the problem with invented data (invented names, numbers in the reserved `0500 000 xx xx` range, `example.com` / `.test` addresses) and describe the smallest input that shows it, for example one line of an invented chat export.

A report is most useful when it contains: the version or commit, the command that was run, the invented input line(s), the output you expected and the output you got.

## What to expect

Reports are handled by the maintainers on a best-effort basis. You will get an answer in the private report, and a fix and an advisory are published together when the problem is confirmed. Please keep the details private until then.
