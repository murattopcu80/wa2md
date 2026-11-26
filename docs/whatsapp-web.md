[README](../README.md) | **English** | [Türkçe](tr/whatsapp-web.md)

# 1. WhatsApp Web path (console path — the path that works today)

> **Important note (WhatsApp Web path):** This path only reads your own chats, in a browser tab that you logged in to yourself, and sends no data anywhere. Even so, automated collection from WhatsApp Web can conflict with WhatsApp's terms of service. The recommended path is WhatsApp's official "Export chat" feature ([phone export](phone-export.md)). Using the Web path is entirely at your own responsibility. Files that belong to this path: `wa_web.py`, `wa_collect.js`, `tests/test_wa_web.py`, `tests/test_browser_smoke.py` and `tests/fixtures/web/`.

The collection logic (finding the chat through the search box, scrolling to older messages, message parsing, photo blobs) is in a single file: `wa2md_assets/wa_collect.js`. No external connection to Chrome is needed; the code runs in your open WhatsApp Web tab.

## Setup (once)

Python 3 is enough (no extra package for the console path). Only for the experimental CDP path and the browser tests: `python -m venv .venv` and `.venv\Scripts\pip install -r requirements.txt` (or `pip install ".[browser]"`).

## Steps

1. Generate the ready-made JS (it is also copied to the clipboard):

   ```
   python wa_web.py snippet --chats "Ali Veli,Sample Group"
   python wa_web.py snippet --chats "Ali Veli" --from 2026-01-01 --to 2026-11-14 --max-messages 500 --no-media
   ```

2. In the logged-in `web.whatsapp.com` tab in Chrome open **F12 → Console**, paste the code, press Enter. The first time, Chrome asks you to type `allow pasting` for safety: type it, press Enter, then paste again.
3. Watch the `[wa] ...` progress lines in the console and the counter in the green box at the top right of the page (do not put the computer to sleep; scrolling is done at human speed). Every 10 minutes (`--checkpoint-minutes N`, `0` = off) a checkpoint part with all messages collected so far is downloaded, so closing the tab or a crash no longer loses the whole collection: `import` converts the newest checkpoint and says that the collection is incomplete. To end early, press **Stop and save** in the green box (or run `__waCollect.stop()` in the console): scrolling stops and the final part is written with what was collected. **The bundles are sealed in the tab before they are downloaded**: the message text and the chat name are encrypted with a one-time key that `snippet` made and keeps in your user state folder (the same folder as the review file, outside Downloads and outside the output folder); the downloaded files hold no readable chat text and no chat name (`wa-bundle-sealed-<session>-001.json`). Photos are stored as before. When it finishes, the bundle(s) try to download automatically: `wa-bundle-sealed-<session>-001.json` appears in your **Downloads** folder. Chrome may block the download from the page (click **Allow** in the "download multiple files" prompt in the address bar) or the file may not download at all; click the **link in the green box** at the top right of the page. If that does not download either, press the **"Download in a new tab (backup)"** button in the same box: the file downloads with a random name (a GUID, no extension); `import` recognizes it from the header inside it, not from its name (pass the file directly as a path). Small chats are a single file; large ones are split into numbered parts of about 40 MB (`-001`, `-002`, ...).
4. Convert the bundles to Markdown (a folder or files can be given; all parts of the same chat are read together, and it tells you if a part is missing):

   ```
   python wa_web.py import C:\Users\user\Downloads --out C:\Users\user\wa-out
   python wa_web.py import wa-bundle-sealed-abc123-001.json wa-bundle-sealed-abc123-002.json --out C:\Users\user\wa-out
   ```

   A summary line is written for every chat: `[Name] N messages, M media copied, K media missing -> path`. `import` opens the sealed bundles in memory with the key from your user state folder, masks them with the same anonymizer as the phone path, and after a successful conversion deletes the bundle files of that chat once its collection is finished (checkpoints included; `--keep-bundles` keeps them) and, once every chat of the run has imported its final part, the key (the key file records how many chats the run asked for, and the final part of a chat carries, authenticated, how many chats the run actually started, so a stop or a chat that was not found does not keep the key for ever; the key also stays while the input still holds a sealed bundle of that run that was not converted, and when you import only some of the chats, and `import` says which case it is; if the run stopped between two chats or its last requested chat was not found, nothing records that, so delete the file in the `keys` folder of your user state folder by hand when no bundle of that run is left): a copy of a bundle left in a backup or a synced folder can no longer be opened. Import all bundles of one `snippet` run together (the folder), on the computer and user account where you ran `snippet`. The seal protects the files at rest; until `import` runs, someone who can read your user state folder can read the key. Bundles of a chat that failed stay where they are. `import` scans a folder as it is: if old bundles are still there, it converts them too. Parts of a collection that has no final part yet (only a checkpoint reached the folder) stay where they are, and so does the key: import again when the final part has been downloaded.

Options: `--from` / `--to` date range, `--max-messages N` newest N messages, `--no-media` do not download media, `--no-video` do not touch video, gif or audio messages (no click, no media viewer, nothing plays or downloads; they are written as `[video: not exported]` / `[audio: not exported]`; photos are taken only when already loaded in the chat or by their download button), `--checkpoint-minutes N` checkpoint interval (default 10, `0` = off), `--older-from-phone` click the "Click here to get older messages from your phone" button at the start of the chat (default: do not click; the phone must be on). `import` also accepts `--from/--to/--max-messages`; `import` and `export` also accept the same anonymization options as `wa2md.py` (`--extra-names`, `--review-dir`, `--no-dictionary`) with the same meaning.

Documents (xlsx, pdf, docx, zip ...) are saved through WhatsApp Web's own **Download** item in the message menu (the collector opens the menu and clicks only an item whose text is exactly "Download"; no preview opens). In an anonymized run they are copied to the output only with `--copy-documents`, because a document can hold names. Video, gif and audio are never played: with `--no-video` they are skipped, without it they are saved only if WhatsApp already holds them as a blob, and otherwise skipped (saving them would need playback).

## Experimental: connecting directly to Chrome (`list` / `export`) — connection not verified

```
.venv\Scripts\python wa_web.py list
.venv\Scripts\python wa_web.py export --chats "Ali Veli" --out C:\Users\user\wa-out
```

This runs the same `wa_collect.js` by attaching to a running Chrome with Playwright and hands the bundles straight to the `import` code. If the collection fails or the tab is closed, what was collected so far (the checkpoints) is converted and masked as usual; parts that cannot be converted stay in a temporary folder whose path is printed, and **Stop and save** ends the whole run, not only the current chat. On `chrome://inspect/#remote-debugging` the box "Allow remote debugging for this browser instance" must be checked, and **Allow** must be clicked in the permission dialog that appears on the first connection. **A connection to a real Chrome has not been verified**: in the maintainer's test environment, with Chrome 157, the endpoint did not answer the WebSocket handshake (three attempts timed out). That the script works with its own temporary Chrome is shown by the tests. If it cannot connect, the command reports an error and recommends the console path.

## Read-only, but the read receipt goes out

The collector writes nothing, sends nothing, reacts to nothing, deletes, archives or mutes nothing, and changes no setting. It only types into the chat search box (and clears it afterwards), opens the chat, scrolls, opens and closes the photo/GIF preview (media viewer), and expands "Read more" on long text. However, **opening a chat marks that chat's messages as "read"** (the other side gets the blue tick). This is inherent to this path and accepted. Texts inside chats are treated as untrusted data; instructions inside them are ignored.

## Limits

- Photos are taken from the full-size image already loaded in the chat (WhatsApp Web already holds a decoded blob); if it is not loaded (a size such as "136 kB" and a download arrow are shown on it), that download arrow is clicked (it arrives in about 1 s); old photos that do not arrive with this click (WhatsApp may have deleted them from the server) are not tried again and stay as `_(dosya eksik: ...)_` ("file missing"). In other cases the media viewer is opened and closed. Every photo in an album is a separate file (`...-1.jpg`, `...-2.jpg`). GIFs are saved as `.mp4`. A photo that cannot be obtained becomes `_(dosya eksik: ...)_` in the Markdown. Video and audio are **not verified** (there was no example in this chat); documents are not downloaded (it would trigger a browser download): a placeholder line (`_belge indirilemedi: rapor.pdf_`, "document could not be downloaded") is written.
- Forwarded messages are written with the note `_Yönlendirilmiş mesaj_` ("forwarded message"). Reactions (emoji) and link preview cards are not written (the link text in the message is written). Bold/italic markers are not kept.
- WhatsApp Web shows only messages synced with the phone. Older messages are on the phone; the collector reports this with a note and clicks the button only with `--older-from-phone`.
- If a day heading is "TODAY/YESTERDAY/weekday" it is resolved against the collection date. The time of unstamped (media-only) messages comes from the message footer, and the date from the day heading or from neighbouring messages; the sender name comes from the label on screen, and for an outgoing message from your own name.
- WhatsApp changes its interface often. All selectors are in the `SEL` table at the top of `wa_collect.js`; each line says whether it was verified by observation in the WhatsApp Web interface (`[V]`) or is unverified / a guess (`[U]`). If something breaks, look at `SEL` first.
