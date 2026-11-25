[README](../README.md) | **English** | [Türkçe](tr/blind-run.md)

# Running blind for an AI agent

Aim: an AI agent runs the script on real exports without learning who is who.

1. Put the phone-export zips in an **input folder** chosen by the owner. The agent is given only the path of this folder; the agent does not list or open the folder (file names contain person names).
2. The agent runs only this one command; a new **output folder** is used on every run, because the `Chat-N` labels (`Sohbet-N` with `--lang tr`) are positional:

   ```
   python wa2md.py <input-folder> --out <output-folder>/<YYYYMMDD-HHMM>
   ```

   It works on Windows, Linux and macOS; **Python 3.9 or later** and only the standard library are enough (the 3.9 lower bound comes from `argparse.BooleanOptionalAction`; the script parses as syntax on 3.8 too, but the `--anonymize`/`--anonim` flag needs 3.9). No venv/Playwright is **needed** for `wa2md.py`; only the experimental `list`/`export` of the WhatsApp Web path and the browser tests need Playwright. Since the output labels contain Turkish characters, the script forces stdout/stderr to UTF-8 (it does not crash on an ASCII console either).

3. What the agent sees: on the console only labels and numbers (summary counts included) (`[Chat-1] N messages, M media ... -> path`, failed inputs as `input N`; no name, zip/file name, phone, message text or unparsable lines are printed), then only the anonymous Markdown in the `Sohbet-N` folders. The review file (written outside the output folder, in the user state folder, see "End-of-run summary" in [Anonymization](anonymization.md)) contains possible real names: the agent does not open it, only you look.
4. `--no-anonymize` is **for you only** (it produces non-anonymized normal output with real names and detailed error diagnosis); it is not given to the agent. In anonymized mode there is no flag that shows or stores the mapping.

Limit: this protects only the console and the output files. Photos are not anonymized (the agent must not carry a name over from an image); `wa_web.py list` prints chat names, and the agent must not run it.
