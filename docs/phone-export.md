[README](../README.md) | **English** | [Türkçe](tr/phone-export.md)

# 2. Export from the phone (alternative)

1. Open the chat in WhatsApp.
2. Android: top right **⋮** → **More** → **Export chat**. iOS: tap the contact/group name at the top → **Export Chat**.
3. Choose **Include media**.
4. Move the resulting zip file to the computer (e-mail, Drive, cable, etc.).

Note: WhatsApp limits the export. About 10,000 of the latest messages with media, about 40,000 without media, are exported. Older messages are not in the file.

```
python wa2md.py <input> [<input>...] --out <folder> [--only "name1,name2"] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--name NAME]
               [--no-media] [--copy-documents] [--extra-names "First Last,Name2" | --extra-names @names.txt]
               [--review-dir FOLDER] [--no-dictionary] [--no-anonymize] [--lang en|tr]
```

Input: a zip file, an extracted folder, or a folder that contains several zips. Only Python 3 is needed (no extra package).

```
python wa2md.py "C:\Users\user\Downloads\WhatsApp Chat with Ali Veli.zip" --out C:\Users\user\wa-out
python wa2md.py C:\Users\user\exports --out C:\Users\user\wa-out --only "ali,veli" --from 2026-01-01 --to 2026-11-14
```

Input files are never touched; on a re-run only its own `.md` file is written and media of the same size is skipped.
