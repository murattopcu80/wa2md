#!/usr/bin/env python3
"""Converts WhatsApp "Export chat" output (zip / folder) to Markdown and anonymizes it.

Python standard library only. Usage:
    python wa2md.py <input> [<input>...] --out <folder> [--only "a,b"] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--name NAME]
                    [--no-media] [--copy-documents] [--extra-names "A B,C" | @file] [--review-dir DIR] [--no-dictionary]
                    [--no-anonymize] [--lang en|tr]
Default: the output is anonymized (direct identifiers are removed, see Anonymizer); --no-anonymize writes real names.
The Turkish option names (--medya-yok, --belgeleri-kopyala, --ek-adlar, --inceleme-dizini, --sozluksuz, --anonim,
--no-anonim) are accepted aliases. Help and console messages are English; --lang tr or WA2MD_LANG=tr selects Turkish
(one table: MSG). The labels inside the Markdown output are still Turkish.
"""
__version__ = "0.1.0"   # the ONE place of the version number (pyproject.toml reads it)

import argparse
import bisect
import datetime as dt
import functools
import hashlib
import itertools
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import zipfile
from urllib.parse import quote

# ---------------------------------------------------------------- message language (command line, help, console)
# ONE table for every user-facing command-line string of wa2md.py and wa_web.py. Selection order: --lang, then the
# WA2MD_LANG environment variable, then English. The OUTPUT labels inside the Markdown (Sohbet-N, Kişi N, [telefon], ...)
# are NOT part of this table: the anonymizer's own patterns embed them (see the language-pack design issue).
LANGS = ("en", "tr")
_LANG = [None]      # set explicitly by init_lang() for the duration of one main() call; None = follow WA2MD_LANG / English


def _norm_lang(value):
    """'tr', 'TR', 'tr_TR', 'tr-TR' -> 'tr'; unknown or empty -> None."""
    code = re.split(r"[-_.]", (value or "").strip().lower(), maxsplit=1)[0]
    return code if code in LANGS else None


def init_lang(argv=None, env=None):
    """Pick the message language before the parser is built, so help text is already in that language.
    --lang (anywhere in argv; '--lang tr' or '--lang=tr') beats WA2MD_LANG beats English. Unknown --lang values are
    reported by the parser (choices); an unknown WA2MD_LANG value is ignored."""
    argv = sys.argv[1:] if argv is None else list(argv)
    env = os.environ if env is None else env
    value = None
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            value = argv[i + 1]
        elif a.startswith("--lang="):
            value = a[len("--lang="):]
    _LANG[0] = _norm_lang(value) or _norm_lang(env.get("WA2MD_LANG")) or "en"
    return _LANG[0]


def reset_lang():
    """End of a main() call: library-style calls (import_bundles, write_chat, ...) follow WA2MD_LANG again."""
    _LANG[0] = None


def current_lang():
    return _LANG[0] or _norm_lang(os.environ.get("WA2MD_LANG")) or "en"


def add_lang_arg(p):
    """--lang on the top-level parser and on every sub-command (SUPPRESS: a sub-command never overwrites the value)."""
    p.add_argument("--lang", type=str.lower, choices=LANGS, default=argparse.SUPPRESS, metavar="{en,tr}",
                   help=t("help_lang"))


def t(key, **kw):
    """Message text in the selected language; {placeholders} are filled from kw."""
    text = MSG[key][current_lang()]
    return text.format(**kw) if kw else text


def t_stat(cat):
    """Display name of an internal statistics category (the internal keys stay Turkish)."""
    return STAT_LABEL.get(cat, cat) if current_lang() == "en" else cat


STAT_LABEL = {"gönderen": "sender", "sistem satırı": "system line", "ek ad": "extra name", "sözlük": "dictionary",
              "hitap": "honorific", "anma": "mention", "iletişim": "contact", "firma": "company",
              "sohbet adı": "chat name", "telefon": "phone", "e-posta": "e-mail", "kullanıcı adı": "username",
              "iban": "iban", "tckn": "national id", "plaka": "plate", "parola": "password", "kod": "code",
              "yer/kurum belirsiz": "place/institution unclear"}

MSG = {
    # ---- errors and warnings (stderr) ----
    "err": {"en": "ERROR", "tr": "HATA"},
    "warn": {"en": "WARNING", "tr": "UYARI"},
    "ref_input": {"en": "input {n}", "tr": "girdi {n}"},
    "no_chat_in_zip": {"en": "no chat (.txt) file found in '{path}'.",
                       "tr": "'{path}' içinde sohbet (.txt) dosyası bulunamadı."},
    "no_chat_in_dir": {"en": "no chat (.txt) file found in folder '{path}'.",
                       "tr": "'{path}' klasöründe sohbet (.txt) dosyası bulunamadı."},
    "no_chat_in_input": {"en": "no chat (.txt) file found.", "tr": "sohbet (.txt) dosyası bulunamadı."},
    "input_missing": {"en": "Input not found: {path}", "tr": "Girdi bulunamadı: {path}"},
    "input_not_zip": {"en": "Unsupported file (zip expected): {path}",
                      "tr": "Desteklenmeyen dosya (zip bekleniyordu): {path}"},
    "no_zip_or_dir": {"en": "no zip or chat folder found in '{path}'.",
                      "tr": "'{path}' içinde zip veya sohbet klasörü bulunamadı."},
    "not_a_zip": {"en": "{who} is not a valid zip file.", "tr": "{who} geçerli bir zip dosyası değil."},
    "unexpected": {"en": "unexpected error ({kind}); for details the user must run with --no-anonymize.",
                   "tr": "beklenmeyen hata ({kind}); ayrıntı için kullanıcı --no-anonim ile çalıştırmalı."},
    "no_match": {"en": "No chat matched the filter.", "tr": "Filtreye uyan sohbet bulunamadı."},
    "no_messages_count": {"en": "No messages could be parsed. Format not recognized. Number of unparsed lines: {n}.",
                          "tr": "Hiç mesaj ayrıştırılamadı. Biçim tanınmadı. Ayrıştırılamayan satır sayısı: {n}."},
    "no_messages_lines": {"en": "No messages could be parsed. Format not recognized. First 3 unparsed lines:",
                          "tr": "Hiç mesaj ayrıştırılamadı. Biçim tanınmadı. İlk 3 ayrıştırılamayan satır:"},
    "file_empty": {"en": "   (the file looks empty)", "tr": "   (dosya boş görünüyor)"},
    "empty_range": {"en": "No messages in the selected date range, skipped.",
                    "tr": "Seçilen tarih aralığında mesaj yok, atlandı."},
    "empty_range_web": {"en": "No messages in the selected range, skipped.",
                        "tr": "Seçilen aralıkta mesaj yok, atlandı."},
    "dict_missing": {"en": "name dictionary missing ({names}; expected location: {path}). Get the complete tool folder "
                           "or explicitly accept running without it: --no-dictionary",
                     "tr": "ad sözlüğü eksik ({names}; beklenen yer: {path}). Araç klasörünü eksiksiz al ya da "
                           "sözlüksüz çalışmayı açıkça kabul et: --sozluksuz"},
    "review_in_git": {"en": "the review file is not written inside a git work tree ({path}). It contains possible "
                            "real names; give a folder outside git with --review-dir.",
                      "tr": "inceleme dosyası bir git çalışma ağacının içine yazılmaz ({path}). Olası gerçek adlar "
                            "içerir; --inceleme-dizini ile git dışında bir klasör ver."},
    "review_unwritable": {"en": "the review folder cannot be created or written ({path}; {err}). No output was "
                                "written; give a writable folder outside git with --review-dir.",
                          "tr": "inceleme klasörü oluşturulamıyor ya da yazılamıyor ({path}; {err}). Hiçbir çıktı "
                                "yazılmadı; --inceleme-dizini ile yazılabilir, git dışında bir klasör ver."},
    "review_in_git_exc": {"en": "the review folder is inside a git work tree",
                          "tr": "inceleme klasörü bir git çalışma ağacının içinde"},
    "dict_missing_exc": {"en": "name dictionary (adlar/) missing; to run without it use --no-dictionary",
                         "tr": "ad sözlüğü (adlar/) eksik; sözlüksüz çalışmak için --sozluksuz"},
    "json_error": {"en": "JSON error (line {line}, column {col})", "tr": "JSON hatası (satır {line}, sütun {col})"},
    "names_unreadable": {"en": "Name file could not be read ({kind})", "tr": "Ad dosyası okunamadı ({kind})"},
    "bad_date": {"en": "Invalid date '{value}' (expected YYYY-MM-DD)",
                 "tr": "Geçersiz tarih '{value}' (YYYY-AA-GG olmalı)"},
    # ---- per-chat summary (stdout) ----
    "summary": {"en": "[{shown}] {real} messages, {copied} media copied, {missing} media missing -> {path}",
                "tr": "[{shown}] {real} mesaj, {copied} medya kopyalandı, {missing} medya eksik -> {path}"},
    "attach_warn": {"en": "   WARNING: attachments: {c} copied, manual check needed ({cd}); {s} not copied ({sd}) -> {path}",
                    "tr": "   UYARI: ekler: {c} kopyalandı, elle kontrol gerekli ({cd}); {s} kopyalanmadı ({sd}) -> {path}"},
    "media_warn": {"en": "   WARNING: {n} media/attachment files were copied as they are and are NOT anonymized (faces, ID "
                         "documents, bank cards, screenshots with names). Use --no-media before sharing.",
                   "tr": "   UYARI: {n} medya/ek dosyası olduğu gibi kopyalandı ve anonimleştirilmedi (yüzler, kimlik "
                         "belgeleri, banka kartları, ad içeren ekran görüntüleri). Paylaşmadan önce --medya-yok kullan."},
    "masked": {"en": "   masked: {counts}", "tr": "   maskelenen: {counts}"},
    "no_dict_warn": {"en": "   WARNING: name dictionary MISSING (--no-dictionary): names that the dictionary or "
                           "honorifics would find were not masked, the suspect-remaining count is incomplete",
                     "tr": "   UYARI: ad sözlüğü YOK (--sozluksuz): sözlük/hitapla bulunacak adlar maskelenmedi, "
                           "şüpheli kalan sayımı eksik"},
    "review_summary": {"en": "   suspect remaining: {n} words ({first} priority), {passes} occurrences -> {path} "
                             "(outside the output; contains possible real names, do not share, for your eyes only)",
                       "tr": "   şüpheli kalan: {n} sözcük ({first} öncelikli), {passes} geçiş -> {path} (çıktının "
                             "dışında; olası gerçek adlar içerir, paylaşma, yalnız sen bak)"},
    "review_zero": {"en": "   suspect remaining: 0", "tr": "   şüpheli kalan: 0"},
    "limit_note": {"en": "Mode: removal of direct identifiers. In the legal sense (for example under the Turkish KVKK) "
                         "the result is NOT anonymous while content that identifies people remains in the text or photos, "
                         "or while the original chat exists: names that are not in a dictionary and nicknames, photo "
                         "content (faces, screenshots; use --no-media for output without photos), the content of "
                         "copied attachments, exact timestamps, places and writing style can still identify people.",
                   "tr": "Mod: doğrudan tanımlayıcıların kaldırılması. KVKK açısından sonuç, metinde/fotoğraflarda "
                         "kimliği belli eden içerik kaldığı sürece veya özgün sohbet durdukça anonim SAYILMAZ: "
                         "sözlükte olmayan adlar ve takma adlar, fotoğraf içeriği (yüzler, ekran görüntüleri; "
                         "fotoğrafsız çıktı için --medya-yok), kopyalanan eklerin içeriği, kesin zaman damgaları, "
                         "yerler ve yazım üslubu kişileri yine belli edebilir."},
    # ---- review file (operator-only text file) ----
    "review_head": {"en": "# MAY CONTAIN REAL NAMES - DO NOT SHARE, DO NOT COMMIT. Words left unmasked for {shown} "
                          "that could be names.\n"
                          "# The file is kept outside the output folder, in the user state folder. Words and example\n"
                          "# contexts are taken from the text AFTER masking: the file only shows what already stands\n"
                          "# as-is in the output text, never a masked name. It still flags which remaining word could\n"
                          "# be a name, so do not share it together with the output. Give the ones that are real\n"
                          "# names with --extra-names and re-run on the same input.\n"
                          "# word<TAB>occurrences<TAB>reason<TAB>example context (at most 3)\n",
                    "tr": "# OLASI GERÇEK ADLAR İÇERİR - PAYLAŞMA, COMMIT ETME. {shown} için maskelenmeden kalan, ad "
                          "olabilecek\n"
                          "# sözcükler. Dosya çıktı klasörünün dışında, kullanıcı durum klasöründe tutulur. Sözcükler ve "
                          "örnek\n"
                          "# bağlamlar maskelemeden SONRAKİ metinden alınır: yalnız çıktı metninde zaten olduğu gibi "
                          "duran şeyleri\n"
                          "# gösterir, maskelenmiş bir adı göstermez. Ama kalan sözcüğün ad olabileceğini işaretler; "
                          "bu yüzden\n"
                          "# çıktıyla birlikte paylaşma. Gerçek ad olanları --ek-adlar ile verip aynı girdiyle yeniden "
                          "çalıştır.\n"
                          "# sözcük<TAB>geçiş<TAB>neden<TAB>örnek bağlam (en çok 3)\n"},
    "why_hitap": {"en": "before an honorific, not in the dictionary (sentence start) - look at this first",
                  "tr": "hitaptan önce, sözlükte yok (cümle başı) - önce buna bak"},
    "why_büyük": {"en": "name that is also an ordinary word, capitalized (sentence start) - look at this first",
                  "tr": "sözcük anlamı da olan ad, büyük harfle (cümle başı) - önce buna bak"},
    "why_küçük": {"en": "name that is also an ordinary word, lower case (mostly ordinary words)",
                  "tr": "sözcük anlamı da olan ad, küçük harfle (çoğu sıradan sözcük)"},
    # ---- wa_web.py ----
    "web_not_bundle": {"en": "bundle part {no} is not a wa-web-bundle file.",
                       "tr": "paket parçası {no} bir wa-web-bundle dosyası değil."},
    "web_no_final": {"en": "Final bundle part not found: the collection may have been cut short.",
                     "tr": "Son paket (final) bulunamadı: toplama yarıda kesilmiş olabilir."},
    "web_missing_parts": {"en": "Missing bundle part(s): {parts}", "tr": "Eksik paket parçası: {parts}"},
    "web_no_bundles": {"en": "wa-bundle-*.json not found.", "tr": "wa-bundle-*.json bulunamadı."},
    "web_skipped_media": {"en": "   {n} video/audio/document items could not be downloaded, written as placeholder lines.",
                          "tr": "   {n} video/ses/belge indirilemedi, yer tutucu satır olarak yazıldı."},
    "web_older_on_phone": {"en": "   Note: older messages are on the phone; the WhatsApp Web button 'Click here to get "
                                 "older messages from your phone' appeared (the script did not click it).",
                           "tr": "   Not: daha eski mesajlar telefonda; WhatsApp Web'de 'Telefonunuzdaki eski mesajları "
                                 "almak için buraya tıklayın' düğmesi göründü (betik tıklamadı)."},
    "web_done": {"en": "Done: {done} chats written, {failed} skipped/failed.",
                 "tr": "Bitti: {done} sohbet yazıldı, {failed} atlandı/hatalı."},
    "web_chats_empty": {"en": "--chats is empty.", "tr": "--chats boş."},
    "web_snippet_ready": {"en": "\n[{kb} KB of JS ready; {copied}]\n", "tr": "\n[{kb} KB JS hazır; {copied}]\n"},
    "web_copied": {"en": "copied to the clipboard", "tr": "panoya kopyalandı"},
    "web_not_copied": {"en": "clipboard not available, copy the text above", "tr": "pano kullanılamadı, yukarıyı kopyala"},
    "web_snippet_steps": {"en": "Steps: 1) In the WhatsApp Web tab press F12 -> Console. 2) Paste (the first time Chrome asks "
                                "you to type 'allow pasting'), Enter. 3) Watch the '[wa] ...' progress lines in the console; "
                                "when it finishes the bundles are downloaded to your Downloads folder (if Chrome asks about "
                                "'downloading multiple files', allow it). 4) python wa_web.py import <Downloads> --out <folder>",
                          "tr": "Adımlar: 1) WhatsApp Web sekmesinde F12 -> Console. 2) Yapıştır (Chrome ilk seferde "
                                "'allow pasting' yazmanı ister), Enter. 3) Konsolda '[wa] ...' ilerleme satırlarını izle; "
                                "bitince paketler İndirilenler'e iner (Chrome 'birden çok dosya indirme' sorarsa İzin ver). "
                                "4) python wa_web.py import <İndirilenler> --out <klasör>"},
    "web_required_step": {"en": "Could not connect to Chrome via remote debugging (experimental path, connection not verified).\n"
                                "The working path is the console path: `python wa_web.py snippet --chats \"Name\"` prints the "
                                "ready-made JS and copies it to the clipboard; paste it into F12 -> Console in the WhatsApp tab; "
                                "convert the downloaded wa-bundle-*.json files with "
                                "`python wa_web.py import <folder> --out <folder>`.\n"
                                "(For CDP: allow remote debugging at chrome://inspect/#remote-debugging and click 'Allow' in the "
                                "permission dialog.)",
                          "tr": "Chrome'a uzaktan hata ayıklama ile bağlanılamadı (deneysel yol, bağlantı doğrulanmadı).\n"
                                "Çalışan yol: konsol yolu. `python wa_web.py snippet --chats \"Ad\"` komutu hazır JS'yi "
                                "yazdırır ve panoya kopyalar; WhatsApp sekmesinde F12 -> Console'a yapıştır; inen "
                                "wa-bundle-*.json dosyalarını `python wa_web.py import <klasör> --out <klasör>` ile "
                                "Markdown'a çevir.\n"
                                "(CDP için: chrome://inspect/#remote-debugging'de uzaktan hata ayıklamaya izin ver ve izin "
                                "penceresinde 'İzin ver'e tıkla.)"},
    "web_bad_port_file": {"en": "DevToolsActivePort file is invalid ({path}).", "tr": "DevToolsActivePort dosyası geçersiz ({path})."},
    "web_connecting": {"en": "Connecting to Chrome (experimental)... If Chrome shows a permission dialog, click 'Allow'.",
                       "tr": "Chrome'a bağlanılıyor (deneysel)... Chrome bir izin penceresi gösterirse 'İzin ver'e tıkla."},
    "web_connect_failed": {"en": "Could not connect to Chrome ({kind}).", "tr": "Chrome'a bağlanılamadı ({kind})."},
    "web_no_playwright": {"en": "playwright is not installed (CDP path only). `.venv\\Scripts\\pip install -r requirements.txt`; "
                                "for the console path use the `snippet` command.",
                          "tr": "playwright kurulu değil (yalnız CDP yolu için). `.venv\\Scripts\\pip install -r "
                                "requirements.txt`; konsol yolu için `snippet` komutunu kullan."},
    "web_total": {"en": "Total: {n} chats.", "tr": "Toplam {n} sohbet."},
    "web_collect_failed": {"en": "collection failed", "tr": "toplama başarısız"},
    "web_collect_failed_kind": {"en": "collection failed ({kind}).", "tr": "toplama başarısız ({kind})."},
    # ---- help text ----
    "help_lang": {"en": "language of help and console messages (default: English; environment variable WA2MD_LANG). "
                        "The labels inside the Markdown output are not affected",
                  "tr": "yardım ve konsol iletilerinin dili (varsayılan: İngilizce; ortam değişkeni WA2MD_LANG). "
                        "Markdown çıktısındaki etiketler değişmez"},
    "help_description": {"en": "Converts WhatsApp chat exports to Markdown.",
                         "tr": "WhatsApp sohbet dışa aktarımını Markdown'a çevirir."},
    "help_inputs": {"en": "zip, extracted folder, or a folder containing zips",
                    "tr": "zip, çıkarılmış klasör veya zip'lerin bulunduğu klasör"},
    "help_out": {"en": "output folder", "tr": "çıktı klasörü"},
    "help_only": {"en": 'chat name filter, comma-separated: "ali,veli"',
                  "tr": 'sohbet adı filtresi, virgülle: "naime,mehmet"'},
    "help_name": {"en": "set the chat name by hand (when anonymizing: this label instead of Sohbet-N)",
                  "tr": "sohbet adını elle belirle (anonimde: Sohbet-N yerine bu etiket)"},
    "help_no_media": {"en": "leave media out of the output (a 'media not included' note is written instead); photos are not "
                            "anonymized (faces, screenshots, documents), recommended for output you will share",
                      "tr": "medyayı çıktıya koyma (yerine 'medya dahil edilmemiş' notu); fotoğraflar anonimleştirilmez "
                            "(yüzler, ekran görüntüleri, belgeler), paylaşılacak çıktı için önerilir"},
    "help_copy_documents": {"en": "when anonymizing, only images, video and audio are copied by default; with this option the "
                                  "other attachments are copied too (contact card, PDF, office document, archive, unknown or "
                                  "extension-less file). They are not anonymized; they may contain names, numbers, signatures",
                            "tr": "anonim modda varsayılan olarak yalnız görüntü, video ve ses kopyalanır; bu seçenekle diğer "
                                  "ekler de (kişi kartı, PDF, ofis belgesi, arşiv, bilinmeyen/uzantısız dosya) kopyalanır. "
                                  "Bunlar anonimleştirilmez; içlerinde ad, numara, imza olabilir"},
    "help_anonymize": {"en": "anonymization (removal of direct identifiers); ON by default, turn off with --no-anonymize. "
                             "Person names become 'Kişi N', chat/folder/file name 'Sohbet-N' (N: position in this run), "
                             "phone -> [telefon], e-mail -> [e-posta], IBAN -> [iban], Turkish national ID -> [tckn], plate -> "
                             "[plaka], trade name (a name before nakliyat/nakliye/lojistik/taşımacılık or a name in "
                             "Ltd./Şti./A.Ş. form, without needing a listing marker; names built with kargo/transport/şirketi "
                             "and lower-case names only in a listing message with a phone or contact field; excluded: the generic "
                             "qualifier list and listing vocabulary, a bare place name, an honorific phrase; see README) and "
                             "sector domain name -> [firma], the path of a link with a masked domain -> [yol]; participant "
                             "names (senders and the people in system lines; full name, a first name alone when unambiguous, "
                             "inflected forms like \"Naime'ye\"), names found in the name dictionary, with an honorific, in a "
                             "contact field or next to a phone are masked in message text too; the chat name only in the "
                             "title, in system lines and in file names. The real name <-> label mapping is written nowhere "
                             "(file, console). This mode is 'removal of direct identifiers'; in the legal sense (for example under the "
                             "Turkish KVKK) it does NOT count as anonymous while content that identifies people remains in the "
                             "text/photos or while the original chat exists: names of non-participants, photo content (faces, "
                             "screenshots, documents; use --no-media if you will share), exact timestamps, places and writing "
                             "style can still identify a person. The labels are Turkish in this version (see README, "
                             "Language support)",
                       "tr": "anonimleştirme (doğrudan tanımlayıcıların kaldırılması); varsayılan AÇIK, kapatmak için "
                             "--no-anonim. Kişi adları 'Kişi N', sohbet/klasör/dosya adı 'Sohbet-N' (N: bu çalıştırmadaki "
                             "sıra), telefon -> [telefon], e-posta -> [e-posta], IBAN -> [iban], T.C. kimlik no -> [tckn], "
                             "plaka -> [plaka], ticari ad (nakliyat/nakliye/lojistik/taşımacılık önündeki ad ya da "
                             "Ltd./Şti./A.Ş. biçimli ad, ilan imi gerekmeden; kargo/transport/şirketi ile kurulan ad ve küçük "
                             "harfli ad yalnız telefonlu ya da iletişim alanlı ilan mesajında; dışlananlar: genel niteleme "
                             "listesi ve ilan sözlüğü, yalnız yer adı, hitap öbeği; bkz. README) ve nakliye alan adı -> "
                             "[firma], maskeli alan adlı bağlantının yolu -> [yol]; katılımcı adları (gönderenler ve sistem "
                             "satırlarındaki kişiler; ad-soyad, belirsiz değilse yalnız ad, 'Naime'ye' gibi ekli biçimler), ad "
                             "sözlüğündeki, hitaplı ve iletişim alanındaki ya da telefon yanındaki adlar mesaj metninde de "
                             "maskelenir; sohbet adı yalnız başlıkta, sistem satırlarında ve dosya adlarında. Gerçek ad <-> "
                             "etiket eşlemesi hiçbir yere (dosya, konsol) yazılmaz. Bu mod 'doğrudan tanımlayıcıların "
                             "kaldırılması'dır; KVKK açısından metinde/fotoğraflarda kimliği belli eden içerik kaldığı sürece "
                             "veya özgün sohbet durdukça anonim SAYILMAZ: katılımcı olmayan kişilerin adları, fotoğraf içeriği "
                             "(yüzler, ekran görüntüleri, belgeler; paylaşacaksan --medya-yok kullan), kesin zaman damgaları, "
                             "yerler ve yazım üslubu kişiyi yine belli edebilir"},
    "help_extra_names": {"en": 'NOT needed in a normal run (names are found automatically). Backup only: names you saw '
                               'in the review file are real, or names that are not in the dictionary, comma-separated '
                               '("First Last,Nickname") or @file (one name per line). Masked in every form like a participant',
                         "tr": 'normal çalıştırmada GEREKMEZ (adlar otomatik bulunur). Yalnız yedek: inceleme dosyasında '
                               'gerçek ad olduğunu gördüğün ya da sözlükte olmayan adlar, virgülle ("Ad Soyad,Takma") veya '
                               '@dosya (satır başına bir ad). Katılımcı gibi her biçimiyle maskelenir'},
    "help_review_dir": {"en": "folder for the suspect-remaining words file (default: the user state folder, e.g. "
                              "~/.local/state/wa2md/inceleme/<time>-<digest>; outside the output folder). The inside of a "
                              "git work tree is not accepted",
                        "tr": "şüpheli kalan sözcükler dosyasının klasörü (varsayılan: kullanıcı durum klasörü, ör. "
                              "~/.local/state/wa2md/inceleme/<zaman>-<özet>; çıktı klasörünün dışında). Git çalışma "
                              "ağacının içi kabul edilmez"},
    "help_no_dict": {"en": "run even if the name dictionary or place list (adlar/*.txt) is missing (not recommended: names "
                           "that the dictionary or honorifics would find are not masked). Without this option an "
                           "anonymized run fails when the dictionary is missing",
                     "tr": "ad sözlüğü ya da yer listesi (adlar/*.txt) eksikse yine de çalış (önerilmez: sözlük/hitapla "
                           "bulunacak adlar maskelenmez). Sözlük yokken bu seçenek olmadan anonim çalıştırma hata verir"},
    "help_web_description": {"en": "Exports WhatsApp Web chats to Markdown (read-only).",
                             "tr": "WhatsApp Web sohbetlerini Markdown'a aktarır (salt okunur)."},
    "help_max_messages": {"en": "newest N messages", "tr": "en yeni N mesaj"},
    "help_web_no_media": {"en": "do not download media / leave it out of the output; photos are not anonymized (faces, "
                                "screenshots, documents), recommended for output you will share",
                          "tr": "medya indirme / çıktıya koyma; fotoğraflar anonimleştirilmez (yüzler, ekran görüntüleri, "
                                "belgeler), paylaşılacak çıktı için önerilir"},
    "help_web_import_no_media": {"en": "leave media out of the output (photos in the bundle are not copied); photos are not "
                                       "anonymized (faces, screenshots, documents), recommended for output you will share",
                                 "tr": "medyayı çıktıya koyma (paketteki fotoğraflar kopyalanmaz); fotoğraflar anonimleştirilmez "
                                       "(yüzler, ekran görüntüleri, belgeler), paylaşılacak çıktı için önerilir"},
    "help_older_from_phone": {"en": "at the start of the chat click the 'get older messages from your phone' button "
                                    "(default: do not click)",
                              "tr": "sohbet başında 'telefondaki eski mesajları al' düğmesine tıkla (varsayılan: tıklama)"},
    "help_user_data_dir": {"en": "(CDP) Chrome user data folder (DevToolsActivePort is looked up here)",
                           "tr": "(CDP) Chrome kullanıcı verisi klasörü (DevToolsActivePort burada aranır)"},
    "help_snippet": {"en": "print the ready-made JS to paste into the console / copy it to the clipboard",
                     "tr": "konsola yapıştırılacak hazır JS'yi yazdır/panoya kopyala"},
    "help_chats": {"en": 'comma-separated: "Ali Veli,Sample Group"', "tr": 'virgülle: "Ali Veli,Örnek Grup"'},
    "help_bundle_paths": {"en": "bundle files or a folder", "tr": "paket dosyaları veya klasör"},
    "help_import": {"en": "convert downloaded wa-bundle-*.json bundles to Markdown",
                    "tr": "indirilen wa-bundle-*.json paketlerini Markdown'a çevir"},
    "help_list": {"en": "(CDP, experimental) print the chat names (opens no chat)",
                  "tr": "(CDP, deneysel) sohbet adlarını yazdır (sohbet açmaz)"},
    "help_export": {"en": "(CDP, experimental) export the named chats straight to Markdown",
                    "tr": "(CDP, deneysel) adlı sohbetleri doğrudan Markdown'a aktar"},
}


IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
# yon isaretleri ve BOM silinir. Sifir genislikli karakterler ve yumusak tire metinde kalir (main gibi; ad
# eslesmesinde sozcuk siniridir); telefon kalibi rakamlar arasindakileri atlar (_ZWP). Bolunmus adlar kapsam disi.
INVISIBLE = re.compile("[\u200e\u200f\u202a-\u202e\ufeff]")

DATE = r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})"
TIME = r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?(?:\s*([AaPp]\.?\s?[Mm]\.?|ÖÖ|ÖS|öö|ös))?"
ANDROID_RE = re.compile(r"^" + DATE + r",?\s+" + TIME + r"\s+-\s+(.*)$")
IOS_RE = re.compile(r"^\[" + DATE + r",?\s+" + TIME + r"\]\s*(.*)$")
ATTACH_ANDROID = re.compile(r"^(.+?)\s+\((?:dosya ekli|file attached)\)\s*$", re.I)
ATTACH_IOS = re.compile(r"<(?:ek|attached):\s*([^>]+?)\s*>", re.I)
OMITTED = re.compile(r"^<?[^<>]{0,30}(?:dahil edilmedi|omitted)>?$", re.I)

STRIP_NAME = [r"^WhatsApp Chat with\s+", r"\s+ile WhatsApp Sohbeti$", r"^WhatsApp Chat\s*-\s*",
              r"^WhatsApp Sohbeti\s*-\s*"]
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def nfc(s):
    return unicodedata.normalize("NFC", s)


def derive_name(stem):
    stem = nfc(stem).strip()
    for p in STRIP_NAME:
        stem = re.sub(p, "", stem, flags=re.I).strip()
    return stem


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ")
    if not name:
        name = "sohbet"
    if name.split(".")[0].upper() in RESERVED:
        name = "_" + name
    return name


# ---------------------------------------------------------------- kaynaklar
class Export:
    """Bir dışa aktarım: sohbet txt + medya dosyalari (basename -> opener)."""

    def __init__(self, label, txt_name, txt_bytes, files):
        self.label = label          # zip/klasor adi (uzantisiz)
        self.txt_name = txt_name
        self.txt_bytes = txt_bytes
        self.files = files          # {nfc(basename): (size, opener)}
        self.lower = {k.lower(): k for k in files}

    def find(self, name):
        name = nfc(os.path.basename(name.replace("\\", "/")))
        if name in self.files:
            return name
        return self.lower.get(name.lower())


def pick_txt(entries):
    """entries: [(name, size)] -> secilen txt adi veya None."""
    txts = [e for e in entries if e[0].lower().endswith(".txt")]
    if not txts:
        return None
    for n, _ in txts:
        if n.lower() == "_chat.txt":
            return n
    return max(txts, key=lambda e: e[1])[0]


def safe_zip_name(raw):
    """Guvenli degilse None; aksi halde basename."""
    p = raw.replace("\\", "/")
    if p.endswith("/") or p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return None
    parts = p.split("/")
    if ".." in parts or not parts[-1]:
        return None
    return parts[-1]


def load_zip(path):
    label = os.path.splitext(os.path.basename(path))[0]
    zf = zipfile.ZipFile(path)
    files = {}
    for info in zf.infolist():
        base = safe_zip_name(info.filename)
        if base is None:
            continue
        base = nfc(base)
        files[base] = (info.file_size, (lambda i=info: zf.open(i)))
    txt = pick_txt([(n, files[n][0]) for n in files])
    if txt is None:
        raise ValueError(t("no_chat_in_zip", path=path))
    data = files[txt][1]().read()
    media = {k: v for k, v in files.items() if k != txt and not k.lower().endswith(".txt")}
    return Export(label, txt, data, media)


def scan_files(path):
    """Klasordeki tum dosyalar -> {nfc(basename): (size, opener)} (Export.files bicimi)."""
    files = {}
    for root, _, names in os.walk(path):
        for n in names:
            full = os.path.join(root, n)
            files.setdefault(nfc(n), (os.path.getsize(full), (lambda f=full: open(f, "rb"))))
    return files


def load_dir(path):
    label = os.path.basename(os.path.normpath(path))
    files = scan_files(path)
    txt = pick_txt([(n, files[n][0]) for n in files])
    if txt is None:
        raise ValueError(t("no_chat_in_dir", path=path))
    with files[txt][1]() as fh:
        data = fh.read()
    media = {k: v for k, v in files.items() if k != txt and not k.lower().endswith(".txt")}
    return Export(label, txt, data, media)


def has_txt(path):
    return any(n.lower().endswith(".txt") for n in os.listdir(path))


def discover(inputs):
    """-> [(kind, path)] ; kind in zip|dir. Hatalar icin ValueError/FileNotFoundError."""
    found = []
    for inp in inputs:
        if not os.path.exists(inp):
            raise FileNotFoundError(t("input_missing", path=inp))
        if os.path.isfile(inp):
            if not inp.lower().endswith(".zip"):
                raise ValueError(t("input_not_zip", path=inp))
            found.append(("zip", inp))
        elif has_txt(inp):
            found.append(("dir", inp))
        else:
            sub = []
            for n in sorted(os.listdir(inp)):
                p = os.path.join(inp, n)
                if os.path.isfile(p) and n.lower().endswith(".zip"):
                    sub.append(("zip", p))
                elif os.path.isdir(p) and has_txt(p):
                    sub.append(("dir", p))
            if not sub:
                raise ValueError(t("no_zip_or_dir", path=inp))
            found.extend(sub)
    return found


# ---------------------------------------------------------------- ayristirma
def decode(data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    return INVISIBLE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")


def parse(text):
    """-> (messages, unparsed_lines). message = dict(raw=(a,b,y,H,M,S,ampm), sender, lines)"""
    msgs, unparsed = [], []
    cur = None
    for line in text.split("\n"):
        m = ANDROID_RE.match(line) or IOS_RE.match(line)
        if m:
            a, b, y, H, M, S, ap, rest = m.groups()
            sender, body = None, rest
            if ": " in rest:
                n, t = rest.split(": ", 1)
                if len(n) <= 60:
                    sender, body = n.strip(), t
            elif rest.endswith(":"):
                if len(rest) - 1 <= 60:
                    sender, body = rest[:-1].strip(), ""
            cur = {"raw": (int(a), int(b), int(y), int(H), int(M), int(S or 0), ap),
                   "sender": sender, "lines": [body]}
            msgs.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
        elif line.strip():
            unparsed.append(line)
    resolve_dates(msgs)
    return msgs, unparsed


def detect_mdy(raws):
    """raws: [(a, b, y, H, M, S, ampm)] -> True ise tarih AA/GG, degilse GG/AA."""
    if any(r[0] > 12 for r in raws):
        return False
    if any(r[1] > 12 for r in raws):
        return True
    return any(r[6] for r in raws)


def to_datetime(raw, mdy):
    """Tek ham kaydi datetime'a cevirir; gecersizse None."""
    a, b, y, H, M, S, ap = raw
    day, mon = (b, a) if mdy else (a, b)
    if y < 100:
        y += 2000
    if ap:
        pm = ap.lower().startswith("p") or ap.lower() == "ös"
        H = H % 12 + (12 if pm else 0)
    try:
        return dt.datetime(y, mon, day, H, M, S)
    except ValueError:
        return None


def resolve_dates(msgs):
    mdy = detect_mdy([m["raw"] for m in msgs])
    for m in msgs:
        m["dt"] = to_datetime(m["raw"], mdy)
    msgs[:] = [m for m in msgs if m["dt"] is not None]


def split_line(line):
    """Satiri parcalara ayirir: ('text', s) | ('file', name) | ('omitted', None)."""
    s = line.strip()
    if not s:
        return []
    m = ATTACH_ANDROID.match(s)
    if m:
        return [("file", m.group(1))]
    if ATTACH_IOS.search(s):
        out, pos = [], 0
        for mm in ATTACH_IOS.finditer(s):
            pre = s[pos:mm.start()].strip()
            if pre:
                out.append(("text", pre))
            out.append(("file", mm.group(1)))
            pos = mm.end()
        post = s[pos:].strip()
        if post:
            out.append(("text", post))
        return out
    if OMITTED.match(s):
        return [("omitted", None)]
    return [("text", s)]


# ---------------------------------------------------------------- anonimlestirme
_SEP = r"[ \-.\u00a0\u2010-\u2015\u2212\uff0d]"   # sabit kaliplarin ayraci: bosluk, NBSP, tire bicimleri, nokta
# Rakam: ASCII ve Unicode suslu bicimleri ayni sayilir. '\d' tum Unicode ondalik rakamlari (tam genislikli,
# matematiksel kalin/cift cizgili/...) zaten kapsar; sabit rakamlar (0, 5, 90, [2-5]) icin ayni rakamin tam genislikli,
# matematiksel (5 stil) ve segmentli bicimleri de sinifa girer (_dl). Tus kapagi ('0' + FE0F + 20E3) rakam sayilir.
# 6. tur: telefonun icinde rakamdan ya da ayractan once gelen sifir genislikli karakter ve yumusak tire (_ZWP) rakama ve
# ayraca katilir ('0500\u200b000 11 22'); yalniz telefon kaliplarinda, metin ve ad eslesmesi degismez. Dizinin bittigini
# denetleyen ileri bakislar (_DG0, _GS0) main'deki gibi bu karakterleri saymaz.
_ZWP = r"[\u00ad\u200b\u200c\u200d\u2060]*"
_KEYCAP = r"(?:\ufe0f?\u20e3)?"
_DG0 = r"(?:\d" + _KEYCAP + ")"
_DG = r"(?:" + _ZWP + r"\d" + _KEYCAP + ")"


def _dl(*ds):
    """Sabit rakam(lar) icin sinif: ASCII + tam genislikli + matematiksel suslu + segmentli + Arap-Hint (dogu ve Farsca)
    bicimler (+ tus kapagi; onunde _ZWP)."""
    return "(?:" + _ZWP + "[" + "".join(chr(b + d) for d in ds for b in (0x30, 0xFF10, 0x1D7CE, 0x1D7D8, 0x1D7E2, 0x1D7EC, 0x1D7F6,
                                                          0x1FBF0, 0x660, 0x6F0)) + "]" + _KEYCAP + ")"


# Grup ayraci: bosluk (NBSP, ince bosluk dahil), tire (Unicode tire/eksi ve tam genislikli bicimleri dahil), nokta, egik
# cizgi, virgul, alt cizgi, orta nokta (' - ' gibi bosluklu da), parantez; satir sonu degil. Yalniz onekli TR numarasinin
# butun rakam dizisinde kullanilir (dizi telefon uzunlugunda bitmeli): fiyat/tarih/olcu bu kaliba girmez.
# S10: ayrac 1-3 kez yinelenebilir ('0500 ... 000'), kapanan parantezden sonra da gelir ('(0500)  -  000')
# tire bicimleri (ASCII, Unicode tire/eksi, kucuk ve tam genislikli): telefon ayraci ve ticari adin tiresi (_FIRM_PREV) tek sinif
_DASH_CH = "-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe63\uff0d"
_DASH = "\\" + _DASH_CH
_DASH_RX = re.compile("[" + _DASH + "]")
# N5 (5. tur): yinelenen ayrac arasinda tek bosluk da olur ('0500 - - 000 ...')
_GSEP = "[" + _DASH + r"./\uff0e\uff0f,_\u00b7\u2022\u2219\u30fb\u2026]"
_GS0 = (r"(?:\)?[^\S\n]{0,2}" + _GSEP + r"(?:[^\S\n]?" + _GSEP + r"){0,2}"
        r"[^\S\n]{0,2}|[^\S\n]{1,2}|\)[^\S\n]{0,2}|[^\S\n]{0,2}\()")
_GS = "(?:" + _ZWP + _GS0 + ")"
# santral/ulke onekinden sonra virgul, alt cizgi, orta nokta ayrac sayilmaz: '0,5000000000' ondalik sayidir
_GS_T = (r"(?:" + _ZWP + r"(?:[^\S\n]{0,2}[" + _DASH + r"./\uff0e\uff0f][^\S\n]{0,2}"
         r"|[^\S\n]{1,2}|\)[^\S\n]{0,2}|[^\S\n]{0,2}\())")
_DATE_AHEAD = rf"(?!{_DG0}{{1,2}}[./]{_DG0}{{1,2}}[./]{_DG0}{{2,4}}(?!{_DG0}))"   # '05.11.2026 150 km': tarih, telefon degil
_TRUNK = rf"\(?(?:(?:(?:\+|{_dl(0)}{{2}}){_GS_T}?)?{_dl(9)}{_dl(0)}{_GS_T}?(?:{_dl(0)}{_GS_T}?)?|(?:{_dl(0)}{_GS_T}?){{1,2}})"   # +90 0090 90 0
# Telefon: (1) onekli (0/90/+90) TR numarasi, gruplama ve ayractan bagimsiz, BUTUN rakam dizisi: cep 9-10 ulusal hane
# (4-2-4 gibi bir hanesi eksik yazim dahil), sabit hat 10; dizi orada biter (ardinda ayrac + rakam yok). Ondeki
# yinelenen cep oneki ('0500 0500 000 00 00') ve ayrik santral/ulke oneki ('0 - 500...', '00 500...') diziyle birlikte
# maskelenir. A3 kismi maskesinin nedeni: sabit 3-3-2-2 kalibi uzun dizinin yalniz SONUNU esliyordu, onek acikta
# kaliyordu. (2) sabit kaliplar (dizi bitmese de: '0500 000 00 00 2 araç'). (3) +<8-15 hane> ve 00 + 1-3 haneli ulke
# kodu + ayrac + 6-12 hane ('0049 151 ...', butun dizi; ayracsiz '0012345678' referans numarasi olabilir, degil). Onekli bicimler bir rakam + tireden sonra da baslar ('...00-0500 ...' ikinci
# numara) ve sozcuge yapisik da ('Tel0500...', 'ara0500...'); ondalik ('1.5...') ve tarih ('05.11.2026') degil.
# Oneksiz bicimler (5xx..., (212)..., +...) harften sonra baslamaz.
# ilke 5: butun obekleri iki haneli dizi telefon degildir ('05-06-07-08-09', '00.30, 01.30'); virgul, alt cizgi, orta nokta
# yalniz telefon bicimli gruplamada ayractir (binlik gruplama '05,000,000,000' degil)
# (sinirli tekrar: telefon en cok ~15 hanedir; sinirsiz ileri bakis uzun rakam dizisinde her konumda sona kadar tarar)
_TWO_GROUPS = r"(?:\d{2}(?:[^\w\n]|_){1,4}){2,8}\d{2}(?!\w)"
_THOUSANDS = r"\d{1,3}(?:[,_\u00b7\u2022\u2219\u30fb]\d{3}){2,5}(?!\d)"
# sozcuge yapisik oneksiz cep numarasi yalniz iletisim sozcugunden sonra ('TEL500 000 00 00', 'GSM5000000000')
_GLUED = "".join(f"|(?<={''.join(f'[{c.upper()}{c}]' for c in w)})" for w in "tel tlf gsm cep telefon whatsapp wp".split())
_PHONE = (rf"(?=[\d+(])(?<![\d+])(?!{_TWO_GROUPS})(?!{_THOUSANDS})(?:"
          rf"(?=[(+]|{_dl(0, 5, 9)})(?<!\d[.,]){_DATE_AHEAD}(?:\(?{_dl(0)}?{_dl(5)}{_DG}{{2}}\)?{_GS})?{_TRUNK}\(?"
          rf"(?:{_dl(5)}(?:{_GS}?{_DG}){{8,9}}|{_dl(2, 3, 4, 8)}(?:{_GS}?{_DG}){{9}})(?!{_GS0}?{_DG0})"   # 8: 0850/0800
          rf"|(?=[(+]|{_dl(0, 9)})(?<!\d[.,]){_TRUNK}\(?{_dl(2, 3, 4, 5, 8)}{_DG}{{2}}\)?{_SEP}?{_DG}{{3}}{_SEP}?{_DG}{{2}}{_SEP}?{_DG}{{2}}"
          rf"|(?<!\d[.,]){_dl(0)}{{2}}{_GS_T}?(?!{_dl(0)}){_DG}{{1,3}}{_GS}{_DG}(?:{_GS}?{_DG}){{5,11}}(?!{_GS0}?{_DG0})"   # 00 49 ...
          rf"|(?:(?<!\w){_GLUED})(?<!\d[.,\-]){_dl(5)}{_DG}{{2}}{_SEP}?{_DG}{{3}}{_SEP}?{_DG}{{2}}{_SEP}?{_DG}{{2}}"   # oneksiz TR cep
          rf"|(?<!\w)(?<!\d[.,\-])\({_dl(2, 3, 4, 5)}{_DG}{{2}}\){_SEP}?{_DG}{{3}}{_SEP}?{_DG}{{2}}{_SEP}?{_DG}{{2}}"  # (322) 000 00 01
          rf"|(?<!\w)(?<!\d[.,\-])\+{_DG}(?:[ \-.() ]{{0,2}}{_DG}){{7,14}}"                              # +<8-15 hane>
          rf")(?!{_DG0})(?![.,]\d)")
_IBAN = r"(?<![\w])[Tt][Rr]\d{2}(?: ?\d){22}(?!\d)"
_TCKN = r"(?<![\w.,+\-])[1-9]\d{10}(?!\d)(?![.,]\d)"
# plaka: main'deki kalip; yalniz 0 ile baslayan rakam obegi (plakada olmaz, telefon basidir: '08:30 TEL 0500 000 00 00')
# bir rakam dizisinin ortasinda bitmez (telefonun basini yutup kuyrugunu acikta birakiyordu)
_PLAKA = (r"(?<!\w)(?:0[1-9]|[1-7]\d|8[01]) ?(?!(?:TL|TRY|KG|TON|KDV|ADET|LT|GR|CM|MM|USD|EUR)\b)[A-Z]{1,3} ?"
          r"(?:[1-9]\d{1,3}(?!\w)|0\d{1,3}(?!\w)(?![ \-.]\d))")
_EMAIL = r"(?<![\w.+\-])[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+"   # basta sinir: uzun sozcukte karesel tarama yok
# sosyal profil adresindeki kullanici adi, WhatsApp kanal kimligi ve grup davet kodu, wa.me numarasi (alan adi ve
# yol kalir, kisisel parca maskelenir). Yol ayraci URL kodlu da olur ('%2Fchannel%2F<kimlik>', yonlendirme baglantisinda)
_SL = r"(?:/|%2F)"
_SOCIAL = (r"(?i:(?<![\w\-.])(?P<sp>(?:https?(?::|%3A)" + _SL + "{2})?(?:www\\.|m\\.|mobile\\.|tr\\.|web\\.)?"
           r"(?:instagram\.com|facebook\.com|fb\.com|twitter\.com|x\.com|tiktok\.com|youtube\.com|t\.me|threads\.net|"
           r"linkedin\.com|whatsapp\.com" + _SL + "channel|chat\\.whatsapp\\.com)" + _SL
           + "(?:(?:in|stories|c|user|invite)" + _SL + ")?)"
           r"(?!(?:p|reel|reels|explore|watch|share|groups|hashtag|tv|shorts|events|pages|search|status|home|login|company|"
           r"school|jobs|posts|feed|results|i|intent|hashtag|embed|playlist)(?:[/?#]|$|[^\w.\-]))"
           r"(?P<sh>profile\.php\?id=\d+|@?[\w][\w.\-]*[\w]|@?\w))")
_WAME = r"(?i:(?<![\w\-.])(?P<wp>(?:https?://)?(?:api\.)?wa\.me/)\+?(?P<wn>\d{6,15})(?!\d))"
# metinde tek basina sosyal kullanici adi: '@' + harf/rakam, icinde '.' ya da '_' (@xandor.plimm). '@' + rakam telefon,
# '@Ad' anma kurali ayri; e-posta (onunde harf) degil
_HANDLE = re.compile(r"@(?<![\w.+\-@/]@)(?=[\w.]*(?:\.\w|_))\w[\w.]*\w")   # Anonymizer.text: '@' varsa, rx'ten once
_TR_I = "iIıİ"


_TR_PAIRS = {"c": "çÇ", "g": "ğĞ", "o": "öÖ", "s": "şŞ", "u": "üÜ"}
_TO_BASE = {x: b for b, xs in _TR_PAIRS.items() for x in xs}
_KEY_TR = str.maketrans({**{c: "i" for c in _TR_I}, **_TO_BASE})


@functools.lru_cache(maxsize=1 << 16)
def _key(s):
    """Buyuk/kucuk harf, Turkce i/I/ı/İ ve ASCII-katlama (ç->c, ğ->g, ö->o, ş->s, ü->u) duyarsiz anahtar."""
    return nfc(s).translate(_KEY_TR).lower()


def _name_regex(name, cap=False):
    """Buyuk/kucuk harf ve Turkce harf duyarsiz ad ifadesi. cap: her sozcugun ilk harfi yalniz buyuk harf (S3/S7: yalniz
    buyuk harfli bicimiyle yayilan ad; 'Sıcak Çorba' eslesir, 'sıcak çorba' eslesmez)."""
    out, head = [], True
    for c in nfc(name):
        if c in _TR_I:
            out.append("[Iİ]" if cap and head else f"[{_TR_I}]")
        elif c.isspace():
            out.append(r"\s+")
            head = True
            continue
        elif c.isalpha():
            b = _TO_BASE.get(c, c.lower())
            cls = {b, b.upper(), *_TR_PAIRS.get(b, "")} if b in _TR_PAIRS else {c, c.lower(), c.upper()}
            if cap and head:
                cls = {x for x in cls if x.isupper()} or cls
            out.append("[" + "".join(re.escape(x) for x in sorted(cls) if len(x) == 1) + "]")    # sirali: ayni harf, ayni ifade
        else:
            out.append(re.escape(c))
        head = False
    return "".join(out)


# Nakliye sektor sozcukleri: TEK liste. Ticari adda (_FIRM_TAIL, Anonymizer._special) ve ciplak alan adinda
# (Anonymizer._web) ayni sozcukler; _SECTOR_GENERIC'tekiler genel ya da kisa oldugu icin alan adinda aranmaz (buyuk kargo
# firmalari, 'translate', 'nakit'). Ekli bicimler (Nakliyattan, Nakliyatın, Lojistiği) _SECTOR_SFX ile.
_SECTOR_W = ("nakliyat nakliye nakliyeci nakliyecilik lojistik taşımacılık taşıma transport trans kargo logistics logistic "
             "nak nakl nakliyatı nakliyesi lojistiği taşımacılığı").split()
_SECTOR_GENERIC = set("taşıma trans kargo nak nakl".split())
_SECTOR_SFX_W = ("ı i sı si ın in nın nin a e ya ye da de ta te dan den tan ten la le yla yle lar ler ları leri cı ci "
                 "cılar ciler cılık cilik ımız imiz").split()
_SECTOR_KEY = re.compile("(?:" + "|".join(sorted({_key(w) for w in _SECTOR_W}, key=len, reverse=True)) + ")(?:"
                         + "|".join(sorted({_key(w) for w in _SECTOR_SFX_W}, key=len, reverse=True)) + ")?")


@functools.lru_cache(maxsize=1 << 14)
def _is_sector(k):
    """Anahtar bicimli sozcuk sektor sozcugu mu (ekli bicimi dahil: nakliyattan, lojistigi)."""
    return bool(_SECTOR_KEY.fullmatch(k))


# ilke 4: GUCLU sektor sozcugu (ticari ad ilan imi olmadan da maskelenir): nakliyat, nakliye, nakliyeci(lik), lojistik,
# taşımacılık, logistic(s) ve ekli bicimleri. Zayif tetikleyiciler (taşıma, trans, transport, kargo, Nak., şirketi,
# firması) ilan imi ister ('HTTP Transport ayarı', 'Annem Kargo'dan aldı', 'Elektrik Şirketi aradı').
_SECTOR_WEAK = _SECTOR_GENERIC | {"transport"}
_SECTOR_STRONG_KEY = re.compile("(?:" + "|".join(sorted({_key(w) for w in _SECTOR_W if w not in _SECTOR_WEAK}, key=len,
                                                          reverse=True)) + ")(?:"
                                + "|".join(sorted({_key(w) for w in _SECTOR_SFX_W}, key=len, reverse=True)) + ")?")


@functools.lru_cache(maxsize=1 << 14)
def _is_strong_sector(k):
    return bool(_SECTOR_STRONG_KEY.fullmatch(k))


# F: ciplak isletme alan adi ('www.ornekfirmaNakliyat.com.tr', 'nakliyat.ornekfirma.com.tr', 'www.ornekfirma.nakliyat.com'). Dar kural:
# yalniz ticari uzantilar (.com/.net/.biz/.info/.tr, .com.tr...; .org/.gov/.edu degil); yalniz kayitli ad ve hemen ustundeki
# alt alan (www/m on ekleri sayilmaz) bakilir; bunlardan birinde genel olmayan sektor sozcugu varsa, bu iki etiketten AYIRT
# EDICI olan(lar) [firma] olur. Sektor sozcugunu cikarinca yalniz ek kalan etiket ('nakliyat', 'transportation') genel
# sozcuktur, firma degildir. Yazilim sohbetindeki baglantilar (github.com, belgeler, urunun kendi alan adlari) bu sozcukleri
# icermez, okunur kalir. Ana makine dogrusal eslesir ([\w-]+ etiketleri); sektor sozcugu _web()'de aranir (eski kalip
# '[\w-]*(sozcuk)[\w-]*' uzun sozcukte karesel taraniyordu). Buyuk/kucuk harf duyarsiz (KAPLONAKLİYAT.COM).
_WEB_KEYS = tuple(sorted({_key(w) for w in _SECTOR_W if w not in _SECTOR_GENERIC}, key=len, reverse=True))
_WEB_AFFIX = set("ation ations s er ers ci cilik i si in tr turk online net web app api mail portal panel blog shop "
                 "store admin destek".split()) | {""}
_WEB_PRE = {"www", "m", "mobile", "tr", "en", "web"}
_WEB_SQ = re.compile("|".join(_WEB_KEYS))
_WEB_STRONG = re.compile("|".join(w for w in _WEB_KEYS if w not in {_key(x) for x in _SECTOR_WEAK}))   # S9
_TR_SLD_NC = {"org", "gov", "edu", "k12", "bel", "pol", "tsk", "av", "dr", "name", "tv", "bbs", "tel", "mil"}   # ticari degil
_WEB = (r"(?i:(?<![\w\-.@/%])(?P<wbp>(?:https?://)?)(?P<wbh>(?:[\w\-]+\.)*?[\w\-]+)"
        r"(?P<wbt>\.(?:com|net|biz|info)(?:\.tr)?|\.(?:web|gen|biz)\.tr|\.tr)(?![\w\-]|\.\w))")
_WEB_RX = re.compile(_WEB)
_WEB_Q = re.compile(r"(?i:\.(?:com|net|biz|info|tr)(?![\w\-]))")   # on suzgec: ticari uzanti yoksa alan adi kurali calismaz


def _web_distinct(k):
    """Alan adi etiketi (anahtar bicimi) ayirt edici mi: sektor sozcukleri, rakam ve tire cikinca anlamli parca kalir."""
    rest = re.sub(r"[\d\-_]+", "", k)
    for w in _WEB_KEYS:
        rest = rest.replace(w, "")
    return rest not in _WEB_AFFIX


# Maskelenmis ana makineli URL'nin geri kalani (yol, sorgu, parca) da kapanir: 'https://www.Kişi 8.com/[yol]',
# 'www.[firma].com.tr/[yol]'. Ana makinede katilimci etiketi, [firma] ya da sohbet etiketi olmali (Anonymizer.text).
_URL_TLD = r"(?:com|net|org|biz|info|io|co|app|dev|me|edu|gov|online|site|shop|store|web|gen|[a-z]{2})"
_URL_Q = re.compile(r"\.[A-Za-z]{2,6}[/?#]")       # on suzgec: uzanti + yol
_CLOSERS = {")": "(", "]": "[", "}": "{"}


_CAT_MIN = 6          # bitisik/ayrik ad biciminde en az harf sayisi
_TOKEN_BEFORE = set("_/-.@:=#%~")
_TOKEN_AFTER = set("_/#?@=:%~")


def _windows(toks, min_len=2):
    """Ardisik >=2 parcali alt diziler ve tersleri (>=6 harf; her parca >=2 karakter)."""
    out = []
    for i in range(len(toks)):
        for j in range(i + 2, len(toks) + 1):
            w = toks[i:j]
            if all(len(t) >= min_len for t in w) and sum(map(len, w)) >= _CAT_MIN:
                for f in (w, w[::-1]):
                    if f not in out:
                        out.append(f)
    return out


def _part_combos(toks):
    """Cok parcali adin bosluklu bicimleri: _windows (ardisik parcalar + tersleri, >=6 harf) ve parcalarin sirasi
    korunmus her >=2'li secimi (ilk+son, orta+son, ilk+orta; kisa parca dahil: 'Ali Su'). Kisa parca yalniz ayni
    katilimcinin baska parcasinin yaninda maskelenir; tek basina (su, er, ok) dokunulmaz."""
    out = _windows(toks)
    idx = [i for i, t in enumerate(toks[:6]) if len(t) >= 2 and t[0].isalpha()]
    for r in range(2, len(idx) + 1):
        for c in itertools.combinations(idx, r):
            f = [toks[i] for i in c]
            if f not in out:
                out.append(f)
    return out


def _concat_forms(name):
    """Cok parcali ad -> bitisik/ayrik bicimlerin parca listeleri: her ardisik alt dizi + tersi, ayrica ilk+son."""
    toks = [t for t in (re.sub(r"[^\w]", "", t) for t in nfc(name).split()) if t]
    forms = _windows(toks)
    if len(toks) > 2:
        for f in ([toks[0], toks[-1]], [toks[-1], toks[0]]):
            if f not in forms and all(len(t) >= 2 for t in f) and sum(map(len, f)) >= _CAT_MIN:
                forms.append(f)
    return forms


def _alt(items):
    return "(?:" + "|".join(sorted({_name_regex(x) for x in items}, key=len, reverse=True)) + ")"


def _first_alt(names):
    """Ad seceneklerini harf harf onek agacinda (trie) birlestirir: her harf ifadesi (_name_regex: buyuk/kucuk harf ve Turkce
    harf duyarsiz) bir konumda bir kez denenir, ortak onekli adlar ayni daldadir (6. tur hizi: ogrenilen ad sayisi satir
    basina maliyeti buyutmez; eskiden yalniz ilk harfe gore gruplanip grup icinde her ad tek tek deneniyordu). Bir adin
    bittigi dugumun devami acgozlu istege baglidir: ayni konumda once en uzun ad denenir, eslesme sonradan bozulursa kisa
    ada donulur; kardes dallar en uzun adlarina gore sirali (ortusen harf ifadelerinde de uzun ad once)."""
    root, tok = {}, {}
    for n in map(nfc, names):
        node = root
        for c in n:
            node = node.setdefault(tok.get(c) or tok.setdefault(c, _name_regex(c)), {})
        if node is not root:
            node[None] = {}
    depth = {}

    def deep(node):
        if id(node) not in depth:
            depth[id(node)] = max((deep(ch) + 1 for t, ch in node.items() if t is not None), default=0)
        return depth[id(node)]

    def gen(node):
        alts = [t + gen(ch) for t, ch in sorted(((t, ch) for t, ch in node.items() if t is not None),
                                                key=lambda x: -deep(x[1]))]
        if not alts:
            return ""
        body = alts[0] if len(alts) == 1 else "(?:" + "|".join(alts) + ")"
        return "(?:" + body + ")?" if None in node else body
    return gen(root)


# Kapali ek listesi (tek parca adlara apostrofsuz eklenebilen): kucultme/sevgi + cogul + iyelik + hal ekleri.
_SFX_DIM = [c + v + g + w + m for c in "cç" for v in "ıiuü" for g in ("ğ",) for w in "ıiuü" for m in ("m",)] + [
    c + v + k for c in "cç" for v in "ıiuü" for k in "mk"]
_SFX_PL = ["lar", "ler"]
_SFX_POSS = ["ım", "im", "um", "üm", "ın", "in", "un", "ün"]
_SFX_CASE = ["a", "e", "ya", "ye", "ı", "i", "u", "ü", "yı", "yi", "yu", "yü", "da", "de", "ta", "te", "dan", "den",
             "tan", "ten", "la", "le", "yla", "yle", "nın", "nin", "nun", "nün", "ca", "ce", "çe", "ça"]
_SFX_RX = (f"(?:{_alt(_SFX_DIM)}?{_alt(_SFX_PL)}?{_alt(_SFX_POSS)}?{_alt(_SFX_CASE)}?)")


# ---- parola / gizli anahtar maskeleme (sezgisel; ayni tek Anonymizer yolu)
_KW_SUF = ["şifre", "parola", "token", "login", "anahtar", "api key", "apikey", "api-key", "api_key", "giriş bilgi"]
_KW_EXACT = ["passwd", "password", "pass", "pwd", "pw", "pin"]
_KW = (r"(?<!\w)(?:" + _alt(_KW_SUF) + r"(?:['’]?\w*)|" + _alt(_KW_EXACT) + r"s?)(?!\w)")
_KW_SEP = r"(?P<sep>[ \t]*[:=][ \t]*|[ \t]+[-–—][ \t]+|[ \t]+)"
_KW_RX = re.compile(_KW + _KW_SEP)
_KW_END = re.compile(_KW + r"[ \t]*[:=\-–—]?[ \t]*$")
_KW_ANY = re.compile(_KW)
_OTP_KW = re.compile(r"(?<!\w)(?:" + "|".join(_name_regex(x) + r"\w*" for x in ("kod", "doğrulama", "onay")) + r"|[Oo][Tt][Pp])(?!\w)")
_OTP_NUM = re.compile(r"(?<![\w.,:/\-+])\d{4,8}(?!\w|[.,:/]\d|\s?(?:TL|₺|TRY|KG|TON|ADET|KDV|USD|EUR)\b)")
_SECRET = re.compile("|".join([
    r"(?<!\w)gh[pousr]_[A-Za-z0-9]{20,}",
    r"(?<!\w)github_pat_[A-Za-z0-9_]{20,}",
    r"(?<!\w)sk-[A-Za-z0-9_\-]{16,}",
    r"(?<!\w)AKIA[0-9A-Z]{16}(?!\w)",
    r"(?<!\w)eyJ[\w\-]{5,}\.[\w\-]{5,}\.[\w\-]{5,}",
    r"(?<![\w/.\-])[0-9a-fA-F]{32,}(?!\w)",
    r"(?<![\w/.\-+=])(?=[A-Za-z0-9+/_\-]*\d)(?=[A-Za-z0-9+/_\-]*[A-Za-z])[A-Za-z0-9+/_\-]{32,}={0,2}(?!\w)",
]))
_RANDOM = re.compile(
    r"(?<![\w.\-/+=@:#%])(?=[A-Za-z0-9_\-+=]*[a-z])(?=[A-Za-z0-9_\-+=]*[A-Z])(?=[A-Za-z0-9_\-+=]*\d)"
    r"[A-Za-z0-9_\-+=]{16,}(?!\w|[\-/@:]|\.\w)")   # >=16 karakter, kucuk+buyuk+rakam; dosya adi/URL/e-posta degil
_BEARER = re.compile(r"(?<!\w)([Bb]earer\s+)[A-Za-z0-9._\-+/=]{12,}")
_UNITS = r"(?:TL|TRY|KDV|KG|TON|ADET|LT|GR|CM|MM|USD|EUR|M2|M3|KM|SA|DK|SN|MT|GUN|GÜN|SAAT)"
_NOT_SECRET = re.compile(r"(?i:\d[\d.,]*\+?" + _UNITS + r"|[\d.,:/\-+]+|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|#\d+)|[0-9a-f]{7,12}")
_STOP = {_key(x) for x in ("yok", "var", "ne", "neydi", "nedir", "bu", "şu", "su", "aynı", "değişti", "degisti", "unuttum",
                          "bilmiyorum", "gönderdim", "yeni", "eski", "tamam", "evet", "hayır", "hayir", "ve", "ile")}
_CODE_CTX = re.compile(r"whatsapp|(?<!%sw)web(?!%sw)|bagla|esle|qr" % (chr(92), chr(92)))
_EDGE = "\"'`()[]<>.,;:!?"
_WA_MEDIA = re.compile(r"(?:IMG|VID|PTT|DOC|STK|AUD)-\d{8}-WA\d{4,}(?:\.[A-Za-z0-9]{1,5})?")   # WhatsApp medya adi


def _cred_like(tok, digits=False):
    """Parola gibi mi: >=6 karakter, URL/tarih/saat/birimli sayi/plaka/telefon degil, >=2 karakter sinifi."""
    core = tok.strip(_EDGE)
    if _WA_MEDIA.fullmatch(core):       # IMG-20240101-WA0001.jpg: WhatsApp'in kendi adi, parola degil
        return False
    if digits and re.fullmatch(r"\d{%d,8}" % digits, core):
        return True
    if len(core) < 6 or "://" in core or core.lower().startswith("www.") or core.startswith(("[", "#", "@")):
        return False
    if _NOT_SECRET.fullmatch(core) or re.fullmatch(_EMAIL, core):
        return False
    if any(re.fullmatch(x, core) for x in (_PHONE, _PLAKA, _TCKN, _IBAN)):
        return False
    low = any(c.islower() for c in core)
    up = any(c.isupper() for c in core)
    dig = any(c.isdigit() for c in core)
    sym = any(not c.isalnum() and c not in "'’" for c in core)
    if core.isalpha() and not any(c.isupper() for c in core[1:]):
        up = False
    return sum((low, up, dig, sym)) >= 2


def _mask_tok(tok, sink=None):
    """Anahtar kelimeden sonra gelen degeri [parola] yapar; sondaki .,; kalir. sink: maskelenen degerler (yalniz bellek)."""
    core = tok.rstrip(".,;")
    if sink is not None and _cred_like(core, 4):
        sink.add(core.strip(_EDGE))
    return "[parola]" + tok[len(core):]


def _next_line_value(line):
    t = line.strip()
    return (len(t) >= 4 and not re.search(r"\s", t) and "://" not in t and not t.startswith(("[", "#"))
            and not re.fullmatch(_EMAIL, t) and _key(t.strip(_EDGE)) not in _STOP and not _WA_MEDIA.fullmatch(t.strip(_EDGE)))


def _cred_line(line, sink=None):
    """Tek satir: gizli anahtar sekilleri, anahtar kelime+deger, tek seferlik kod. -> (satir, deger_bekliyor)."""
    line = _BEARER.sub(lambda m: m.group(1) + _mask_tok(m.group(0)[len(m.group(1)):], sink), line)
    line = _SECRET.sub(lambda m: _mask_tok(m.group(0), sink), line)
    line = _RANDOM.sub(lambda m: _mask_tok(m.group(0), sink), line)
    spans, pos = [], 0
    for m in _KW_RX.finditer(line):
        if m.start() < pos:
            continue
        v = re.match(r"\S+", line[m.end():])
        if not v:
            continue
        tok = v.group(0)
        loose = any(c in m.group("sep") for c in ":=")
        core = tok.strip(_EDGE)
        if _KW_ANY.fullmatch(core) or "://" in tok or tok.startswith("[") or _key(core) in _STOP or _WA_MEDIA.fullmatch(core):
            continue
        digits = 4 if _key(m.group(0)).startswith("pin") else 0
        if (len(core) >= 3 if loose else _cred_like(tok, digits)):
            spans.append((m.end(), m.end() + len(tok), tok))
            pos = m.end() + len(tok)
    for a, b, tok in reversed(spans):
        line = line[:a] + _mask_tok(tok, sink) + line[b:]
    if _OTP_KW.search(line):
        line = _OTP_NUM.sub("[kod]", line)
    pending = (not spans) and bool(_KW_END.search(line))
    return line, pending


# ---- sistem satirlarindaki kisiler (eklendi/katildi/ayrildi/...): Ingilizce ve Turkce yerel
_SYS_PATTERNS = [re.compile(p, re.I) for p in (
    r"^your security code with (?P<s>.+?) changed\b",
    r"^(?P<s>.+?) changed to (?P<same>\+?\d[\d ()\-]{6,}\d)\b",
    r"^(?P<s>.+?) made (?P<o>.+?) an? admin\b",
    r"^(?P<s>.+?) (?:added|removed) (?P<o>.+?)\.?$",
    r"^(?P<s>.+?) (?:created group|created this group|changed the subject|changed the group|changed this group|"
    r"deleted this group|reset this group|joined using|joined from|joined via|left\b|was added|was removed|"
    r"is now an admin|requested to join|changed their phone number|changed the settings|pinned a message|"
    r"started a (?:video |voice )?call|turned (?:on|off))",
    r"^(?P<s>.+?) ile güvenlik kodunuz değişti",
    r"^(?P<s>.+?),? (?P<same>\+?\d[\d ()\-]{6,}\d) numaras[ıi]na geçti",
    r"^(?P<s>[^,]+?), (?P<o>.+?)(?: adlı kişiyi| adlı kişileri| kişisini| kişilerini)? (?:ekledi|çıkardı|yönetici yaptı)\.?$",
    r"^(?P<s>.+?) (?:sizi|seni) (?:ekledi|çıkardı)",
    r"^(?P<s>.+?),? (?:[\"“].*[\"”] )?(?:grubunu|grubu) oluşturdu",
    r"^(?P<s>.+?) (?:bu grubun|grubun|grup |konuyu|telefon numarasını|numarasını|davet bağlantısı|bu grubu|topluluktan|"
    r"gruptan|bir mesajı sabitledi|aramayı başlattı|artık yönetici)",
    r"^(?P<s>.+?) (?:katıldı|ayrıldı|eklendi|çıkarıldı)\.?$",
)]
_SUBJECT = re.compile(r"created group|changed the subject|changed the group name|changed this group's name|"
                      r"grubunu oluşturdu|konuyu|grup adını|grubun adını|olarak değiştirdi", re.I)
_QUOTED = re.compile(r"([\"“])([^\"“”\n]{1,200})([\"”])")
_SYS_SPLIT = re.compile(r",\s*(?:and\s+|ve\s+)?|\s+(?:and|ve)\s+")
_SYS_NOT = {"you", "your", "siz", "sizi", "seni", "sen", "ben", "beni", "biz"}
_SYS_BAD = re.compile(r"[\"“”:/@]|https?|\b(?:messages?|mesaj\w*|group|grub?\w*|this|bu)\b", re.I)


def system_people(body):
    """Sistem satiri -> [(kisi, ayni_kisi_ise_onceki)]: eklenen/katilan/ayrilan/degistiren kisiler (numaralar dahil)."""
    body = INVISIBLE.sub("", body or "").strip()
    out = []

    def add(x, same=None):
        x = re.sub(r"['’][a-zçğıöşü]+$", "", " ".join(x.split()).lstrip("~ ").strip(" .,;"))   # Naime'yi -> Naime
        if not x or x.lower() in _SYS_NOT or len(x) > 40 or len(x.split()) > 5 or _SYS_BAD.search(x):
            return
        if not any(c.isalpha() for c in x) and sum(c.isdigit() for c in x) < 7:
            return
        out.append((x, same))

    for p in _SYS_PATTERNS:
        m = p.match(body)
        if not m:
            continue
        g = m.groupdict()
        add(g["s"])
        for x in _SYS_SPLIT.split(g.get("o") or ""):
            add(x)
        if g.get("same"):
            add(g["same"], same=" ".join(g["s"].split()).lstrip("~ ").strip(" .,;"))
        break
    return out


# iOS sistem satirlari gonderen yerinde grup adiyla gelir ('[..] Grup: Ali added Veli'); kisisiz bildirimler de oyle
_SYS_NOTICE = re.compile(r"end-to-end encrypted|uçtan uca şifreli|disappearing messages|süreli mesaj|security code|"
                         r"güvenlik kod|group description|grup açıklama|admin approval|only admins|yalnızca yönetici|"
                         r"changed (?:the|this) group|group icon|grup simgesi|grup resmi", re.I)
_GROUP_EVT = re.compile(r"\b(?:added|removed|joined|left|created (?:this )?group|changed the subject|changed (?:the|this) "
                        r"group|is now an admin|made .+ admin)\b|\b(?:ekledi|çıkardı|katıldı|ayrıldı|oluşturdu|gruptan|"
                        r"grubun|bu grubu|konuyu|yönetici)", re.I)


def _body(m):
    return " ".join(v for k, v in message_parts(m) if k == "text" and v) if ("parts" in m or "lines" in m) else ""


def _system_shaped(body):
    return bool(system_people(body) or _SUBJECT.search(body) or _SYS_NOTICE.search(body))


# Yalniz grupta olan olaylar (tam satir): sohbetin grup oldugunu ve iOS'ta grup adiyla gelen satirin sistem satiri
# oldugunu yalniz bunlar soyler. Siradan mesajda da gecen sozcukler ('Kardeşim de katıldı.', 'Ali ayrıldı') sayilmaz.
_GRP_ONLY = [re.compile(p, re.I) for p in (
    r'^(?P<s>.+?) created (?:group [\"“].*[\"”]|this group)\.?$',
    r"^(?P<s>.+?) (?:added|removed) (?P<o>.+?)\.?$",
    r"^(?P<s>.+?) joined (?:using this group's invite link|using an invite link|from the community|via invite link)",
    r"^(?P<s>.+?) changed (?:the subject|this group's icon|the group description|this group's settings|the group name|"
    r"this group's name|the group icon)\b",
    r"^(?P<s>.+?) (?:is now an admin|made .+ an? admin)\b",
    r"^you(?:'re| are) now an admin\b|^you were added\b",
    r'^(?P<s>.+?),? (?:[\"“].*[\"”] )?(?:grubunu|grubu) oluşturdu\.?$',
    r"^(?P<s>[^,]+?), (?P<o>.+?)(?: adlı kişiyi| adlı kişileri| kişisini| kişilerini)? (?:ekledi|çıkardı)\.?$",
    r"^(?P<s>.+?) (?:sizi|seni) (?:ekledi|çıkardı)\b",
    r"^(?P<s>.+?),? (?:bu grubun |grubun )?davet bağlantısı(?:yla| ile|nı kullanarak) katıldı",
    r"^(?P<s>.+?) (?:konuyu|grup adını|grubun adını|grup simgesini|grubun simgesini|bu grubun simgesini|grup açıklamasını|"
    r"grubun açıklamasını|grubun ayarlarını|bu grubun ayarlarını) ",
    r"^(?P<s>.+?),? gruptan ayrıldı\.?$",
    r"^(?P<s>.+?),? (?:artık yönetici|(?P<o>.+?) adlı kişiyi yönetici yaptı)",
)]
# grupta, grup adiyla gelen ad bicimli olay satiri ('Jorvik Plimm left', '+90 500 ... katıldı'): yalniz donusturmede
_GRP_WEAK = re.compile(r"^(?P<s>.+?),? (?:left|joined|was added|was removed|ayrıldı|katıldı|eklendi|çıkarıldı)\.?$", re.I)


_EVT_MAX = 1000     # bundan uzun satir olay/sistem satiri sayilmaz (gercek olay satirlari birkac yuz karakter)
# on eleme: olay, sistem satiri ve bildirim desenlerinin (_GRP_ONLY, _GRP_WEAK, _SYS_PATTERNS, _SYS_NOTICE) anahtar
# sozcuklerinden biri yoksa satir olay/bildirim degildir (duz alt dize aramasi: buyuk mesaj akisinda hizli)
_EVT_WORDS = (
    "added", "removed", "changed", "made", "created", "deleted", "reset", "joined", "left", "was ", "is now", "now an",
    "requested", "pinned", "started", "turned", "security", "you were", "encrypted", "disappearing", "description",
    "admin", "icon", "ekledi", "çıkardı", "çıkarıldı", "eklendi", "katıldı", "ayrıldı", "oluşturdu", "yönetici", "grubun",
    "grup ", "grubu", "gruptan", "konuyu", "numaras", "güvenlik", "davet", "topluluktan", "sabitledi", "aramayı",
    "şifreli", "süreli", "açıklama", "simgesi", "resmi")


def _evt_quick(body):
    low = body.lower()
    return any(w in low for w in _EVT_WORDS)


def _name_shaped(x):
    """Sistem satirindaki kisi gibi mi: 1-5 sozcuk, harf iceren her sozcuk buyuk harfle (ya da numara, 'you/sizi')."""
    x = re.sub(r"['’][a-zçğıöşü]+$", "", " ".join(x.split()).lstrip("~ ").strip(" .,;"))
    if _key(x) in {"you", "sizi", "seni", "siz"} or re.fullmatch(r"\+?\d[\d ()\-]{6,}\d", x):
        return True
    toks = x.split()
    return 1 <= len(toks) <= 5 and all(t[:1].isupper() or not any(c.isalpha() for c in t) for t in toks)


def group_only_event(body, weak=False):
    """Tam satir yalniz grupta olan bir olay mi (grup kuruldu, eklendi/cikarildi, davet baglantisiyla katildi, konu/simge/
    aciklama degisti, yonetici). Eklenen/cikarilan kisiler ad bicimli olmali ('I added salt' olay degil).
    weak=True: ad bicimli 'X left / X ayrıldı / X katıldı' da (yalniz grup oldugu bilinen sohbette donusturmek icin)."""
    body = INVISIBLE.sub("", body or "").strip()
    if len(body) > _EVT_MAX or not _evt_quick(body):    # olay satiri kisadir; uzun mesajda tembel desenler karesel
        return False                                      # tarar
    for p in _GRP_ONLY:
        m = p.match(body)
        if m:
            o = m.groupdict().get("o")
            if o is None or all(_name_shaped(x) for x in _SYS_SPLIT.split(o) if x.strip()):
                return True
    if weak:
        m = _GRP_WEAK.match(body)
        return bool(m and _name_shaped(m.group("s")))
    return False


@functools.lru_cache(maxsize=1 << 15)
def title_event_line(body):
    """Grupta, gonderen yerinde grup adiyla gelen satir bir olay mi: yalniz grupta olan olay ya da kisileri ad bicimli
    sistem satiri ('Jorvik Plimm left'). 'Kardeşim de katıldı.' degil. mark_system_lines ve Anonymizer ayni kurali kullanir."""
    if len(body or "") > _EVT_MAX or not _evt_quick(body or ""):
        return False
    if group_only_event(body, weak=True):
        return True
    sp = system_people(body)
    return bool(sp) and all(_name_shaped(x) for x, _ in sp)


@functools.lru_cache(maxsize=1 << 12)
def _loose(s):
    return re.sub(r"[\W_]+", "", _key(s))


def title_senders(msgs, chat):
    """Sohbet adiyla ayni olan gonderen adlari kumesi (dosya adinda duşen karakterlere toleransli: buyuk/kucuk harf,
    Turkce harf, noktalama/bosluk farki). Her ayri gonderen icin bir kez karsilastirilir."""
    ck, loose = _key(chat or ""), _loose(chat or "")
    return {s for s in {m.get("sender") for m in msgs} if s and (_key(s) == ck or (bool(loose) and _loose(s) == loose))}


def is_group(msgs, chat=None):
    """Grup sohbeti mi; disa aktarimin kendisinden, TUM dosya uzerinden (tarih suzgecinden once) karar verilir, baslik
    sozcuklerinden degil. Grup: sohbet adi olmayan en az 2 ayri gonderen (bire bir sohbette gonderenler karsidaki kisi =
    sohbet adi ve disa aktaran kisidir), ya da yalniz grupta olan olay: Android'de gonderensiz sistem satiri, iOS'ta
    gonderen yerinde sohbet adiyla gelen tam satir olay (group_only_event). Aksi: bire bir."""
    titles = title_senders(msgs, chat)
    if len({_key(s) for s in {m.get("sender") for m in msgs} if s and s not in titles}) >= 2:
        return True
    for m in msgs:
        s = m.get("sender")
        if s is None and _GROUP_EVT.search(_body(m)):
            return True
        if s is not None and s in titles and group_only_event(_body(m)):
            return True
    return False


def mark_system_lines(chat, msgs, group=None):
    """iOS grup sohbeti: gonderen yerinde sohbet adiyla gelen satir, SATIR SATIR karar verilerek sistem satiri olur
    (sender None): yalniz grupta olan olay, ad bicimli katildi/ayrildi, kisisiz bildirim (sifreleme, guvenlik kodu);
    o gonderenin tum satirlari sistem bicimindeyse hepsi. Grup adiyla ayni adli uye (rehberde 'Annem') gercek mesajlarini
    yazmaya devam eder. Bire bir sohbette (group False; None ise is_group) hicbir satira dokunulmaz. Yeni liste dondurur."""
    if group is None:
        group = is_group(msgs, chat)
    if not group:
        return msgs
    titles = title_senders(msgs, chat)
    mine = [m for m in msgs if m.get("sender") in titles] if titles else []
    if not mine:
        return msgs
    bodies = {id(m): _body(m) for m in mine}
    pure = all(_system_shaped(b) for b in bodies.values())     # grup adi yalniz sistem satiri yaziyor (uye degil)
    ids = {i for i, b in bodies.items() if (pure and _system_shaped(b))
           or (_evt_quick(b) and (title_event_line(b) or _SYS_NOTICE.search(b)))}
    return [dict(m, sender=None) if id(m) in ids else m for m in msgs] if ids else msgs


# ---- ad sozlugu (adlar/*.txt; Wikidata CC0) ve baglam kurallari
_HERE = os.path.dirname(os.path.abspath(__file__))
_LISTS = {}
_TAKVIM = {_key(x) for x in ("ocak şubat mart nisan mayıs haziran temmuz ağustos eylül ekim kasım aralık pazartesi salı "
                             "çarşamba perşembe cuma cumartesi pazar").split()}
_CAPWORD = {_key(x) for x in "türk ege asya medine islam kuzey güney doğu akdeniz karadeniz".split()}
_HON = re.compile(r"(?:bey|beyefendi|hanim|hanimefendi|abi|abla|hoca|baskan|kardes|amca|teyze|usta|agabey|abey|reis|dayi)"
                  r"(?:ler|lar)?(?:imiz|umuz|miz|muz|im|um|m)?(?:cigim|cugum|cim|cum)?"
                  r"(?:['\u2019]?(?:yle|yla|nin|nun|den|dan|ye|ya|yi|yu|in|un|de|da|le|la|si|e|a|i|u))?")   # _key bicimi
_HON_ORG = re.compile(r"baskani(?!m)[a-z]*|baskanlig[a-z]*")       # Dernek Başkanı: onundeki sozcuk kurum adidir
_HON_STOP = {_key(x) for x in (
    "tamam selam merhaba merhabalar günaydın iyi evet hayır sağol sağolun teşekkürler teşekkür aynen peki tabi tabii olur "
    "hadi haydi hayırlı kolay rica estağfurullah eyvallah valla vallahi allah sayın değerli kıymetli sevgili muhterem "
    "saygıdeğer canım ben sen siz biz onlar bu şu o ve ile ya yok var ne nasıl kusura geçmiş hoş hoşgeldin hoşgeldiniz "
    "lütfen bence genel yönetim kurulu kurul bölge şube il ilçe dernek derneği grup grubu ekip ekibi takım merkez müdür "
    "müdürlük daire belediye belediyesi oda odası vakıf vakfı federasyon kulüp kulübü birlik birliği komisyon meclis "
    "onursal eski yeni sağ baş başkan abi abla hocam hoca usta amca teyze kardeş bey hanım reis dayı ağabey "
    "selamlar selamün aleyküm aleykümselam teşekkürlerim kardeşim abim başkanım hocamız ustam hayırdır günler geceler "
    "akşamlar iyiyim tebrikler tebrik bravo süper harika güzel aferin maşallah inşallah amin hakkınızda hakkın "
    "doktor dr av müh öğretmen kaptan komutan şef ekibimiz arkadaşlar arkadaşım dostum kanka reisim").split()}
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")
_APOS = re.compile("['’]")
_GAP_INI = re.compile(r"[.!?…:;]")
_LABEL_AFTER = re.compile(r" (?:\d|\?)")               # 'Kişi 3', 'Kişi ?': etiketin kendisi ad sanilmaz
# yer/kurum adi: ad + bu sozcuk (ya da araya buyuk harfli sozcukler) -> dokunulmaz (Mimar Sinan Üniversitesi, Hz. Muhammed)
_INST_ANY_W = ("üniversitesi lisesi hastanesi köprüsü caddesi bulvarı mahallesi camii stadı stadyumu ilkokulu ortaokulu "
               "havalimanı havaalanı fakültesi enstitüsü müzesi kütüphanesi istasyonu otogarı kampüsü").split()
_INST_CAP_W = ("sokağı sokak cad sok mah cami parkı meydanı okulu koleji barajı vakfı kışlası tüneli kulesi çarşısı pazarı "
               "köyü ilçesi apartmanı sitesi hanı oteli limanı yolu terminali yurdu salonu merkezi gölü dağı çayı ırmağı "
               "nehri tepesi kalesi türbesi").split()
_INST_ANY = re.compile("^(?:" + "|".join(_key(x) for x in _INST_ANY_W) + ")")
_INST_CAP = re.compile("^(?:" + "|".join(_key(x) for x in _INST_CAP_W) + ")$")
_INST_ANY_K = tuple(_key(x) for x in _INST_ANY_W)      # onek (Hastanesinde)
_INST_CAP_K = frozenset(_key(x) for x in _INST_CAP_W)   # tam sozcuk
_LM_NEXT = re.compile(r" ([^\W\d_]\w*)")            # tek bosluk + sozcuk (ozel ad obegi: araya noktalama girmez)
_LM_HZ = re.compile(r"(?:^|[^\w])(?:[Hh][Zz]|Hazreti|Hazret|HAZRETİ)\.?[ \t]*$")
_SURNAME_SFX = re.compile(r"..(?:oglu|ogullari|gil|soy|turk|demir|kaya|tas|yildiz|aslan|arslan|dogan)$")   # Öztürkoğlu
_FAMILY = {_key(x) for x in "aile ailesi ailemiz family kuzenler akrabalar sülale sülalesi".split()}
_TITLE_STOP = {_key(x) for x in "bizim benim sizin onların büyük küçük geniş mutlu canım güzel tatlı yeni eski".split()}
_SAYIN = {"sayin", "sn"}
_NOT_NAME_SFX = re.compile(r"(?:imiz|umuz|miz|muz|lar|ler|larimiz|lerimiz)$")   # Sayın Üyelerimiz, Sayın Yetkililer
_SAYIN_STOP = {_key(x) for x in (
    "yetkili ilgili müşteri katılımcı arkadaş meslektaş hocam başkanım müdürüm bakanım valim vekilim kaymakamım dekanım "
    "rektörüm hakim savcı avukat doktor dr av müh prof doç yrd öğretmen veli üye vatandaş okuyucu yolcu "
    "komutanım amirim kurul heyet").split()}

# ---- nakliye ilanlari: iletisim baglami, ticari ad, ilan sozlugu (anahtar bicimi; tek kod yolu: Anonymizer._scan)
# iletisim sozcugu: ardindaki (ayrac ya da satirda telefon varsa), onundeki ya da maskelenen telefonun yanindaki buyuk
# harfli 1-3 sozcuk kisi adidir
# S6: iletisim kanali sozcukleri ve sik yanlis yazimlari da (alan etiketidir, ad olarak ogrenilmez)
_CONTACT_W = ("irtibat irt iletişim ilt tel tlf telefon gsm cep yetkili sorumlu whatsapp wp whatsap watsap watsapp vatsap "
              "vatsapp wtsp wsp telegram").split()
# S3c: birim adi ('Muhasebe Birimi', 'Satış Departmanı', 'Gündüz Ekibi') kisi degildir: iletisim adi olarak alinmaz. Anahtar
# bicimi; iyelik eki sart, hal eki olabilir ('Biriminden'). Ticari ad kuralinda dislama yalniz durdurma listesidir (5. tur).
_ORG_UNIT = re.compile(r"(?:birim|departman|ekib|bolum|mudurlug|sube|ofis|servis|depo|merkez|grub|takim|kalem|sekreterlig)"
                       r"(?:i|u|si|su)(?:n|ne|na|nde|nda|nden|ndan|nin|nun|yle|yla)?")
_CONTACT = {_key(x) for x in _CONTACT_W}
# dolgu ve alan etiketi sozcukleri: iletisim baglaminda hicbir zaman ad degildir ('İRTİBAT İÇİN:', 'Tel No:',
# 'Hafta İçi Arayınız', '[telefon] Sadece WhatsApp', 'Yetkili Servis'); numara*/telefon*/iletişim*/irtibat* ekli bicimleri de
_FILLER_W = ("no nu nr numara için icin sadece yalnız yalnızca lütfen arayınız arayın ara arama arayabilirsiniz ulaşın "
             "ulaşınız ulaşabilirsiniz bilgi bilgileri bilgisi bilgilendirme kişi kişisi hat hattı hattımız hafta içi sonu "
             "mesai saat saatleri saatlerinde servis servisi destek müşteri hizmet hizmeti hizmetleri fatura faturası web "
             "mesaj mesajı sms adres adresi mail eposta email faks fax sabit mobil ev iş işyeri satış muhasebe operasyon "
             "randevu rezervasyon business api phone contact call mobile number info only büro "
             "ad adı soyad soyadı isim ismi unvan unvanı ünvan ünvanı diğer ikinci birinci alternatif yedek santral "
             "dahili ofis").split()
_FILLER = {_key(x) for x in _FILLER_W}
# ilke 3: siradan sozcuk testi (zayif kanit yalniz bundan gecerse maskelenir; guclu bulgu gecmezse yalniz o yerde kalir).
# Anahtar bicimi (_key: ı->i, ü->u, ş->s, ç->c, ğ->g, ö->o). Cekim ekleri: simdiki/gecmis/gelecek zaman, emir, gereklilik,
# mastar, yeterlilik, -ArIm/-ArIz, cogul (+iyelik, hal), iyelik, -deki, ulac. Soyadlarinda sik olan '-an/-en' (Doğan,
# Gülen), '-ar/-er' (Uçar), '-maz' (Yılmaz), '-li' (Erdemli) bilerek YOK; listedeki ad/soyad hic sayilmaz.
_ORD_SFX = re.compile(
    r"(?:[iu]?yor(?:um|sun|uz|sunuz|lar|ler|du|dum|duk|dunuz|mus|sa)?|s[iu]n(?:lar|ler)?"
    r"|[dt][iu](?:m|n|k|niz|nuz|lar|ler)?|m[iu]s(?:im|sin|iz|siniz|lar|ler|tir)?"
    r"|[ae]c[ae]k(?:sin|im|iz|siniz|lar|ler|tir)?|[ae]c[ae]g[iu][mz]|m[ae]l[iu](?:yim|sin|yiz|siniz|lar|ler|dir|ydi)?"
    r"|m[ae]k|[ae]bil[iu]r(?:im|sin|iz|siniz|ler|lar)?|[aeiu]r[iu][mz]"
    r"|l[ae]r[iu]?(?:m|n|miz|niz|n[iu]n)?(?:l[ae]|[ae]|d[ae]|d[ae]n)?|[iu]ml[ae]|[iu]n[iu]z(?:l[ae])?|[iu]m[iu]z"
    r"|[aeiou]s[iu]|[dt][ae]ki|[iu]nc[ae]|[ae]r[ae]k)$")
_ORD_W = {_key(x) for x in (
    "ola olsun olur gele kolaylıklar bereketli uğurlu geçmiş sevgiler saygılar selamlar teşekkürler rica ederim "
    "bilginize bilgilerinize duyurulur önemle aşağıda yukarıda burada orada şurada içeride dışarıda dostlar cepten "
    "cebimden numaradan").split()}
_FILLER_PFX = tuple(_key(x) for x in "numara telefon iletişim irtibat whatsapp".split())
# iletisim sozcugu alan olarak: ardinda (dolgu etiketi sozcukleriyle) ':', '-', '.' ('Tel: ...', 'İRT. ...',
# 'Yetkili Kişi: ...'). Ilan imi: bu ya da satirda telefon (_ad_line); 'WhatsApp Web açılmıyor' alan degildir.
# ayrac: ':', '-', '.', ok ('İRTİBAT ⇒ AD'); sozcukle ayrac arasinda parantezli ek olabilir ('Tel (Ofis): Ad Soyad')
_FIELD_SEP = r"(?:=>|->|[:\-\u2013\u2014]|\.(?!\w)|[\u21d2\u2192\u279c\u2794]|\u27a1\ufe0f?)"
_CONTACT_FIELD = re.compile(r"(?<![\w.\-/@])" + _alt(_CONTACT_W) + r"(?!\w)(?:[ \t]+" + _alt(_FILLER_W)
                            + r"(?!\w)){0,2}(?:[ \t]*\([^()\n]{1,24}\))?[ \t]*" + _FIELD_SEP)
# sektor sozcugu ve hukuki bicim: onlerindeki buyuk harfli sozcukler firma adinin ayirt edici kismidir -> [firma].
# Hizmet sozcukleri zincirin parcasidir ('Kaplo Lojistik Hizmetleri Ltd. Şti.': tek maske).
_LEGAL_W = ("ltd limited şti şirketi firması san sanayi tic ticaret inş inşaat paz pazarlama ith ihr ithalat ihracat ve "
            "hizmetleri hizmet hizmetler").split()
_LEGAL_K = {_key(x) for x in _LEGAL_W}
_LEGAL_STRONG = {_key(x) for x in "ltd limited şti şirketi firması".split()}
# hukuki bicim (ikinci ilan imi gerekmez): Ltd, Şti, A.Ş., San.+Tic., Limited+Şirketi. Tek 'Şirketi' siradan sozcuktur
# ('Elektrik Şirketi aradı').
_LEGAL_FORM = {_key(x) for x in "ltd şti".split()}
_SAN, _TIC = {_key(x) for x in "san sanayi".split()}, {_key(x) for x in "tic ticaret".split()}
_LEGAL_GLUED = re.compile(r"(?i:ltd\.|\.[şs]t[iİıI])")                          # 'Ltd.Şti.' tek parca yazimi
_AS = re.compile(r"(?<!\w)[Aa]\.?[ ]?[Şş]\.?(?!\w)")                         # A.Ş.
_FIRM_ITEM = (r"(?:(?:" + _alt(_SECTOR_W) + r")(?:['\u2019]\w+|" + _alt(_SECTOR_SFX_W) + r")?|" + _alt(_LEGAL_W)
              + r"|[Aa]\.?[ ]?[Şş])\.?(?!\w)")
_FIRM_TAIL = re.compile(r"(?<!\w)" + _FIRM_ITEM + r"(?:[ \t.]*" + _FIRM_ITEM + r")*")     # 'Lojistik San. Tic. Ltd. Şti.'
# ilan sozlugu: il adlarinin gayriresmi bicimleri, yuk merkezi semtleri, ulke/bolge, arac/dorse, birim, sik ilan sozcukleri.
# Bunlar kisi ya da firma adi sayilmaz. Il ve ilce adlarinin TEK kaynagi yer listesidir (adlar/tr-yerler.txt, places());
# il adlari yuklenince bu sozluge katilir (_LISTS['ilan']).
_ILAN_PLACE_W = ("afyon antep maraş urfa içel hadımköy ambarlı "
                 "türkiye irak iran suriye gürcistan azerbaycan nahçıvan bulgaristan yunanistan romanya rusya ukrayna "
                 "almanya avrupa asya trakya anadolu marmara doğu batı orta").split()
_ILAN_PLACE = {_key(x) for x in _ILAN_PLACE_W}
_ILAN_W = (
    " ".join(_ILAN_PLACE_W) + " "
    "tır tir kamyon kamyonet kırkayak onteker teker lowbed lowbet tenteli tente damper frigo frigorifik dorse çekici "
    "panelvan pikap kasa açık kapalı sal sallı platform konteyner tanker silobas flatbed mega jumbo minivan vinç "
    "ton kg kilo palet paletli metre km tl lira euro dolar adet desi "
    "acil yük yükü yükler araç aracı araçlar aranıyor aranır lazım gerekli var yok boş dolu müsait fiyat fiyatı ücret "
    "navlun peşin nakit havale komisyon yükleme boşaltma indirme teslim teslimat çıkış çıkışlı varış dönüş gidiş "
    "parsiyel komple günlük haftalık aylık sefer sevkiyat ilan bilgi detay detaylı not uygun ucuz hızlı güvenli "
    "sigortalı sahibinden firma firması şirket merkez şube depo antrepo liman gümrük fabrika ofis sabah akşam gece "
    "bugün yarın hemen şimdi evden eve şehirlerarası şehiriçi uluslararası yurtiçi yurtdışı ithalat ihracat parça eşya "
    "mobilya hurda malzeme gıda çimento kum tuğla kereste hububat buğday arpa mısır saman meyve sebze mimar mühendis "
    "şoför sürücü dikkat duyuru önemli").split()
_ILAN = {_key(x) for x in _ILAN_W}
_KIN = {_key(x) for x in "kardeşler kardeşleri oğulları oğlu ve &".split()}   # ticari adin icindeki akrabalik/baglac
# ilke 4a: ticari ad kuralinin durdurma listesi: nakliye ilanlarinda ve gunluk konusmada sik genel nitelemeler (bunlar
# ayirt edici sozcuk degildir: 'Şehirler Arası Nakliyat', 'Uygun Fiyatlı Taşımacılık', 'Güvenilir Nakliye Hizmeti',
# 'Proje Lojistiği'). Il, ilan, hitap ve dolgu sozlukleri ayrica dislanir. Ad kurallari (main) bunlara yine uygulanir.
# S4: dilbilgisi sozcukleri (belirtec, sayi, baglac, zamir, iyelikli akrabalik) hukuki bicimli zincirde de ad degildir;
# listenin geri kalani (nitelemeler) ve yer adlari hukuki bicim varken ayirt edici sozcuktur ('Ekspres Lojistik A.Ş.')
_FIRM_FUNC = {_key(x) for x in (
    "her türlü bütün tüm bir iki üç dört beş altı yedi sekiz dokuz on yüz bin hangi bazı birçok başka aynı kendi dün "
    "sonra önce ama fakat ancak çünkü yani belki sanırım galiba ayrıca hatta zaten yine gene hep artık henüz biraz çok az "
    "en daha benim senin onun bizim sizin onların annem babam eşim oğlum kızım ailem").split()}
_FIRM_STOP = _FIRM_FUNC | {_key(x) for x in (
    "şehirler arası şehir içi ulusal yerel bölgesel global kaliteli güvenilir profesyonel ekonomik fiyatlı garantili "
    "asansörlü ambalajlı paketli ekspres express özel kurumsal bireysel ticari ağır hafif proje soğuk zincir kombine "
    "karayolu denizyolu havayolu demiryolu büro piyano oto otomobil makine hayvan canlı kötü büyük küçük ürün tedarik "
    "zinciri satın alma tersine iç dış askeri sağlık dijital entegre festival kermes mahalle").split()}
# ilke 4c: yalin hitap firma adi olabilir ('ABLA NAKLİYAT'); cogul/iyelik/hal ekli hitap hitap obegidir ('Değerli Abilerim
# Nakliye', 'Hocam Nakliyat'), firma adi degil
_HON_BASE = {_key(x) for x in "bey beyefendi hanım hanımefendi abi abla hoca başkan kardeş amca teyze usta ağabey abey reis "
             "dayı".split()}
# S5: tekil iyelik ekli hitap ('DAYIM NAKLİYAT', 'Ustam Nakliyat') firma adi olabilir; hitap sifatindan sonra ('Değerli Dayım
# Nakliye') ya da cogul bicimde ('Abilerim') hitap obegidir. Anahtar bicimi.
_HON_SG = re.compile(r"(?:bey|beyefendi|hanim|hanimefendi|abi|abla|hoca|baskan|kardes|amca|teyze|usta|agabey|abey|reis"
                     r"|dayi)(?:im|um|m)")
_ADDR_ADJ = {_key(x) for x in "sayın sn değerli kıymetli sevgili muhterem saygıdeğer aziz canım".split()}
# ticari adin ayirt edici sozcugu (sagdan sola): kesme ekli ve tireli bicim de ('Kaplo-Tavro Nakliyat'); sektor
# sozcugune tireyle bagli ad da ('Tavro-Nakliyat' -> '[firma]-Nakliyat'); URL/e-posta/anma parcasi degil
_FIRM_PREV = re.compile(r"(?<![\w./@:#" + _DASH + r"])([^\W\d_]+(?:['\u2019][^\W\d_]+)?(?:[" + _DASH + r"][^\W\d_]+)*)"
                        r"(?:[ \t]+(?:&[ \t]+)?|[" + _DASH + r"])$")
_FIRM_HYPH = re.compile(r"[^\W\d_][" + _DASH + r"](?=" + _FIRM_ITEM + ")")     # on suzgec: tireli sozcuk sozcuk sayilmaz
_JOIN_GAP = re.compile(r"[ \t]{0,2}[+&][ \t]{0,2}|[ \t]")                    # 'Tavro+Kişi 2', 'Tavro Kişi 2'
_LABEL_AT = re.compile(r"Kişi (\d+)")
_GAP_WS = re.compile(r"\s+")
_HAS_DIGIT = re.compile(r"\d")
_PHONE_CTX = re.compile(r"\[telefon\]|" + _PHONE)      # ham satirda telefon, ciktida maskesi
# hiz: telefon en az 7 hanedir ve iki hanesi arasinda en cok 14 rakam disi karakter olur (tus kapagi 2 + grup ayraci _GS
# 11, ')' dahil + '('); bu on denetimden gecmeyen satirda telefon aranmaz
_PHONE_Q = re.compile(r"\d(?:\D{0,14}\d){6}")
_TEL_MASK = re.compile(r"\[telefon\]")
# iletisim sozcugu/telefon ile ad arasi; 7. tur: telefon ve isaret emojisi, ok, '|', '*' da ilan ayracidir ('Ad Soyad
# <telefon emojisi> 0500...'); emoji secicisi U+FE0F ayrac sayisina girmez
_CTX_PUNCT = "\u260e\U0001f4de\U0001f4f1\U0001f4f2\U0001f448\U0001f449\u261b\u261e\u2192\u21d2\u27a1\u279c\u2794>=|*"
_CTX_GAP_AFTER = re.compile(r"(?:[\s:.\-\u2013\u2014,/()" + _CTX_PUNCT + r"]\ufe0f?){0,4}")
_CTX_GAP_BEFORE = re.compile(r"(?:[\s:.\-\u2013\u2014,/(" + _CTX_PUNCT + r"]\ufe0f?){0,4}")
_FIRM_GAP = re.compile(r"[ \t]+(?:&[ \t]+)?")
_LABEL_END = re.compile(r"Kişi (?:\d+|\?)(?:(?:[ \t]+(?:ve|&))?[ \t]+|[" + _DASH + r"])$")   # firma adindaki etiket
_LABEL_BEFORE = re.compile(r"(Kişi \d+)(?:[ \t]{0,2}[+&][ \t]{0,2}|[ \t])$")   # 'Kişi N <ad>'
_COLON = re.compile(r"[ \t]*:")
_HWS = re.compile(r"[ \t]*")
_SIG_TAIL = re.compile(r"[\s\-\u2013\u2014:.,/|()]*(?:\[telefon\][\s\-\u2013\u2014:.,/|()]*)*")   # imza sonu
_ALNUM = re.compile(r"[^\W_]")
# soyad konumu (ilan baglaminda bilinmeyen soyad): satir sonu, ayrac, telefon (ham ya da maskeli)
_SURNAME_POS = re.compile(r"[ \t]*(?:$|[:\-\u2013\u2014,/|(]|\.(?!\w)|\[telefon\])")
# guzergah baglami (F3, ilke 2): ok/tire ile oteki ucu yer adi, ardinda yukleme sozcugu, '<yer>'dan ... 'a' / '...'dan <yer>'e
_ARROW = r"(?:\u27a1\ufe0f?|\u2192|\u21d2|\u279c|\u2794|->|=>|>|-|\u2013|\u2014)"
_ROUTE_PRE = re.compile(r"([^\W\d_]+)(?:['\u2019][^\W\d_]+)?[ \t]*" + _ARROW + r"[ \t]*$")
_ROUTE_POST = re.compile(r"[ \t]*" + _ARROW + r"[ \t]*([^\W\d_]+)")
# S8: yalniz kisinin ozne olamayacagi bicimler ('X yüklemeli', 'X çıkışlı'); 'X indirme/yükleme yaptı' kisi olabilir
_ROUTE_LOAD = re.compile(r"[ \t]+" + _alt("yüklemeli yüklemesi yüklenecek çıkışlı boşaltmalı indirmeli varışlı".split())
                         + r"(?!\w)")
_ROUTE_FROM = re.compile(r"([^\W\d_]+)['\u2019](?:dan|den|tan|ten|DAN|DEN|TAN|TEN)(?!\w)")
_ROUTE_TO = re.compile(r"([^\W\d_]+)['\u2019](?:y?[aeAE]|Y[AE])(?!\w)")
_ROUTE_GAP = " \t:.,;/()-\u2013\u2014"
_ROUTE_CONTACT = re.compile(r"(?<!\w)" + _alt(_CONTACT_W) + r"(?!\w)")
_ROUTE_CONTACT_END = re.compile(r"(?<!\w)" + _alt(_CONTACT_W) + r"$")


def _ad_line(line):
    """Satir ilan imi tasiyor mu: telefon (ham ya da maskeli) ya da alan olarak iletisim sozcugu."""
    return ("[telefon]" in line or (bool(_PHONE_Q.search(line)) and bool(_PHONE_CTX.search(line)))
            or bool(_CONTACT_FIELD.search(line)))


def _text_lines(parts):
    """Mesaj parcalarindan metin satirlari (ilan imi icin)."""
    return [ln for kind, v in parts if kind == "text" and v for ln in v.split("\n")]


def _src_lines(src):
    """Ilan imi kaynagi -> satirlar: metin (alinti, dosya adi), mesaj parcalari listesi ya da mesaj."""
    if isinstance(src, str):
        return src.split("\n")
    return _text_lines(src if isinstance(src, list) else message_parts(src))


def _route_place(w):
    """Guzergahin oteki ucu yer adi mi: yer listesindeki il/ilce ya da ilan sozlugundeki yer (ulke, bolge, Antep...)."""
    k = _key(w)
    return k in places() or k in _ILAN_PLACE


def _route_adjacent(s, st, end):
    """s[st:end] sozcugunun hemen yaninda (arada yalniz bosluk/noktalama) telefon ya da iletisim sozcugu var mi."""
    ws = end
    while ws < len(s) and ws < end + 6 and s[ws] in _ROUTE_GAP:
        ws += 1
    if _PHONE_CTX.match(s, ws) or _ROUTE_CONTACT.match(s, ws):
        return True
    pre = s[max(0, st - 40):st].rstrip(_ROUTE_GAP)
    if pre.endswith("[telefon]") or _ROUTE_CONTACT_END.search(pre):
        return True
    return pre[-1:].isdigit() and any(mo.end() == len(pre) for mo in _PHONE_CTX.finditer(pre))


def _route(s, st, en, end):
    """Ilke 2: s[st:en] (ek dahil sonu end) KANITLI guzergah baglaminda mi. Yaninda telefon ya da iletisim sozcugu yok ve:
    ardinda yukleme sozcugu ('X yüklemeli', 'X çıkışlı'), ya da ok/tire ile oteki ucu yer adi ('Şanlıurfa ➡️ X',
    'X - Konya'), ya da "X'dan Mersin'e" / "Konya'dan X'e" (oteki uc yer adi). 'teslim', 'çıkış' yukleme sozcugu degil."""
    if _route_adjacent(s, st, end):
        return False
    if _ROUTE_LOAD.match(s, end):
        return True
    mo = _ROUTE_POST.match(s, end)
    if mo and _route_place(mo.group(1)):
        return True
    mo = _ROUTE_PRE.search(s, max(0, st - 40), st)
    if mo and _route_place(mo.group(1)):
        return True
    sfx = _key(s[en:end]).lstrip("'\u2019")
    if sfx in ("dan", "den", "tan", "ten"):
        mo = _ROUTE_TO.search(s, end, end + 60)
        return bool(mo and _route_place(mo.group(1)))
    if sfx in ("a", "e", "ya", "ye"):
        mo = None
        for mo in _ROUTE_FROM.finditer(s, max(0, st - 60), st):
            pass
        return bool(mo and _route_place(mo.group(1)))
    return False


_ACT_RANK = {"firma": 4, "join": 3, "rx": 2, "ctx": 1}


def _merge(line, spec, out):
    """Ilke 2: ozel kurallar (Anonymizer._special) yalniz maske EKLER; ad kurallarinin (main) kararini bastiramaz.
    Bir maskeyle cakisan 'review' karari duser. Bir maskenin icinde kalan ya da baska turde maskeyle birlesen 'rx' karari
    gosterilmez ama ad yine ogrenilir ('learn': sohbetin her yerinde maskelenir). Kismen cakisan iki maske tek kararda
    birlesir (kapsayan aralik; tur sirasi firma > join > rx > ctx). -> baslangica gore sirali, cakismayan kararlar
    (+ 'learn', 'mark'; bunlar metne uygulanmaz)."""
    marks = [d for d in spec if d[4] == "mark"]
    masks = sorted((d for d in (*spec, *out) if d[4] not in ("mark", "review")), key=lambda d: (d[0], -d[1]))
    res, learn = [], []
    for d in masks:
        if not res or d[0] >= res[-1][1]:
            res.append(d)
            continue
        p = res[-1]
        if d[1] <= p[1]:                                   # tamamen icinde
            if p[:2] == d[:2] and p[4] == d[4] == "rx" and p[5] == "imza":    # S7: ad kurali (main) imzadan gucludur
                res[-1] = d
                continue
            # ayni aralikta ayri kanitli iki 'rx' (iletisim + ad kurali): ad kuralinin karari da ogrenilir (main'in kaniti
            # iletisim kanitinin dar bicimini guclendirir; _learn). Ticari adin icindeki sozluk adi da (main gibi): ekli
            # (apostrofsuz) ve kucuk harfli gecisleri baska satirda yalniz ogrenilmisse maskelenir
            if d[4] == "rx" and not (p[4] == "rx" and p[:2] == d[:2] and p[5] == d[5]):
                learn.append((d[0], d[1], d[2], d[3], "learn", d[5]))
            continue
        top = max((p, d), key=lambda x: _ACT_RANK[x[4]])
        for x in (p, d):        # birlesen kararin ad kurali karari da ogrenilir (ticari ad icinde de; main gibi)
            if x[4] == "rx" and top[4] != "rx":
                learn.append((x[0], x[1], x[2], x[3], "learn", x[5]))
        disp = " ".join(line[p[0]:d[1]].split())
        res[-1] = (p[0], d[1], top[2] if top[4] == "join" else "" if top[4] == "firma" else _key(disp), disp, top[4],
                   top[5])
    rev = [d for d in out if d[4] == "review" and not _overlaps(res, d)]
    return sorted(res + rev + learn + marks, key=lambda d: d[0])


def _overlaps(sorted_spans, d):
    """d (bas, son, ...) bas'a gore sirali, kendi aralarinda cakismayan araliklardan biriyle cakisiyor mu."""
    i = bisect.bisect_left(sorted_spans, (d[1],))
    return i > 0 and sorted_spans[i - 1][1] > d[0]


def _inst(wk):
    """Anahtar bicimli sozcuk kurum sozcugu mu (Üniversitesi..., Sokağı)."""
    return wk.startswith(_INST_ANY_K) or wk in _INST_CAP_K


def _inst_word(w):
    return _inst(_key(w.split("'", 1)[0].split("’", 1)[0]))


def _landmark(text, st, en, end=None):
    """Katilimci OLMAYAN sozluk adi text[st:en] bir yer/kurum adinin parcasi mi. Cagiran katilimci adina hic sormaz.
    True (dokunma): 'Hz.' sonrasi, ya da ad ile kurum sozcugu buyuk harfle, aralarinda yalniz tek bosluk, tek ozel ad
    obegi: ad kurum sozcugunun hemen onunde (Mimar Sinan Üniversitesi, Atatürk Caddesi) ya da aradaki sozcuklerle
    birlikte zincir (Fatih Sultan Mehmet Köprüsü: zincirin onceki halkalari sozcuk anlami da olan ad ya da ad degil).
    None (karar yok -> maskelenir, 'yer/kurum belirsiz' sayilir): kurum sozcugune ulasildi ama bu dar bicim yok
    (Zeynep Gazi Üniversitesi'ni kazandı, Selin müzesinde, ekli ad + kurum). False: kurum sozcugu yok (maskelenir)."""
    if _LM_HZ.search(text[max(0, st - 12):st]):
        return True
    end = en if end is None else end            # end: ekli bicimin sonu ('Sinan'ın'): ek varsa ozel ad obegi degil
    cap = end == en and text[st:st + 1].isupper()
    pos, mid = end, []
    for _ in range(4):
        mo = _LM_NEXT.match(text, pos)
        if not mo:
            return False
        w = mo.group(1)
        if _inst_word(w):
            if not (cap and w[:1].isupper()):
                return None
            if not mid:
                return True
            g, _, a = name_lists()
            chain = [_key(t) for t in text[st:en].split()] + mid[:-1]
            return True if all(t in a or t not in g for t in chain) else None
        if not (cap and w[:1].isupper()):
            return False                        # cogu gecis: ilk sozcuk kucuk harf, hizli cikis
        mid.append(_key(w))
        pos = mo.end()
    return False


def name_lists():
    """(adlar, soyadlar, sozcuk-olan-adlar) anahtar kumeleri; ayni yukleyici yer listesini de okur (places()). Dosya yoksa
    bos kume; missing_name_lists() eksikleri verir (anonim modda main bunu hata sayar, bkz. --sozluksuz)."""
    if not _LISTS:
        missing = []
        for k, fn in (("g", "tr-adlar.txt"), ("f", "tr-soyadlar.txt"), ("a", "sozcuk-adlar.txt"), ("p", "tr-yerler.txt")):
            s = {} if k == "p" else set()
            try:
                with open(os.path.join(_HERE, "adlar", fn), encoding="utf-8") as fh:
                    for line in fh:
                        if line.startswith("#"):
                            continue
                        if k == "p":                  # '<il|ilçe><TAB><ad>'
                            kind, _, name = line.rstrip("\n").partition("\t")
                            if name.strip():
                                s[_key(name.strip())] = kind
                        else:
                            s.update(_key(w) for w in line.split())
            except OSError:
                missing.append(fn)
            _LISTS[k] = s
        _LISTS["missing"] = missing
        _ordinary.cache_clear()               # sozluk yeniden yuklendi (testler _LISTS'i temizler): onbellek eskidi
        p, g, f = _LISTS["p"], _LISTS["g"], _LISTS["f"]
        _LISTS["ilan"] = _ILAN | {k for k, v in p.items() if v == "il"}       # il adlari ilan sozlugudur
        # yalniz yer: il adi ya da ad/soyad sozlugunde olmayan ilce adi (Bozova, Gebze); Fatih, Kartal, Bozkurt belirsizdir
        _LISTS["pure"] = {k for k, v in p.items() if " " not in k and (v == "il" or (k not in g and k not in f))}
    return _LISTS["g"], _LISTS["f"], _LISTS["a"]


def places():
    """Il ve ilce adlari (adlar/tr-yerler.txt; Wikidata CC0): anahtar -> 'il' | 'ilçe'. Dosya yoksa bos."""
    name_lists()
    return _LISTS["p"]


def ilan_words():
    """Ilan sozlugu (_ILAN_W) + il adlari (yer listesinden): kisi ya da firma adi sayilmayan sozcukler (anahtar bicimi)."""
    name_lists()
    return _LISTS["ilan"]


def _pure_place(k):
    """Anahtar bicimli sozcuk yalniz yer adi mi (bkz. name_lists 'pure'): guzergah istisnasi, ticari ad ve iletisim
    kurallari bunu sorar. Ad ya da soyad da olan ilce adi yer sayilmaz (supheli durumda maskelenir)."""
    name_lists()
    return k in _LISTS["pure"]


@functools.lru_cache(maxsize=1 << 15)
def _ordinary(k):
    """Ilke 3: anahtar bicimli sozcuk siradan sozcuk mu (ad sayilmaz): sozcuk listeleri (_ORD_W; hitap, dolgu, iletisim,
    hukuki bicim, takvim, kurum, sektor, ilan sozcukleri), yalniz yer adi, cekim eki (_ORD_SFX, kok en az 2 harf). Ad ya da
    soyad listesindeki sozcuk siradan sayilmaz (Durmuş, Tosun)."""
    if (k in _ORD_W or k in _HON_STOP or k in _FILLER or k.startswith(_FILLER_PFX) or k in _CONTACT or k in _LEGAL_K
            or k in _TAKVIM or k in _CAPWORD or k in _SAYIN_STOP or _HON.fullmatch(k) or _inst(k) or _is_sector(k)
            or k in ilan_words() or _pure_place(k)):
        return True
    g, f, _ = name_lists()
    if k in g or k in f:
        return False
    m = _ORD_SFX.search(k)
    return bool(m and m.start() >= 2)


def missing_name_lists():
    name_lists()
    return list(_LISTS["missing"])


def _tokens(line):
    """Sozcukler (URL/e-posta/dosya adi/kullanici adi icindekiler haric) -> [(bas, son, sozcuk, cumle_basi, anma)].
    anma: '@' ile baslayan (e-posta degil) sozcuk."""
    out, prev_end, n = [], None, len(line)
    for m in _WORD.finditer(line):
        st, en = m.span()
        b = line[st - 1] if st else ""
        a, a2 = (line[en] if en < n else ""), (line[en + 1] if en + 1 < n else "")
        men = b == "@" and (st < 2 or not (line[st - 2].isalnum() or line[st - 2] in "._-+"))
        if ((not men and (b.isalnum() or (b and b in "/@#_.-\\"))) or a.isalnum() or (a and a in "/@_\\")
                or (a and a in ".-" and a2.isalnum()) or (m.group(0) == "Kişi" and _LABEL_AFTER.match(line, en))):
            prev_end = en
            continue
        gap = line[prev_end:st] if prev_end is not None else ""
        initial = prev_end is None or bool(_GAP_INI.search(gap))
        out.append((st, en, m.group(0), initial, men))
        prev_end = en
    return out


class _LabelMap(dict):
    """Anonymizer'in etiket sozlukleri (labels, found, found_cap, ctx_labels): degerleri ortak sayacta sayilir; yeni etiket
    numarasi (_new_label) dort sozlugu her cagrida taramadan, ayni sonucla bulunur (hiz: ogrenilen ad sayisinda karesel)."""

    def __init__(self, counts):
        super().__init__()
        self._counts = counts

    def __setitem__(self, k, v):
        if k in self:
            old = self[k]
            self._counts[old] -= 1
            if not self._counts[old]:
                del self._counts[old]
        super().__setitem__(k, v)
        self._counts[v] = self._counts.get(v, 0) + 1

    def __delitem__(self, k):
        old = self[k]
        super().__delitem__(k)
        self._counts[old] -= 1
        if not self._counts[old]:
            del self._counts[old]


class Anonymizer:
    """Tek anonimlestirme noktasi (telefon ve web yolu write_chat uzerinden kullanir). Diske gercek ad yazmaz.
    Kisiler ilk gorunme sirasiyla 'Kişi N': once gonderenler, sonra sistem satirlarindaki kisiler (eklendi, katildi,
    ayrildi; numara olarak gorunenler dahil), sonra operatorun ek adlari (extra), sonra metinde ad sozlugu / hitapla
    bulunanlar. Sohbet 'Sohbet-<sira>' (kosudaki konumu; code ile degistirilebilir). Sohbet adi baslikta, sistem
    satirlarinda ve dosya adlarinda hep maskelenir (title=True); mesaj metninde yalniz bire bir sohbette (baslik
    karsidaki kisinin adidir, kisi gibi maskelenir) ya da baslikta kisi adi varsa (sozluk adi, katilimci ad parcasi,
    'Ailesi'); kurum/genel ifade olan grup adinin sozcukleri metinde dokunulmaz. Telefon, e-posta vb. maskelenir.
    group: grup sohbeti mi (None: msgs'ten is_group; process tarih suzgecinden ONCEKI tum mesajlarla verir)."""

    def __init__(self, chat, msgs, chat_no=1, code=None, extra=None, group=None):
        self.chat = nfc(chat)
        self.code = code or f"Sohbet-{chat_no}"
        self._label_counts = {}               # etiket -> dort etiket sozlugundeki gecis sayisi (_LabelMap, _new_label)
        self.labels = _LabelMap(self._label_counts)   # gercek ad -> 'Kişi N'
        self.origin = {}                      # etiket -> kaynak (sayim ozeti icin; gercek ad tutmaz)
        self.by_key = {}                      # anahtar -> maske

        def person(real, origin, same=None):
            if not real or real in self.labels:
                return
            if same is not None and same in self.labels:      # 'X changed to +90...' -> ayni kisi
                lab = self.labels[same]
            elif _key(real) in self.by_key:
                lab = self.by_key[_key(real)]
            else:
                lab = f"Kişi {len(set(self.labels.values())) + 1}"
                self.origin[lab] = origin
            self.labels[real] = lab
            self.by_key.setdefault(_key(real), lab)
            clean = " ".join(re.sub(r"[^\w\s'’.+()\-]", " ", real).split())     # 'Ali 🚒' -> 'Ali' (ayni etiket)
            if clean and clean != real and any(c.isalpha() for c in clean) and clean not in self.labels:
                self.labels[clean] = lab
                self.by_key.setdefault(_key(clean), lab)

        mparts = [message_parts(m) if ("parts" in m or "lines" in m) else [] for m in msgs]   # bir kez ayristir
        self.group = is_group(msgs, self.chat) if group is None else bool(group)
        titles = title_senders(msgs, self.chat) if self.group else set()
        for m in msgs:
            person(m.get("sender"), "gönderen")
        for m, ps in zip(msgs, mparts):
            if ps and (m.get("sender") is None or m["sender"] in titles):
                body = " ".join(v for k, v in ps if k == "text" and v)
                # grupta grup adiyla gelen ve sistem satirina cevrilmemis olay satiri (mark_system_lines atlanmissa):
                # kisileri yine toplanir (ayni kural: title_event_line)
                if m.get("sender") is None or title_event_line(body):
                    for real, same in system_people(body):
                        person(real, "sistem satırı", same)
        for real in extra or []:
            person(nfc(real).strip(), "ek ad")
        if not self.group:
            person(self.chat, "sohbet adı")         # bire bir: baslik karsidaki kisi (hic yazmamis olsa da)
        self._people = set(self.labels.values())   # katilimci etiketleri (sozlukle bulunanlardan ayirmak icin)
        self._single = {_key(r) for r in self.labels if len(nfc(r).split()) == 1}   # tek sozcuklu katilimci adlari (C)
        self.media = {}
        self.stats = {}                       # kategori -> maskelenen gecis sayisi (yalniz sayilar)
        self.review = {}                      # anahtar -> [sozcuk, sayi, neden, ornekler]: maskelenmeden kalan supheli adlar
        self._counting = False
        self._cur, self._pend = None, 0
        self._secrets = set()                 # maskelenen parola degerleri (yalniz bellekte; alintida/tekrarda da maskelenir)
        self._cand = {}                       # anahtar kelimeli mesajin +-3 komsusu: kisa mesaj -> en az hane (parola/PIN)
        self._own = {}                        # aday mesajin kendi ek adlari (ek basligi bunlardan biriyse maskelenmez)
        mtext = []
        for ps in mparts:
            mtext.append(" ".join(v for k, v in ps if k in ("text", "quote") and v))
        self._cand_code = set()               # whatsapp/web/baglama baglami: tek basina 6-8 haneli mesaj -> [kod]
        for i in range(len(msgs)):
            if _CODE_CTX.search(_key(mtext[i])):
                for j in range(max(0, i - 3), min(i + 4, len(msgs))):
                    if j != i and re.fullmatch(r"\d{6,8}", mtext[j].strip()):
                        self._cand_code.add(id(msgs[j]))
        for i, m in enumerate(msgs):
            if not _KW_ANY.search(mtext[i]) and not _OTP_KW.search(mtext[i]):
                continue
            nd = 4 if re.search(r"(?<!\w)(?:pin|kod|otp|do[gğ]rulama)", _key(mtext[i])) else 6
            for j in range(max(0, i - 3), min(i + 4, len(msgs))):
                toks = mtext[j].split()
                own = {nfc(v.strip()) for k, v in mparts[j] if k == "file" and v}
                own |= {os.path.basename(v.replace("\\", "/")) for v in own}
                if j != i and 1 <= len(toks) <= 2 and any(_cred_like(t, nd) and nfc(t) not in own for t in toks):
                    self._cand[id(msgs[j])] = min(nd, self._cand.get(id(msgs[j]), 9))
                    if own:
                        self._own[id(msgs[j])] = own
        firsts, lasts = {}, {}                # tek parca anahtari -> [ad-soyad]; ad >=2, soyad >=4 karakter
        toktext = {}
        for real in self.labels:
            toks = nfc(real).split()
            if len(toks) > 1:
                for d, t, mn in [(firsts, toks[0], 2), *((lasts, t, 4) for t in toks[1:])]:   # ilk olmayan her parca soyad adayi
                    # ilke 2: main gibi her parca maskelenir (ilan/sektor sozcugu olan parca da: '10 teker' -> '10 Kişi N');
                    # tek istisna kanitli guzergahtaki yer adi parcasi (_route_keys, _route_hit)
                    if len(t) >= mn and t[0].isalpha():
                        if real not in d.setdefault(_key(t), []):
                            d[_key(t)].append(real)
                        toktext.setdefault(_key(t), t)
        full_keys = {_key(r) for r in self.labels} | {_key(self.chat)}
        owners = {}                           # tek parca anahtari -> sahip katilimcilar (ad ve soyad birlikte)
        for d in (firsts, lasts):
            for k, reals in d.items():
                owners.setdefault(k, set()).update(reals)
        first_names = []
        for k, own in owners.items():
            if k in full_keys:                # tam ad olarak zaten cozuluyor (tek sozcuklu katilimci kazanir)
                continue
            if len({self.labels[r] for r in own}) == 1:
                self.by_key[k] = self.labels[next(iter(own))]
            else:                             # belirsiz ve tek sozcuklu sahibi yok: ad sizmasin diye notr etiket
                self.by_key[k] = "Kişi ?"
            first_names.append(toktext[k])
        # F3 (ilke 2): yer listesinde olan, ad/soyad sozlugunde olmayan (il adi her zaman) tek parca ('Veli Karasoy Bozova 2'
        # icin 'Bozova') yalniz KANITLI guzergahta (oteki uc yer adi ya da yukleme sozcugu, yaninda telefon/iletisim sozcugu
        # yok) maskelenmez (Anonymizer._route_hit); baska her yerde main gibi maskelenir. Tam ad hicbir zaman.
        gl, fl, _ = name_lists()               # ad/soyad listesindeki il adi da ('Mehmet Aydın') istisna almaz (ilke 1)
        self._route_keys = {k for k in owners if k not in full_keys and _pure_place(k) and k not in gl and k not in fl
                            and not _SURNAME_SFX.search(k)}
        single = [nfc(r) for r in self.labels if len(nfc(r).split()) == 1]
        win_names, combo = [], {}
        for real, lab in self.labels.items():
            toks = nfc(real).split()
            if len(toks) > 2:                 # >=2 parcali bicimler (ardisik, ilk+son, orta+son...) bosluklu da
                for w in _part_combos(toks):
                    combo.setdefault(_key(" ".join(w)), [" ".join(w), set()])[1].add(lab)
        for k, (disp, labs) in combo.items():
            if k in full_keys:                # baska katilimcinin tam adi: o kazanir
                continue
            self.by_key[k] = next(iter(labs)) if len(labs) == 1 else "Kişi ?"   # iki katilimcida ortak: notr
            win_names.append(disp)
        self._mstart = {_key(n.split()[0]) for n in [*self.labels, *win_names] if len(n.split()) > 1}   # hiz: on suzgec
        # metinde gecen, katilimci olmayan adlar (ad sozlugu, hitap): yalniz bu sohbette gecenler regex'e girer
        self._compiled, self._lazy, self._quiet = False, set(), set()
        self._pkeys = {k for k, lab in self.by_key.items() if self._participant(lab)}   # katilimci ad parcalari (C)
        self.found = _LabelMap(self._label_counts)       # gosterim -> etiket (tam sozcuk + ek bicimleri; parca/bitisik yok)
        self.found_cap = _LabelMap(self._label_counts)   # S3/S7: yalniz buyuk harfli bicimiyle yayilan adlar (gosterim -> etiket)
        self._capk = set()                    # bunlarin anahtarlari
        self._capparts = {}                   # bunlarin tek parcasi -> tam adin etiketi (yalniz hitap/Sayın yaninda; _learn)
        # 7. tur eki: yalniz iletisim/imza kanitiyla by_key'e giren anahtarlar. Ad kurallari (main) bunlari bilinmeyen
        # sayar (_known): main'in kaniti (Sayın, hitap, @anma, sozluk) geldiginde ad ayni etiketle her bicimiyle yayilir
        # (_strengthen); kanit bilineni yalniz guclendirir, mesaj sirasi sonucu degistirmez
        self._contact_keys = set()
        self.ctx_labels = _LabelMap(self._label_counts)  # sozcuk anlami da olan ad -> etiket (yalniz baglamli geciste)
        # ilan imi: mesajda telefon ya da alan olarak iletisim sozcugu var mi (ilan cok satirli bir mesajdir). Ticari ad,
        # etiket katilimi ve soyad kurallari bunu sorar (_ad_ctx; yalniz soruldugunda hesaplanir, mesaj kimligiyle saklanir;
        # render ayni degeri id(m) ile alir). Imza satiri: ayni mesajda ilan imli satira komsu, yalniz ad bicimli satir
        # (_sig_ctx; yalniz ilk taramada). Ilan imini soran satir karar vermese de _quiet'e girmez (render'da yeniden taranir).
        self._adctx, self._sigs, self._actx, self._ad_used, self._sigok = {}, {}, (None, ""), False, False
        self._pre = {}                        # (mesaj/metin kimligi, ham satir) -> ilk taramanin yerel kararlari
        self._pre_keys = set()                # yerel karari olan mesaj/metin kimlikleri (hiz)
        self._quiet_m = set()                 # (mesaj/metin kimligi, ham satir): bu mesajda ciktida yeniden taranmaz
        self._partof = {}                     # guclu kanitli adin parca anahtari -> tam ad anahtari (ayri kisiler karismaz)
        for m, ps in zip(msgs, mparts):
            if m.get("sender") is None:       # sistem satiri: kisileri system_people toplar; konu metni ad degildir
                continue
            mctx = (id(m), ps)
            for kind, v in ps:
                if not v or kind == "omitted":
                    continue
                if kind == "file":
                    v = re.sub(r"[_\-.]+", " ", os.path.splitext(v)[0])
                self._actx = (("s", v), v) if kind == "quote" else mctx
                self._sigok = kind == "text"
                for line in v.split("\n"):
                    self._ad_used = False
                    dec = self._scan(line)
                    if not dec and kind != "file":    # karar yok: ciktida (maskeleme yalniz ad cikarir) yeniden taranmaz;
                        if self._ad_used:             # ilan imini soran satir yalniz bu mesajda (baska mesajda imi farkli)
                            self._quiet_m.add((self._actx[0], line))
                        else:
                            self._quiet.add(line)
                    for st, en, k, disp, act, why in dec:
                        if act in ("rx", "learn"):
                            self._learn(disp, why)
                        elif act == "ctx":
                            self._ctx_label(k, why, disp)
                    loc = [d for d in dec if d[4] in ("ctx", "firma")]
                    # hiz: kararlarin hepsi nakliye iletisim/firma karari ise satir ciktida rx ve _pre_apply ile tamamen islenir;
                    # yeniden tarama yeni bir sey bulamaz (adlarin ilk taramadaki karari ayni ham satirdan cikar)
                    done = bool(dec) and all(d[4] == "learn" or (d[4] in ("rx", "ctx", "firma")
                                                                    and d[5] in ("iletişim", "imza", "firma")) for d in dec)
                    if loc and kind != "file":    # yerel kararlar ciktida rx'ten ONCE uygulanir (_pre_apply)
                        self._pre.setdefault((self._actx[0], line), (loc, done))
                        self._pre_keys.add(self._actx[0])
                    elif done and kind != "file":
                        self._quiet_m.add((self._actx[0], line))
        self._actx, self._sigok = (None, ""), False
        self.by_key.setdefault(_key(self.chat), self.code)   # 1:1 ise yukaridaki katilimci etiketi kazanir
        g, f, a = name_lists()
        toks = self.chat.split()
        ttoks = [re.sub(r"[^\w]", "", t) for t in toks]
        personal = any(_key(t) in _FAMILY or (len(t) >= 3 and _key(t) in owners) or
                       (len(t) >= 3 and _key(t) in g and _key(t) not in a and _key(t) not in _TAKVIM | _CAPWORD)
                       for t in ttoks if t)
        self.title_in_text = (not self.group) or personal

        def namelike(i):
            """Grup basliginin i. sozcugu ad gibi mi: katilimci ad parcasi, sozcuk anlami olmayan sozluk adi/soyadi ya
            da aile sozcugunun onundeki buyuk harfli sozcuk (Plimm Ailesi). 'Doğum', 'Günü', 'Okul' degil."""
            t = ttoks[i]
            k = _key(t)
            if len(t) < 3 or k in _FAMILY or k in _HON_STOP or k in _TITLE_STOP or k in _TAKVIM | _CAPWORD:
                return False
            if k in owners or ((k in g or k in f) and k not in a):
                return True
            return t[0].isupper() and i + 1 < len(ttoks) and _key(ttoks[i + 1]) in _FAMILY
        named = set(range(len(toks))) if not self.group else {i for i in range(len(toks)) if namelike(i)}
        chat_wins, chat_wins_named = [], []   # ardisik parcalar; grupta metinde yalniz ad gibi sozcuk icerenler
        if len(toks) > 2:
            for i in range(len(toks)):
                for j in range(i + 2, len(toks) + 1):
                    w = toks[i:j]
                    if all(len(t) >= 2 for t in w) and sum(map(len, w)) >= _CAT_MIN:
                        for fw in (w, w[::-1]):
                            win = " ".join(fw)
                            if win not in chat_wins:
                                self.by_key.setdefault(_key(win), self.code)
                                chat_wins.append(win)
                                if named & set(range(i, j)):
                                    chat_wins_named.append(win)
        title_single = []                     # kisi adli grup basligi: yalniz ad gibi sozcuk tek basina da (Plimm Ailesi)
        if self.group and personal and len([t for t in ttoks if t]) > 1:
            for i in sorted(named):
                k = _key(ttoks[i])
                if ttoks[i][:1].isupper() and k not in self.by_key:
                    self.by_key[k] = self.code
                    title_single.append(ttoks[i])
        found_single = [n for n in self.found if len(n.split()) == 1]
        sfx_names = sorted({n for n in [*first_names, *single, *found_single, *title_single]
                            if len(n) >= 4 and n[0].isalpha() and _key(n) in self.by_key}, key=len, reverse=True)
        self.cat_keys = {}                    # bitisik biciminin anahtari -> maske
        forms, chat_forms, chat_forms_named = [], [], []
        for real, lab in self.labels.items():
            for fm in _concat_forms(real):
                self.cat_keys.setdefault(_key("".join(fm)), lab)
                forms.append(fm)
        nkeys = {_key(ttoks[i]) for i in named}
        for fm in _concat_forms(self.chat):
            self.cat_keys.setdefault(_key("".join(fm)), self.code)
            chat_forms.append(fm)
            if nkeys & {_key(x) for x in fm}:
                chat_forms_named.append(fm)
        body = [*self.labels, *first_names, *win_names, *self.found]
        caps = list(self.found_cap)
        self.rx_t = self._compile([*body, self.chat, *chat_wins, *title_single], forms + chat_forms, sfx_names, caps)   # sistem satiri, dosya adi
        if not self.title_in_text:                                                                   # mesaj metni
            self.rx = self._compile(body, forms, sfx_names, caps)
        elif self.group:              # kisi adli grup basligi: tam baslik ve ad gibi sozcuk iceren parcalari
            self.rx = self._compile([*body, self.chat, *chat_wins_named, *title_single], forms + chat_forms_named, sfx_names,
                                    caps)
        else:
            self.rx = self.rx_t
        self._caprx = self._compile((), (), (), caps) if caps else None   # 7. tur eki: yalniz buyuk harfli adlar (_rx_sub)
        self._compiled = True
        # L9: ana makinesinde maske olan URL: maskenin ardindaki etiketler + uzanti + yol (maske harfiyle baslar: hizli)
        self._url_rx = re.compile(r"(?:Kişi[ \-](?:\d+|\?)|\[firma\]|" + re.escape(self.code) + r")[\w\-]*(?:\.[\w\-]+)*?"
                                  r"\.(?i:" + _URL_TLD + r")(?P<ur>[/?#][^\s]*)")

    @staticmethod
    def _compile(names, forms, sfx_names, caps=()):
        names = sorted((n for n in {nfc(x) for x in names} if n.strip()), key=len, reverse=True)
        alts = [f"(?P<wame>{_WAME})", f"(?P<social>{_SOCIAL})", f"(?P<iban>{_IBAN})", f"(?P<email>{_EMAIL})"]
        cats = sorted({"".join(_name_regex(p) + ("" if i == len(f) - 1 else r"[._\-]?") for i, p in enumerate(f))
                       for f in forms}, key=len, reverse=True)
        if cats:   # bitisik/ayrik ad: sozcuk siniri yok (kullanici adi, URL, dosya adi); tek parcalar icin yok
            alts.append(r"(?P<cat>" + "|".join(cats) + ")")
        caps = sorted({nfc(c) for c in caps if c.strip()}, key=len, reverse=True)
        if names or caps:   # ad agaci once; yalniz buyuk harfli bicimiyle yayilan adlar (S3/S7) sonra. Ayni konumda daha uzun
            # buyuk harfli adi _rx_sub secer (_caprx): hangi turden olursa olsun ayni konumdaki en uzun ad maskelenir
            nm = "|".join(x for x in (_first_alt(names), "|".join(_name_regex(c, cap=True) for c in caps)) if x)
            alts.append(r"(?P<name>(?<!\w)@?(?P<nm>" + nm + r")(?P<suf>['\u2019]\w+)?(?!\w))")
        if sfx_names:   # ad + kapali ek listesi (apostrofsuz): 'Kişi 1'cüm'
            alts.append(r"(?P<nsfx>(?<!\w)@?(?P<nn>" + _first_alt(sfx_names) + ")(?P<sx>" + _SFX_RX + r")(?!\w))")
        alts += [f"(?P<phone>{_PHONE})", f"(?P<tckn>{_TCKN})", f"(?P<plaka>{_PLAKA})"]
        return re.compile("|".join(alts))

    def _new_label(self, origin):
        lab = f"Kişi {len(self._label_counts) + 1}"   # dort etiket sozlugundeki farkli etiket sayisi + 1 (_LabelMap)
        self.origin[lab] = origin
        return lab

    def _learn(self, disp, why):
        """Metinde bulunan ad (sozluk/hitap/anma) -> etiket; her bicimiyle maskelenir. Ad+Soyad ise ad da (belirsiz
        degilse). Daha once sozlukle bulunmus tek ad + soyad ayni kisidir (ayni etiket); katilimci adi + baska soyad
        baska kisidir (yeni etiket)."""
        k = _key(disp)
        by_contact = why in ("iletişim", "imza")      # nakliye iletisim kaniti; oteki nedenler ad kurallarinin (main) kanitidir
        known = k in self.by_key
        k0 = _key(disp.split()[0]) if len(disp.split()) == 2 else None
        if known and not by_contact and k not in self._contact_keys and not (k0 and why in ("anma", "hitap") and k0 in self._contact_keys):
            return self.by_key[k]              # (Sayın/@ kaniti ad parcasini da yayar: once baska kanitla ogrenilmis olsa da)
        parts = disp.split()
        g, f, a = name_lists()
        # S3: iletisim kanitli ad, hicbir parcasi ad sozlugunde degilse (b) yalniz o obek ve yalniz buyuk harfli bicimiyle
        # yayilir ('Sıcak Çorba', 'Mavi Kapak': soyad listesinde siradan sozcuk coktur, tek basina kanit degildir). S7: zayif
        # kanitli imza ('imza') da yalniz tam obek, buyuk harfli bicimiyle; tek parcalari yayilmaz.
        part_cap = why == "imza" or (why == "iletişim" and not any(_key(p) in g for p in parts))
        # 7. tur: katilimci ad parcasi iceren ad tam obek olarak main gibi her bicimiyle yayilir; parcalari S3'teki gibi
        # (part_cap: yalniz hitap/Sayın yaninda)
        cap = part_cap and (why == "imza" or not any(_key(p) in self._pkeys for p in parts))
        if known:                              # 7. tur eki: kanit bilineni yalniz guclendirir, sira sonucu degistirmez
            lab = self.by_key[k]
            if (not by_contact and k in self._contact_keys) or (not cap and k in self._capk):   # main'in kaniti ya da yalniz buyuk harfli
                self._strengthen(k, disp, by_contact)              # adda guclu iletisim: ayni etiketle her bicimiyle; parcalar asagida
        else:
            first = (self.by_key.get(k0) or self.ctx_labels.get(k0)) if k0 and k0 not in self._partof else None
            if first and first not in self._people and first != self.code and first != "Kişi ?":
                lab = first
            else:
                lab = (self.ctx_labels.get(k) or self._capparts.get(k)
                       or self._new_label("iletişim" if why == "imza" else why))
            (self.found_cap if cap else self.found)[disp] = lab
            self.by_key[k] = lab
            if cap:
                self._capk.add(k)
            if by_contact:
                self._contact_keys.add(k)
            if part_cap:
                # tek parca yayilmaz; ama hitaptan hemen once ya da 'Sayın'dan hemen sonra tam adin etiketini alir ('Soyad
                # bey aradı', 'Sayın Soyad'; _scan). Iki farkli adda ortak parca: notr etiket
                for p in parts if len(parts) > 1 else ():
                    pk = _key(p)
                    if len(p) >= 3 and pk not in self.by_key and pk not in _HON_STOP and not _HON.fullmatch(pk):
                        self._capparts[pk] = lab if self._capparts.get(pk, lab) == lab else "Kişi ?"
            if self._compiled:
                self._lazy.add(k)
        if k0 and k0 not in a and (k0 in g or why in ("anma", "hitap")):
            if k0 not in self.by_key:
                self.found[parts[0]] = lab
                self.by_key[k0] = lab
                if by_contact:
                    self._contact_keys.add(k0)
                if self._compiled:
                    self._lazy.add(k0)
            elif not by_contact and k0 in self._contact_keys:
                self._strengthen(k0, parts[0])
        if why == "iletişim" and len(parts) > 1 and not part_cap:   # ilke 3, S3a: guclu kanitli adin parcalari da ayni etiketle
            for p in parts:
                pk = _key(p)
                if pk not in self.by_key and pk not in a and len(p) >= 3 and not _ordinary(pk):
                    c = pk not in g and pk not in f           # sozlukte olmayan parca yalniz buyuk harfli bicimiyle
                    (self.found_cap if c else self.found)[p] = lab
                    self.by_key[pk] = lab
                    self._partof[pk] = k
                    self._contact_keys.add(pk)
                    if c:
                        self._capk.add(pk)
                    if self._compiled:
                        self._lazy.add(pk)
                elif self._partof.get(pk, k) != k and self.by_key.get(pk) not in (lab, "Kişi ?"):
                    self.by_key[pk] = "Kişi ?"        # N1: iki ogrenilmis adda ortak parca: notr etiket (main gibi)
        return lab

    def _known(self, k):
        """Ad kurallari (main) icin bilinen anahtar: yalniz nakliye iletisim/imza kanitiyla ogrenilen anahtar sayilmaz (main o
        anahtari bilmez; Sayın, hitap, @anma ve sozluk kurallari onu yine ogrenir, _learn guclendirir)."""
        return k in self.by_key and k not in self._contact_keys

    def _strengthen(self, k, disp, by_contact=False):
        """Bilinen anahtar daha guclu kanitla yeniden bulundu (main'in kaniti ya da yalniz buyuk harfli adda guclu iletisim
        kaniti): ayni etiketle her bicimiyle yayilir (yalniz buyuk harfli bicimi (S3/S7) kalkar). Kanit bilineni hic
        daraltmaz. by_contact: kanit yine iletisim kanitidir (anahtar main icin bilinmeyen kalir). -> etiket."""
        lab = self.by_key[k]
        for d in [d for d in self.found_cap if _key(d) == k]:
            v = self.found_cap[d]
            del self.found_cap[d]
            self.found[d] = v
        self.found[disp] = lab
        self._capk.discard(k)
        if not by_contact:
            self._contact_keys.discard(k)
        if self._compiled:
            self._lazy.add(k)
        return lab

    def _ad_ctx(self):
        """Mevcut mesajin (ya da mesajsiz metnin) ilan imi: telefon ya da alan olarak iletisim sozcugu (_ad_line).
        Ilk soruldugunda hesaplanir, kimligiyle saklanir."""
        self._ad_used = True
        key, src = self._actx
        v = self._adctx.get(key)
        if v is None:
            v = self._adctx[key] = any(map(_ad_line, _src_lines(src)))
        return v

    def _sig_ctx(self, line):
        """Ilk taramada satir, mevcut mesajda ilan imli bir satira komsu mu (bos satirlar sayilmaz)."""
        key, src = self._actx
        sigs = self._sigs.get(key)
        if sigs is None:
            tl = [ln for ln in _src_lines(src) if ln.strip()]
            fl = [_ad_line(ln) for ln in tl]
            sigs = self._sigs[key] = {tl[i] for i in range(len(tl)) if not fl[i] and (
                (i and fl[i - 1]) or (i + 1 < len(tl) and fl[i + 1]))}
        return line in sigs

    def _ctx_label(self, k, why, disp=None):
        """Yalniz o yerde maskelenen ad (sozcuk anlami da olan ad, zayif kanit) -> etiket. Ad-soyadin ilk parcasi bilinen
        (katilimci olmayan) ad ya da sozcuk anlami olmayan sozluk adiysa ayni kisidir: onun etiketi (ilke 3: tek etiket)."""
        if k in self.by_key:
            return self.by_key[k]
        if k not in self.ctx_labels:
            parts, lab = k.split(), None
            if len(parts) > 1 and parts[0] not in self._partof:
                lab = self.by_key.get(parts[0]) or self.ctx_labels.get(parts[0])
                g, _, a = name_lists()
                if lab is None and disp and parts[0] in g and parts[0] not in a:
                    lab = self._learn(disp.split()[0], why)
                if lab is not None and (self._participant(lab) or lab == "Kişi ?"):
                    lab = None
            self.ctx_labels[k] = lab or self._capparts.get(k) or self._new_label(why)
        return self.ctx_labels[k]

    def _special(self, line, toks, bases, keys):
        """Nakliye ilani kurallari -> (kararlar, ad kurallarinin atlayacagi sozcuk indeksleri). Karar bicimi _scan ile
        ayni; karar: 'firma' (ticari adin ayirt edici sozcukleri -> [firma]), 'rx'/'ctx' (iletisim baglamindaki kisi adi,
        neden 'iletişim'; ad testinden (sozluk adi ya da listede soyad) gecmeyen baglam bulgusu yalniz o geciste: 'ctx'),
        'join' (katilimci etiketine komsu ad parcasi etikete katilir; anahtar yerine etiket), 'mark' (ilk taramada join
        adayi: satir yeniden taranir, maske yok). Ilan sozlugu (_ILAN: il, arac, birim, ilan sozcugu) ve dolgu/alan etiketi
        sozcukleri (_FILLER) hicbir kurala aday olmaz. _ad_ctx(): mesajda ilan imi (telefon ya da alan olarak iletisim
        sozcugu); _sig_ctx(): satir, ayni mesajda ilan imli satira komsu (imza adayi)."""
        out, skip, n = [], set(), len(toks)
        il = ilan_words()
        firm = (n and (not _LEGAL_STRONG.isdisjoint(keys) or any(map(_is_sector, keys))
                       or ("." in line and _LEGAL_GLUED.search(line)) or (("Ş" in line or "ş" in line) and _AS.search(line)))
                or (bool(_DASH_RX.search(line)) and bool(_FIRM_HYPH.search(line))))
        contact = n and not _CONTACT.isdisjoint(keys)
        if not firm and not contact and not any(b[:1].isupper() and k not in il for b, k in zip(bases, keys)):
            return out, skip     # hiz: firma ve iletisim disindaki her kural buyuk harfli, ilan sozlugunde olmayan sozcuk ister
        phone = n and ("[telefon]" in line or (not self._compiled and bool(_PHONE_Q.search(line))))
        join = n and (("Kişi " in line) if self._compiled else not self._pkeys.isdisjoint(keys))
        sig = self._sigok and 2 <= n <= 3 and keys[0] in name_lists()[0]    # imza: ilk sozcuk sozluk adi
        if not (firm or contact or phone or join or sig):     # hiz: cogu satirda hicbir kural adayi yok
            return out, skip
        g, f, a = name_lists()
        ad = self._ad_ctx

        def free(j, firm=False, place_ok=False, low=False, known=False):
            """Ad sozcugu olabilir mi. firm=True: firma adinda hitap sozcugu de olur ('ABLA NAKLİYAT', ilan iminde).
            Yalniz yer adi (il, ad/soyad olmayan ilce; _pure_place) ad degildir; place_ok: soyad konumunda olabilir.
            low: kucuk harfli sozcuk de (guclu baglamda sozluk adiyla baslayan ad). known: bilinen ad parcasi da (iletisim
            adi: 'İrtibat: <katilimcinin adi> <baska soyad>' baska kisidir; soyad acikta kalmasin)."""
            b, k = bases[j], keys[j]
            if j in skip or toks[j][4] or not (low or b[:1].isupper()) or len(b) < 2 or (k in self.by_key and not known):
                return False
            if k in il or k in _CONTACT or k in _FILLER or k.startswith(_FILLER_PFX) or k in _LEGAL_K or _is_sector(k):
                return False
            if not place_ok and _pure_place(k):
                return False
            if k in _TAKVIM or k in _CAPWORD or k in _SAYIN or k in _SAYIN_STOP or _inst(k):
                return False
            if _HON.fullmatch(k):
                return firm
            return k not in _HON_STOP

        def bend(j):
            return toks[j][0] + len(bases[j])

        starts = [t[0] for t in toks]
        ends = [t[0] + len(b) for t, b in zip(toks, bases)]

        # D (ilke 4): ticari ad VARSAYILAN olarak maskelenir: guclu sektor sozcugunun (nakliyat, nakliye, nakliyeci,
        # lojistik, taşımacılık; ekli bicimleri) ya da hukuki bicimin (Ltd, Şti, A.Ş., San.+Tic.) onundeki 1-4 ayirt edici
        # sozcuk (arada 've', '&', akrabalik; tireli bicim 'Kaplo-Tavro'; bitisik katilimci etiketi ya da bilinen ad da
        # maskeye girer) tek '[firma]' olur. Zayif tetikleyici (taşıma, trans, transport, kargo, Nak., şirketi, firması)
        # ilan imi ister. Hukuki bicimde her harf buyuklugu; yalniz guclu sektor sozcugunde kucuk harfli ad ilan imi ister.
        # Dislananlar yalniz: durdurma listesi (_FIRM_STOP), yer listesi (_pure_place, il adlari), ekli hitap obegi
        # (Abilerim), ilan/dolgu/iletisim/takvim sozlukleri.
        def firm_word(w, lowok, hon):
            """-> 'd' ayirt edici sozcuk, 't' saydam (genel niteleme: durdurma listesi, ilan sozlugu, yer adi; zinciri
            kesmez, bastaysa maskelenmez), None (zinciri keser). lowok None: kucuk harfte ilan imi sorulur."""
            k = _key(w)
            if len(w) < 2:
                return None
            if k in _FIRM_STOP or k in il or _pure_place(k):
                return "t"
            if not (w[:1].isupper() or lowok or (lowok is None and ad())):
                return None
            if _HON_SG.fullmatch(k):                   # S5 (hitap sifatindan sonrasi dongude ayiklanir); SF2: kucuk harfli
                return "d" if hon or ad() else None    # sektor sozcugunden once ilan imi ister ('Dayım nakliyat işine girdi')
            if (k in _CONTACT or k in _FILLER or k.startswith(_FILLER_PFX) or k in _LEGAL_K or _is_sector(k)
                    or k in _TAKVIM or k in _CAPWORD or k in _SAYIN or k in _SAYIN_STOP or _inst(k)):
                return None
            if _HON.fullmatch(k):
                return "d" if k in _HON_BASE else None   # 'ABLA NAKLİYAT' evet, 'Abilerim Nakliye' hayir (4c)
            if k in _HON_STOP or (not w[:1].isupper() and _ordinary(k)):
                return None
            return "d"

        for m in (_FIRM_TAIL.finditer(line) if firm else ()):
            chain = m.group(0)
            hon = chain[:1].isupper()                  # sektor sozcugu buyuk harfli (SF2)
            ck = {_key(w) for w in re.findall(r"[^\W\d_]+", chain)}
            legal = bool(ck & _LEGAL_FORM or _AS.search(chain) or (ck & _SAN and ck & _TIC) or {"limited", "sirketi"} <= ck)
            strong = legal or any(_is_strong_sector(k) for k in ck)
            if not strong and not ((ck & _LEGAL_STRONG or any(_is_sector(k) for k in ck)) and ad()):
                continue
            lowok = legal or None                      # kucuk harfli sozcukte sorulur (ilan imi: _ad_used yalniz gerekince)
            el, pos = [], m.start()                    # el: (bas, son, tur: 'l' etiket/bilinen ad, 'd', 't', 'k'), sagdan sola
            while len(el) < 6:
                lm = _LABEL_END.search(line, max(0, pos - 24), pos)    # kisa pencere: uzun satirda karesel arama yok
                if lm:                                 # 'Kişi 2 Nakliyat', 'Kişi 2 ve Oğulları Nakliyat'
                    el.append((lm.start(), lm.start(), "l"))
                    pos = lm.start()
                    continue
                wm = _FIRM_PREV.search(line, max(0, pos - 64), pos)
                if not wm:
                    break
                word = wm.group(1)
                base = _APOS.split(word, 1)[0]
                if base != word and el:                # ekli sozcuk (Ali'nin) adin parcasi degil
                    break
                parts = _DASH_RX.split(base)
                bk = _key(base)
                kinds = [firm_word(x, lowok, hon) for x in parts]
                if len(parts) == 1 and bk in self.by_key and base == word and (bk not in self._capk or base[:1].isupper()):
                    kind = "l"                         # katilimci ya da bilinen ad (ciktida etiket olur)
                elif bk in _KIN and (el or base[:1].isupper()):
                    kind = "k"
                elif None not in kinds:
                    kind = "d" if "d" in kinds else "t"
                else:
                    break
                if kind == "d" and _HON_SG.fullmatch(bk):     # S5: 'Değerli Dayım Nakliye' hitap obegidir
                    pw = _FIRM_PREV.search(line, max(0, wm.start(1) - 64), wm.start(1))
                    if pw and _key(_APOS.split(pw.group(1), 1)[0]) in _ADDR_ADJ:
                        break
                el.append((wm.start(1), wm.end(1), kind))
                pos = wm.start(1)
            el.reverse()
            for i in range(1, len(el)):                # adin hemen ardindaki yer adi soyad konumundadir ('Ali Bozova Nakliyat')
                if el[i][2] == "t" and el[i - 1][2] in "ld" and _pure_place(_key(line[el[i][0]:el[i][1]])):
                    el[i] = (el[i][0], el[i][1], "d")
            if legal and not any(e[2] == "d" for e in el):     # S4: hukuki bicimde sektor sozcugune bitisik buyuk harfli
                for i in range(len(el) - 1, -1, -1):            # niteleme ve yer adi ayirt edicidir (dilbilgisi sozcugu degil)
                    w = line[el[i][0]:el[i][1]]
                    if el[i][2] != "t" or not w[:1].isupper() or _APOS.search(w) or _key(w) in _FIRM_FUNC:
                        break
                    el[i] = (el[i][0], el[i][1], "d")
            # 'X ve Oğulları', 'X Kardeşler': X aile adidir (yer adi da olsa maskelenir)
            fam = any(e[2] == "k" and _key(line[e[0]:e[1]]) not in ("ve", "&") for e in el)
            while el and (el[0][2] == "t" and not fam or (el[0][2] == "k" and not line[el[0][0]:el[0][0] + 1].isupper())):
                el.pop(0)
            if any(e[2] == "d" for e in el) or (fam and any(e[2] != "l" for e in el)):
                st, en = el[0][0], len(line[:m.start()].rstrip(" \t" + _DASH_CH))
                out.append((st, en, "", line[st:en], "firma", "firma"))
                skip.update(range(bisect.bisect_left(starts, st), bisect.bisect_left(starts, en)))

        # B (ilke 3): iletisim baglamindaki ad. GUCLU kanit: ayracli alanin (':', '-', '.', ok; '(Ofis)' gibi ekli de)
        # ardi, ayni satirdaki telefonun hemen yani, ayracli alanin ya da telefonun hemen onu (iki sozcuk ya da listede
        # ad), sozluk adi + listede soyad -> 'rx': sohbetin her yerinde tek etiket (_learn parcalari da ayni etikete baglar);
        # siradan sozcuk testinden (_ordinary) gecmeyen guclu bulgu yalniz o yerde ('ctx', 'İrtibat: Proje Masası').
        # ZAYIF kanit (ayracsiz iletisim sozcugu, telefonlu alanin onundeki tek bilinmeyen sozcuk, imza satiri): yalniz
        # o yerde ('ctx') ve yalniz testten gecerse (listede olmayan sozcuk en az 4 harf).
        tel = [(mo.start(), mo.end()) for mo in (_TEL_MASK if self._compiled else _PHONE_CTX).finditer(line)] if phone else []
        # (ciktida telefon zaten '[telefon]'; ilk taramada ham numara, yalniz en az 7 haneli dizi varsa aranir: _PHONE_Q)

        tel_st, tel_en = [t[0] for t in tel], [t[1] for t in tel]     # sirali (telefonlar cakismaz)

        def tel_after(pos):
            """pos'tan hemen sonra (arada yalniz bosluk/noktalama) telefon var mi (en yakin telefon: ikili arama)."""
            i = bisect.bisect_left(tel_st, pos)
            return i < len(tel_st) and bool(_CTX_GAP_AFTER.fullmatch(line, pos, tel_st[i]))

        def near_tel(st, en):
            i = bisect.bisect_right(tel_en, st) - 1
            return tel_after(en) or (i >= 0 and bool(_CTX_GAP_BEFORE.fullmatch(line, tel_en[i], st)))

        def take(run, strong, sig=False, local=False):
            if (len(run) == 1 and keys[run[0]] in self.by_key) or any(keys[x] in self._single for x in run):
                return          # tek bilinen ad: rx maskeler; tek sozcuklu katilimci adinin yanindaki parca etikete katilir (C)
            nx = run[-1] + 1
            if _ORG_UNIT.fullmatch(keys[run[-1]]) or (nx < n and _ORG_UNIT.fullmatch(keys[nx])
                                                       and line[ends[run[-1]]:toks[nx][0]] == " "):
                return          # S3c: birim adi ('Muhasebe Birimi', 'Gündüz Ekibi') kisi degil
            if not sig and keys[run[0]] in g and keys[run[0]] not in a:   # S11: sozluk adindan sonraki siradan sozcuk soyad
                cut = next((i for i in range(1, len(run)) if _ordinary(keys[run[i]])), None)   # degil ('Mehmet Bekliyor')
                if cut:
                    skip.update(run[cut:])             # ayni satirdaki baska kural da almaz
                    run = run[:cut]
                    if len(run) == 1 and keys[run[0]] in self.by_key:
                        return
            st, en = toks[run[0]][0], ends[run[-1]]
            k0 = keys[run[0]]
            strong = strong or near_tel(st, en) or (k0 in g and any(keys[x] in f for x in run[1:]))
            clean = not any(_ordinary(keys[x]) for x in run if not (x == run[0] and k0 in g))
            if not strong and not (clean and all(len(bases[x]) >= 4 for x in run if keys[x] not in g and keys[x] not in f)):
                return
            disp = " ".join(line[st:en].split())
            why = "imza" if sig and not strong else "iletişim"     # S7: zayif imza obegi buyuk harfli bicimiyle yayilir
            out.append((st, en, _key(disp), disp, "rx" if strong and clean and not local or why == "imza" else "ctx", why))
            skip.update(run)

        def fwd(j, low_ok=False):
            """j'den baslayan en cok 3 sozcuklu ad. low_ok (guclu baglam): ilk sozcuk sozcuk anlami olmayan sozluk adiysa
            kucuk harfli ad da ('İrtibat: hasan tavro 0500...')."""
            low = low_ok and j < n and not bases[j][:1].isupper() and keys[j] in g and keys[j] not in a
            run = []
            while j < n and len(run) < 3 and free(j, place_ok=bool(run), low=low, known=True) and (
                    not run or line[ends[run[-1]]:toks[j][0]] == " "):
                if run and low and not bases[j][:1].isupper() and _ordinary(keys[j]):
                    break
                run.append(j)
                if bases[j] != toks[j][2]:
                    break
                j += 1
            return run

        def back(j, single=False):
            """j'de biten en cok 3 sozcuklu ad (ad yer adiyla baslamaz: 'Gebze Tel: ...'; soyad konumunda olur). Tek
            bilinmeyen sozcuk yalniz single ise: telefonun hemen onu ('Tavro 0500...') ya da telefonlu alanin onu ('Tavro
            Tel: 0500...', 'TAVRO GSM 0500...'); take() siradan sozcuk testini uygular."""
            if j < 0 or bases[j] != toks[j][2]:
                return []
            run = []
            while j >= 0 and len(run) < 3 and free(j, place_ok=True, known=True) and (
                    not run or line[ends[j]:toks[run[0]][0]] == " "):
                run.insert(0, j)
                j -= 1
            while run and _pure_place(keys[run[0]]):
                run.pop(0)
            return run if run and (len(run) > 1 or keys[run[0]] in g or keys[run[0]] in f or single) else []

        for j0 in (range(n) if contact else ()):
            if keys[j0] not in _CONTACT or bases[j0] != toks[j0][2]:
                continue
            fm = _CONTACT_FIELD.match(line, toks[j0][0])
            sep = bool(fm)
            direct = tel_after(toks[j0][1])                                                  # 'GSM 0500...'
            # L1: alan olarak iletisim sozcugunun (ya da telefonun hemen onundeki iletisim sozcugunun) onundeki ad; ayracsiz
            # ve telefonsuz satirda yalniz ilan imli mesajda ve zayif kanitla ('AD SOYAD İRTİBAT' + alt satirda telefon)
            if (sep or tel or ad()) and j0 and _CTX_GAP_BEFORE.fullmatch(line, ends[j0 - 1], toks[j0][0]):
                run = back(j0 - 1, single=(sep or direct) and bool(tel))
                if run:
                    take(run, (sep or direct) and (len(run) > 1 or keys[run[0]] in g or keys[run[0]] in f))
            if fm:                                     # ayracli alan: ad ayractan sonra baslar ('Tel (Ofis): Ad Soyad')
                j = bisect.bisect_left(starts, fm.end())
                if j < n and _CTX_GAP_AFTER.fullmatch(line, fm.end(), toks[j][0]):
                    run = fwd(j, low_ok=True)
                    if run:
                        take(run, True)
                        continue
            j = j0 + 1
            if j >= n or not _CTX_GAP_AFTER.fullmatch(line, toks[j0][1], toks[j][0]):
                continue
            # P1: ':' ile biten 1-3 sozcuk alan etiketidir; ':'dan sonra ad yoksa (telefon, satir sonu) etiket sanilan serbest
            # sozcukler adin kendisidir ('İrtibat Ad: 0500...')
            run, strong = None, sep
            for c in range(j, min(j + 3, n)):
                if c > j and line[toks[c - 1][1]:toks[c][0]] != " ":
                    break
                cm = _COLON.match(line, toks[c][1])
                if cm:
                    strong = True
                    nx = c + 1
                    run = fwd(nx, low_ok=True) if nx < n and _CTX_GAP_AFTER.fullmatch(line, cm.end(), toks[nx][0]) else []
                    if not run and all(free(x) for x in range(j, c + 1)):
                        run = fwd(j)
                    break
            if run is None:
                run = fwd(j)
            # P2: iletisim sozcugunden sonra ad icin ayrac, satirda telefon ya da mesajda ilan imi gerekir ('WhatsApp Web
            # açılmıyor', 'Yetkili Servis' ad degil); ayracsiz iletisim sozcugu zayif kanittir (yalniz o yerde). Yalniz ilan
            # imiyle tek sozcuk back() gibi ancak listede adsa alinir ('İletişim Kurun Lütfen' ad degil)
            if run and (strong or tel or (ad() and (len(run) > 1 or keys[run[0]] in g or keys[run[0]] in f))):
                take(run, strong)
        for st_, en_ in tel:                           # telefonun hemen yani: guclu
            j = bisect.bisect_left(starts, en_)
            if j < n and _CTX_GAP_AFTER.fullmatch(line, en_, toks[j][0]):
                # N6: kanal etiketinden sonraki ad ('[telefon] Ofis: Ad Soyad'); 6. tur: yalniz ad sozlugu parcasi iceren
                # aday, yalniz o yerde ('[telefon] Mobil Uygulama' ad degil, sohbete yayilmaz)
                lab = (keys[j] in _CONTACT or keys[j] in _FILLER) and j + 1 < n and bool(
                    _CTX_GAP_AFTER.fullmatch(line, ends[j], toks[j + 1][0]))
                run = fwd(j + 1 if lab else j)
                # 7. tur: ad sozlugunde de olan etiket sozcugu ':' almadan (tek boslukla) adin ilk parcasidir ('[telefon]
                # Sabit Ad': tek etiket, yalniz o yerde)
                if run and lab and keys[j] in g and bases[j] == toks[j][2] and bases[j][:1].isupper() and (
                        line[ends[j]:toks[j + 1][0]] == " "):
                    run = [j] + run
                if run and (not lab or any(keys[x] in g for x in run)):
                    take(run, True, local=lab)
            j = bisect.bisect_right(ends, st_) - 1
            if j >= 0 and _CTX_GAP_BEFORE.fullmatch(line, ends[j], st_):
                run = back(j, single=True)             # 'Tavro 0500...'; yer adi ve ilan/dolgu sozcugu degil ('Gebze 0500')
                if run:
                    take(run, True)

        # L5: imza satiri (zayif kanit): ayni mesajda ilan imli satira komsu, yalniz ad bicimli satir (istege bagli
        # emoji/noktalama, sonra 2-3 buyuk harfli sozcuk, ilki sozluk adi): '🪪 Ad Soyadı' -> yalniz o yerde; soyad
        # konumundaki sozcukler siradan sozcuk testinden gecmeli ('Sevgi Saygılarımla', 'Umut Ediyoruz' imza degil)
        if (sig and not out and keys[0] in g and all(free(j) and bases[j] == toks[j][2] for j in range(n))
                and all(line[ends[j]:toks[j + 1][0]] == " " for j in range(n - 1))
                and not _ALNUM.search(line, 0, toks[0][0]) and not _ALNUM.search(line, ends[-1]) and self._sig_ctx(line)):
            take(list(range(n)), False, sig=True)

        # C: katilimci etiketine ('Kişi N') ya da ham metinde katilimci ad parcasina yapisik tek ad parcasi. '+'/'&' ile ya da
        # imza satirinda her zaman; boslukla yalniz ilan iminde (F2: 'dün Review Kişi N yaptı' siradan sozcugu yutmaz)
        if not join:
            return out, skip
        last = -9                                      # son join'in sonu: etiketin iki yanindaki parcadan yalniz ilki
        for j in range(n):
            if not self._compiled:                     # ilk tarama: yalniz komsu katilimci ad parcasi -> yeniden tara
                nb = [o for o in (j - 1, j + 1) if 0 <= o < n and self._participant(self.by_key.get(keys[o]))]
                if not nb or not free(j) or keys[j] in g:
                    continue
                st, en = toks[j][0], ends[j]
                for o in nb:
                    lo, hi = (toks[o][1], st) if o < j else (en, toks[o][0])
                    if _JOIN_GAP.fullmatch(line[lo:hi]):
                        out.append((st, en, "", bases[j], "mark", ""))
                        break
                continue
            if not free(j) or keys[j] in g:
                continue
            st, en = toks[j][0], ends[j]
            if st < last + 2:
                continue
            gr = _JOIN_GAP.match(line, en)
            lr = gr and _LABEL_AT.match(line, gr.end())
            if (lr and lr.group(0) in self._people   # '<ad> Kişi N' / '<ad>+Kişi N'; onunde baska ad parcasi yoksa
                    and not (j and free(j - 1) and ends[j - 1] + 1 == st and line[ends[j - 1]] == " ")):
                gap = gr.group(0)
                solo = not line[:st].strip() and not line[lr.end():].strip()
                sig_tail = bool(_SIG_TAIL.fullmatch(line, lr.end()))
                if "+" in gap or "&" in gap or solo or ((not toks[j][3] or sig_tail) and ad()):
                    out.append((st, lr.end(), lr.group(0), bases[j], "join", ""))
                    skip.add(j)
                    last = lr.end()
                    continue
            if bases[j] != toks[j][2]:
                continue
            ll = _LABEL_BEFORE.search(line, max(0, st - 24), st)    # 'Kişi N <ad>' (kisa pencere: karesel arama yok)
            if (ll and ll.group(1) in self._people
                    and not (j + 1 < n and free(j + 1) and toks[j + 1][0] == en + 1 and line[en] == " ")):
                gap = line[ll.end(1):st]
                solo = not line[:ll.start()].strip() and not line[en:].strip()
                if "+" in gap or "&" in gap or solo or ad():
                    out.append((ll.start(), en, ll.group(1), bases[j], "join", ""))
                    skip.add(j)
                    last = en
        return out, skip

    def _scan(self, line):
        """Satirdaki olasi adlar -> [(bas, son, anahtar, gosterim, karar, neden)].
        karar: 'rx' her bicimiyle maskelenir (sozcuk anlami olmayan sozluk adi, Ad Soyad, hitapli/@anilan/Sayın'li
        bilinmeyen ad), 'ctx' yalniz bu geciste (sozcuk anlami da olan ad, baglam var), 'review' maskelenmez, supheli
        kalan sayilir. Yer/kurum adinin parcasi olan ad (Mimar Sinan Üniversitesi, Hz. Muhammed) hic karar almaz."""
        g, f, a = name_lists()
        toks = _tokens(line)
        bases = [_APOS.split(t[2], 1)[0] for t in toks]
        keys = [_key(b) for b in bases]
        spec, _ = self._special(line, toks, bases, keys)
        out = []
        n = len(toks)

        def emit(st, en, k, disp, act, why):
            if not self._participant(self.by_key.get(_key(disp.split()[0]))):   # katilimci adi: istisna yok
                lm = _landmark(line, st, en)
                if lm:
                    return
                if lm is None and self._counting:
                    self.stats["yer/kurum belirsiz"] = self.stats.get("yer/kurum belirsiz", 0) + 1
            out.append((st, en, k, disp, act, why))

        def pfull(j, people=False):
            """toks[j]'den baslayan metin bir katilimcinin cok parcali tam adi mi: oncesindeki sozluk adiyla eslenmez
            (Mimar Mert Er -> Mimar + katilimcinin tam adi; yoksa soyad acikta kalirdi). people: yalniz kisi
            etiketi (sohbet adi degil; kurum adli grup basligi metinde maskelenmez, supheli sayimi surer)."""
            parts = []
            for t in toks[j:j + 4]:
                if parts and line[parts[-1][1]:t[0]].strip():
                    break
                tb = _APOS.split(t[2], 1)[0]
                parts.append((t[0], t[0] + len(tb), tb))
                lab = self.by_key.get(_key(" ".join(p[2] for p in parts))) if len(parts) > 1 else None
                if self._participant(lab) and not (people and lab == self.code):
                    return True
                if tb != t[2]:
                    break
            return False

        sec = []

        def sector_line():
            """Satirda guclu sektor sozcugu var mi (satir basina bir kez: aday basina tum satiri taramak karesel)."""
            if not sec:
                sec.append(any(_is_strong_sector(x) for x in keys))
            return sec[0]

        def surname_like(nb, nk, k, j):
            """toks[j] (gosterim nb, anahtar nk) k adinin soyadi olabilir mi -> 1: listede (soyad, sozcuk anlami olmayan
            ad, soyad eki; main'deki kural, guclu); 2: L4, zayif kanit (ilke 3): sozcuk anlami olmayan sozluk adinin
            ardindaki listede olmayan sozcuk soyad konumunda (satir sonu; telefon, iletisim sozcugu ya da ayrac oncesi),
            ilan iminde, hemen ardinda iletisim sozcugu ya da satirda guclu sektor sozcugu varken, siradan sozcuk testinden
            (_ordinary) geciyor ve en az
            4 harfli ('Hasan Gelsin', 'Mehmet Yazıyor:' degil) -> yalniz o yerde; 0: hayir."""
            if (not nb[:1].isupper() or len(nb) < 3 or nk in _TAKVIM or nk in _CAPWORD or _HON.fullmatch(nk)
                    or nk in _HON_STOP):
                return 0
            if nk in f or (nk in g and nk not in a) or _SURNAME_SFX.search(nk):
                return 1
            if not (k in g and k not in a and nb == toks[j][2]) or len(nb) < 4 or _ordinary(nk):
                return 0
            e = toks[j][0] + len(nb)
            cnext = j + 1 < n and keys[j + 1] in _CONTACT and not line[e:toks[j + 1][0]].strip()   # 'AD SOYAD İRTİBAT'
            if not (cnext or _SURNAME_POS.match(line, e) or _PHONE_CTX.match(line, _HWS.match(line, e).end())):
                return 0                               # soyad konumu degil
            # baglam: hemen ardinda iletisim sozcugu, ayni satirda guclu sektor sozcugu ('… NAKLİYAT AD SOYAD') ya da ilan imi
            return 2 if cnext or sector_line() or self._ad_ctx() else 0

        def pair(i, st, nxt, nb, why="sözlük", weak=False):
            """Ad + Soyad; ardinda buyuk harfli ucuncu parca varsa o da (Mehmet Ali Xandor). weak: zayif kanitli ad-soyad
            (L4) yalniz o yerde ('ctx'; etiket adin etiketidir, _ctx_label). -> sonraki indeks."""
            end, disp, j = nxt[0] + len(nb), line[st:nxt[0] + len(nb)], i + 1
            if nxt[2] == nb and j < n and not line[end:toks[j][0]].strip():
                tb = _APOS.split(toks[j][2], 1)[0]
                tk = _key(tb)
                if (tb[:1].isupper() and len(tb) >= 3 and not tb.isupper() and tk not in _HON_STOP and tk not in _TAKVIM
                        and tk not in _CAPWORD and not _HON.fullmatch(tk) and (tk not in g or tk in f)
                        and not _INST_ANY.match(tk) and not _INST_CAP.match(tk) and not pfull(j)):
                    end, disp, j = toks[j][0] + len(tb), line[st:toks[j][0] + len(tb)], j + 1
            emit(st, end, _key(disp), " ".join(disp.split()), "ctx" if weak else "rx", why)
            return j

        i = 0
        while i < n:                          # ilke 2: ad kurallari (main) ozel kararlardan bagimsiz; birlesim _merge'de
            st, en, w, ini, men = toks[i]
            base, k = bases[i], keys[i]
            i += 1
            if k in self._lazy and (k not in self._capk or base[:1].isupper()):   # derlemeden sonra ogrenilen ad
                emit(st - men, st + len(base), k, base, "rx", self.origin.get(self.by_key[k], "sözlük"))
                continue
            cap = base[:1].isupper()
            if men:                           # @anma: katilimci degilse ad gibi duran sozcuk maskelenir
                if not self._known(k) and len(base) >= 2 and (cap or k in g or k in f):
                    emit(st - 1, st + len(base), k, base, "rx", "anma")
                continue
            if k in _SAYIN:                   # 'Sayın Ad Soyad', 'Sn. Ad': ardindaki buyuk harfli 1-3 sozcuk
                run, j, prev = [], i, en
                while j < n and len(run) < 3:
                    t = toks[j]
                    if line[prev:t[0]].strip() not in ("", ".") or (run and line[prev:t[0]].strip()):
                        break
                    tb = _APOS.split(t[2], 1)[0]
                    tk = _key(tb)
                    if (not tb[:1].isupper() or tk in _HON_STOP or tk in _SAYIN_STOP or _HON.fullmatch(tk)
                            or tk in _TAKVIM or _NOT_NAME_SFX.search(tk) or self._known(tk) or len(tb) < 2):
                        break
                    run.append(tb)
                    prev, j = t[0] + len(tb), j + 1
                    if t[2] != tb:
                        break
                if run:
                    s0 = toks[i][0]
                    disp = line[s0:prev]
                    emit(s0, prev, _key(disp), disp, "rx", "hitap")
                    i = j
                continue
            if len(base) < 3 or (not cap and k not in g) or _HON.fullmatch(k):
                continue                      # kucuk harfli, sozlukte olmayan sozcuk hicbir kurala girmez
            if k in self._mstart and pfull(i - 1, True):            # katilimcinin cok parcali adi burada basliyor (Ali Su): rx maskeler
                continue
            nxt = toks[i] if i < n and not line[en:toks[i][0]].strip() else None
            nb = _APOS.split(nxt[2], 1)[0] if nxt else ""
            nk = _key(nb)
            if k in self.by_key:              # bilinen ad + listede soyad: baska tam ad (Kenan Er varken Kenan Karakoç)
                sl = cap and nxt and surname_like(nb, nk, k, i)
                if sl and not self._known(_key(base + " " + nb)) and not pfull(i):
                    i = pair(i, st, nxt, nb, weak=sl == 2)
                    continue
                if self._known(k):            # bilinen tam ad (zayif imza da) rx'te tek etiket; ardindaki sozcuk main'deki
                    continue                  # gibi kendi kurallarindan gecer. Yalniz iletisimle bilinen ad (_contact_keys) asagidaki
                                              # ad kurallarindan da gecer (main'in kaniti onu guclendirir)
            sl = k in g and cap and k not in _TAKVIM | _CAPWORD and nxt and surname_like(nb, nk, k, i)
            if sl and not pfull(i):
                i = pair(i, st, nxt, nb, weak=sl == 2)      # Ad + Soyad (+ ucuncu parca)
                continue
            if nxt and _HON.fullmatch(nk):
                if k in g:
                    emit(st, st + len(base), k, base, "ctx" if k in a else "rx", "hitap")
                elif cap and k not in _HON_STOP and k not in _TAKVIM and not _HON_ORG.fullmatch(nk):
                    if k in f:                # soyad + hitap (Karakoç Hoca, Şimşek abi): satir basinda da
                        act = "ctx" if k in a else "rx"
                    else:                     # satir basinda bilinmeyen sozcuk supheli; ogrenilmis adin parcasi (_capparts) o yerde
                        act = ("ctx" if k in self._capparts else "review") if ini else "rx"
                    emit(st, st + len(base), k, base, act, "hitap")
                continue
            if k not in g or k in _TAKVIM:
                continue
            prv = toks[i - 2] if i >= 2 and not line[toks[i - 2][1]:st].strip() else None
            titled = any(t and t[2][:1].isupper() and (_key(_APOS.split(t[2], 1)[0]) not in g
                                                      or _key(_APOS.split(t[2], 1)[0]) in a)
                         for t in (prv, nxt))      # 'Temel Satranç Eğitimi', 'Türk Medeni Kanunu': baslik bicimi
            if k in _CAPWORD:
                titled = True                      # hep buyuk harfle yazilan ad olmayan sozcuk (Türk, Ege, Kuzey)
            if k not in a:
                emit(st, st + len(base), k, base, "rx", "sözlük")
            elif cap and not base.isupper() and (w != base or (not ini and not titled)):
                emit(st, st + len(base), k, base, "ctx", "sözlük")
            elif not cap and (w != base or any(t and _key(_APOS.split(t[2], 1)[0]) in self.by_key for t in (prv, nxt))):
                emit(st, st + len(base), k, base, "ctx", "sözlük")   # kucuk harf: yalniz kesme eki / yaninda bilinen ad
            else:
                emit(st, st + len(base), k, base, "review", "sözlük")
        return _merge(line, spec, out) if spec else out

    def _ctx(self, text, raw=None):
        """Sozluk/hitap kararlarini metne uygular (rx'in maskelemedigi baglamli gecisler) ve supheli kalanlari sayar.
        Inceleme ornekleri maskelemeden SONRAKI satirdan alinir: dosya yalniz ciktida zaten duran metni gosterir.
        raw: rx'ten onceki metin; ilk taramada karar cikmamis satirlar yeniden taranmaz (hiz)."""
        lines = text.split("\n")
        rlines = raw.split("\n") if raw is not None else None
        if rlines is not None and len(rlines) != len(lines):
            rlines = None
        key = self._actx[0]
        for n, line in enumerate(lines):
            if rlines is not None and (rlines[n] in self._quiet or (key, rlines[n]) in self._quiet_m):
                continue
            dec = self._scan(line)
            rev, subs = [], []
            for st, en, k, disp, act, why in reversed(dec):     # sagdan sola (etiket sirasi eskisi gibi)
                if act == "review":
                    rev.append((k, disp, why))
                    continue
                if act in ("mark", "learn"):
                    if act == "learn":
                        self._learn(disp, why)
                    continue
                lab = (self._learn(disp, why) if act == "rx" else self._ctx_label(k, why, disp) if act == "ctx"
                       else "[firma]" if act == "firma" else k)          # join: k katilimci etiketidir
                if self._counting:
                    self.stats[self.origin.get(lab, why)] = self.stats.get(self.origin.get(lab, why), 0) + 1
                subs.append((st, en, lab))
            if subs:                      # satir bir kez kurulur (her kararda yeniden kurmak uzun satirda karesel)
                parts, pos = [], 0
                for st, en, lab in reversed(subs):
                    parts += [line[pos:st], lab]
                    pos = en
                line = "".join(parts) + line[pos:]
            lines[n] = line
            if rev and self._counting:
                for k, disp, why in reversed(rev):
                    why = ("hitap" if why == "hitap" else "büyük" if disp[:1].isupper() else "küçük")
                    r = self.review.setdefault(k, [disp, 0, why, []])
                    r[1] += 1
                    if len(r[3]) < 3:
                        mo = re.search(r"(?<!\w)" + re.escape(disp) + r"(?!\w)", line)
                        if mo:
                            r[3].append(line[max(0, mo.start() - 40):mo.end() + 40].strip())
        return "\n".join(lines)

    def _pre_apply(self, text, key, rx):
        """Ilk taramada bir satir icin verilmis yerel kararlar ('ctx': zayif kanitli ad, imza, sozcuk anlami da olan ad;
        'firma': ticari ad) ayni satirda rx'ten ONCE uygulanir: rx satirdaki bir adi (sozluk adi, katilimci parcasi)
        etiketleyip yerel bulguyu bolmesin ('Ad Soyad' zayif ad-soyadda ad etiketlenir, soyad kalirdi). Karar ayni ham
        satir ve ayni ilan imi icin ayni oldugundan yeniden hesaplanmaz; satir degismisse (parola maskesi) cikti taramasi
        (_ctx) yine calisir."""
        lines = text.split("\n")
        hit = False
        for i, line in enumerate(lines):
            dec, done = self._pre.get((key, line), (None, False))
            if not dec:
                continue
            hit = True
            # 7. tur eki: rx'in maskeleyecegi daha uzun bir adin (main'in ogrendigi tam ad) icinde kalan yerel karar ('ctx' ya
            # da ticari ad) uygulanmaz; adi rx bolunmeden maskeler (main'de rx yerel karardan once calisir)
            spans = [mm.span(gn) for mm in rx.finditer(line) for g1, gn in (("name", "nm"), ("nsfx", "nn"))
                     if mm.groupdict().get(g1) and self._name_label(mm, gn, False)]
            inner = {d for d in dec if d[4] in ("ctx", "firma")
                     and any(a <= d[0] and d[1] <= b and b - a > d[1] - d[0] for a, b in spans)}
            inner = {d for d in inner if not any(x not in inner and x[0] < b and a < x[1] for x in dec for a, b in spans
                                                     if a <= d[0] and d[1] <= b)}
            parts, pos = [], 0
            for st, en, k, disp, act, why in dec:
                if (st, en, k, disp, act, why) in inner:
                    continue
                lab = "[firma]" if act == "firma" else self._ctx_label(k, why, disp)
                if self._counting:
                    cat = "firma" if act == "firma" else self.origin.get(lab, why)
                    self.stats[cat] = self.stats.get(cat, 0) + 1
                parts += [line[pos:st], lab]
                pos = en
            lines[i] = "".join(parts) + line[pos:]
            if done:                      # bu satirin kararlari tamam: cikti taramasi atlanir (_ctx, _quiet_m)
                self._quiet_m.add((key, lines[i]))
        return "\n".join(lines) if hit else text

    def _sub(self, m):
        out, cat = self._mask(m)
        if self._counting and cat:
            self.stats[cat] = self.stats.get(cat, 0) + 1
        return out

    def _rx_sub(self, rx, s):
        """rx.sub(self._sub, s). 7. tur eki: yalniz iletisim kanitiyla bilinen adin eslesmesinin icinde baslayip disina tasan
        ogrenilmis ad (ortusen iki ad, 'A B C' ve 'B C D': en soldaki en uzun eslesme 'D'yi acik birakirdi) tasan kismiyla
        birlikte maskelenir; dalin main'de olmayan daha uzun adi main'in ogrendigi adi yutsa da onun hicbir sozcugu acik
        kalmaz."""
        m = rx.search(s)
        if m is None:
            return s
        names = [g for g in ("name", "nsfx") if g in rx.groupindex]
        out, pos = [], 0
        while m is not None:
            if self._caprx is not None and "name" in names and m.group("name"):   # ayni konumda daha uzun buyuk harfli ad
                cm = self._caprx.match(s, m.start())
                if cm and cm.group("name") and cm.end() > m.end():
                    m = cm
            rep, end = self._sub(m), m.end()
            gn = next(({"name": "nm", "nsfx": "nn"}[g] for g in names if m.group(g)), None)
            # yalniz iletisim kanitiyla bilinen ad (_contact_keys; main onu bilmez, icindeki adi main eslerdi): oteki eslesmeler rx.sub
            p = m.start(gn) if gn and rep != m.group(0) and _key(" ".join(m.group(gn).split())) in self._contact_keys else end
            while p < end:
                ext = None
                for w in _GAP_WS.finditer(s, p, end):
                    mm = rx.match(s, w.end())
                    if mm and mm.end() > end and any(mm.group(g) for g in names):
                        ext = mm
                        break
                if ext is None:
                    break
                tail = self._sub(ext)                   # etiket (+ ek): tasan sozcuklerin yerine
                if tail == ext.group(0):
                    break
                lead = _GAP_WS.match(s, end)
                rep += (lead.group(0) if lead else "") + tail
                p, end = ext.start(), ext.end()
            out += [s[pos:m.start()], rep]
            pos = end
            m = rx.search(s, pos) if pos < len(s) else None
        out.append(s[pos:])
        return "".join(out)

    def _web(self, m):
        """Ciplak isletme alan adi (bkz. _WEB): kayitli ad ve hemen ustundeki alt alandan, genel olmayan sektor sozcugu
        tasiyan ana makinede ayirt edici etiket(ler) [firma] olur."""
        host = m.group("wbh")
        if not _WEB_SQ.search(_key(host)):              # hiz: genel olmayan sektor sozcugu yoksa alan adina dokunulmaz
            return m.group(0)
        labels = host.split(".")
        if len(labels) > 1 and m.group("wbt").lower() == ".tr" and labels[-1].lower() in _TR_SLD_NC:
            return m.group(0)                           # 'ornek-lojistikbirligi.org.tr': ticari olmayan ikinci duzey
        i = 0
        while i < len(labels) - 1 and _key(labels[i]) in _WEB_PRE:
            i += 1
        cand = range(max(i, len(labels) - 2), len(labels))
        keys = {c: _key(labels[c]) for c in cand}
        if not any(w in k for k in keys.values() for w in _WEB_KEYS):
            return m.group(0)
        hit = [c for c in cand if _web_distinct(keys[c])]
        if not hit:                     # sektor etiketi genel ('ornekfirma.panel.nakliyat.com'): daha alttaki ayirt edici etiket
            hit = [c for c in range(i, max(i, len(labels) - 2)) if _web_distinct(_key(labels[c]))]
        if hit and not _WEB_STRONG.search(_key(host)) and not self._ad_ctx():   # S9: zayif sozcuk ('transport') ilan imi
            hit = [c for c in hit if _WEB_SQ.search(_key(labels[c]))]          # olmadan yalniz kendi etiketini kurar
        if not hit:                                     # 'transportation.com', 'www.nakliyat.com': genel sozcuk
            return m.group(0)
        for c in hit:
            labels[c] = "[firma]"
        if self._counting:
            self.stats["firma"] = self.stats.get("firma", 0) + 1
        return m.group("wbp") + ".".join(labels) + m.group("wbt")

    def _url_rest(self, m):
        """Ana makinesi maskelenmis URL'nin yolu/sorgusu/parcasi: '/[yol]'. Sondaki noktalama ve yalniz ESLESMEYEN kapanan
        parantez kalir ('(bkz. …/a)' -> '…/[yol])'); yoldaki dengeli parantez yolun parcasidir ('/a(b)' -> '/[yol]')."""
        r = m.group("ur")
        end = len(r)
        while end > 1:
            c = r[end - 1]
            if c in ".,;:!?'\"\u2026" or (c in _CLOSERS and r.count(c, 0, end) > r.count(_CLOSERS[c], 0, end)):
                end -= 1
            else:
                break
        if end <= 1:
            return m.group(0)
        return m.string[m.start():m.start("ur")] + r[0] + "[yol]" + r[end:]

    def _handle(self, m):
        if self._counting:
            self.stats["kullanıcı adı"] = self.stats.get("kullanıcı adı", 0) + 1
        return "[kullanıcı]"

    def _cat(self, lab):
        return "sohbet adı" if lab == self.code else self.origin.get(lab, "gönderen")

    def _mask(self, m):
        """-> (yerine, kategori|None)."""
        if m.group("wame"):
            return m.group("wp") + "[telefon]", "telefon"
        if m.group("social"):
            return m.group("sp") + "[kullanıcı]", "kullanıcı adı"
        if m.group("iban"):
            return "[iban]", "iban"
        if m.group("email"):
            return "[e-posta]", "e-posta"
        if m.groupdict().get("cat"):
            lab = self.cat_keys.get(_key(re.sub(r"[._\-]", "", m.group("cat"))))
            if lab is None:
                return m.group("cat"), None
            st, en, t = m.start("cat"), m.end("cat"), m.string
            b, a = (t[st - 1] if st else ""), (t[en] if en < len(t) else "")
            a2 = t[en + 1] if en + 1 < len(t) else ""
            inside = (b.isalnum() or b in _TOKEN_BEFORE or a.isalnum() or a in _TOKEN_AFTER
                      or (a in "-." and a2.isalnum()))
            return (lab.replace(" ", "-") if inside else lab), self._cat(lab)
        if m.groupdict().get("nsfx"):
            lab = self._name_label(m, "nn")
            if lab is None:
                return m.group("nsfx"), None
            return (f"{lab}'{m.group('sx')}" if m.group("sx") else lab), self._cat(lab)
        if m.groupdict().get("name"):
            lab = self._name_label(m, "nm")
            if lab is None:
                return m.group("name"), None
            return lab + (m.group("suf") or ""), self._cat(lab)
        if m.group("tckn"):
            return "[tckn]", "tckn"
        if m.group("plaka"):
            return "[plaka]", "plaka"
        return "[telefon]", "telefon"

    def _name_label(self, m, grp, count=True):
        """rx ad eslesmesinin (grp: 'nm' ya da 'nn') etiketi; maskelenmeyecekse (yer/kurum adinin parcasi, kanitli
        guzergahtaki yer adi) None. count=False: 'yer/kurum belirsiz' sayilmaz (yalniz yoklama: _pre_apply)."""
        lab = self.by_key.get(_key(" ".join(m.group(grp).split())))
        if lab is None or self._landmark_hit(m, grp, lab, count) or self._route_hit(m, grp):
            return None
        return lab

    def _participant(self, lab):
        """Etiket bir katilimcinin (gonderen, sistem satiri kisisi, ek ad, bire bir baslik; belirsiz ad parcasi 'Kişi ?')
        ya da kisi adli sohbet basliginin mi: bunlara hicbir istisna (yer/kurum, Hz.) uygulanmaz."""
        return lab is not None and (lab in self._people or lab == self.code or lab == "Kişi ?")

    def _route_hit(self, m, grp):
        """F3: katilimci adinin yalniz ilk olmayan konumdaki, sozlukte ad/soyad olmayan tek parcasi ('Bozova') guzergah
        baglaminda yer adidir: 'Şanlıurfa ➡️ Bozova', 'Bozova yüklemeli', "Bozova'dan Mersin'e" maskelenmez."""
        return (bool(self._route_keys) and _key(m.group(grp)) in self._route_keys
                and _route(m.string, m.start(grp), m.end(grp), m.end()))

    def _landmark_hit(self, m, grp, lab, count=True):
        """Katilimci olmayan sozluk adi dar bicimli yer/kurum adinin parcasi mi (Mimar Sinan Üniversitesi, Hz. Muhammed).
        Karar yoksa maskelenir ve 'yer/kurum belirsiz' sayilir."""
        if self._participant(lab):
            return False
        lm = _landmark(m.string, m.start(grp), m.end(grp), m.end())
        if lm is None and self._counting and count:
            self.stats["yer/kurum belirsiz"] = self.stats.get("yer/kurum belirsiz", 0) + 1
        return bool(lm)

    def text(self, s, m=None, title=False, cred=True, count=False):
        """m: mesaj (parola kurallari icin durum: ayni mesajin sonraki satiri, anahtar kelimeden sonraki kisa mesaj).
        title: sohbet adi da maskelenir (sistem satiri, dosya adi); mesaj metninde False (sohbet adinin sozcukleri
        siradan cumlede kalir). cred=False: parola/kod algilama yok (ek basligi, dosya adi). count: ozet sayimi."""
        if m is None or id(m) != self._cur:
            self._cur, self._pend = (None if m is None else id(m)), 0
        cand = self._cand.get(id(m)) if m is not None else None
        out = []
        for line in s.split("\n"):
            if not cred:                  # baslik satiri; ama anahtar kelimeli satirin ardindaki tek sozcuk yine deger,
                v = line.strip()          # anahtar kelimeli komsu mesajin ardindaki ek basligi da (ekin kendi adi degilse)
                stem, ext = os.path.splitext(v)   # 'fatura.pdf' degil, 'Zorlu61.pdf' (kok parola gibi)
                capt = (cand and len(v.split()) == 1 and nfc(v) not in self._own.get(id(m), ())
                        and _cred_like(stem if ext.lower() in _FILE_EXT else v, cand))
                out.append(line if not ((self._pend and _next_line_value(line)) or capt)
                           else line[:len(line) - len(line.lstrip())] + _mask_tok(v, self._secrets))
                continue
            if self._pend:
                toks = line.split()
                if _next_line_value(line) and (self._pend == 2 or _cred_like(line.strip())):
                    self._pend -= 1
                    out.append(line[:len(line) - len(line.lstrip())] + _mask_tok(line.strip(), self._secrets))
                    continue
                if 1 < len(toks) <= 3 and _cred_like(toks[0]):   # 'Deneme.80 yapalim' -> yalniz parola gibi sozcuk
                    out.append(" ".join(_mask_tok(t, self._secrets) if _cred_like(t) else t for t in toks))
                    self._pend = 0
                    continue
                self._pend = 0
            if id(m) in self._cand_code:
                line = re.sub(r"^(%s*)%sd{6,8}$" % (chr(92) + "s", chr(92)), lambda x: x.group(1) + "[kod]", line)
            if cand:
                line = " ".join(_mask_tok(t, self._secrets) if _cred_like(t, cand) else t for t in line.split(" "))
            for sec in sorted(self._secrets, key=len, reverse=True):
                if sec in line:
                    line = re.sub(r"(?<![\w])" + re.escape(sec) + r"(?!\w)", "[parola]", line)
            line, pend = _cred_line(line, self._secrets)
            if pend and m is not None:
                self._pend = 2
            out.append(line)
        if m is None or not cred:
            self._pend = 0
        joined = "\n".join(out)
        self._counting = count
        # ilan imi: mesajinki (ilk taramadaki degerle ayni); mesajsiz metinde (alinti, dosya adi) metnin kendisinden
        self._actx = (id(m), m) if m is not None else (("s", s), s)
        try:
            if count:
                for tag, cat in (("[parola]", "parola"), ("[kod]", "kod")):
                    n = joined.count(tag) - s.count(tag)
                    if n > 0:
                        self.stats[cat] = self.stats.get(cat, 0) + n
            if title and _SUBJECT.search(joined):
                joined = _QUOTED.sub(lambda q: q.group(1) + self.code + q.group(3), joined)
                if count:
                    self.stats["sohbet adı"] = self.stats.get("sohbet adı", 0) + 1
            if self._actx[0] in self._pre_keys:   # ilk taramanin yerel kararlari, rx bir parcasini etiketleyip bolmeden once
                joined = self._pre_apply(joined, self._actx[0], self.rx_t if title else self.rx)
            if _WEB_Q.search(joined):     # nakliye isletmesi alan adi (yalniz ticari uzantili satirda: hiz)
                joined = _WEB_RX.sub(self._web, joined)
            if "@" in joined:             # tek basina sosyal kullanici adi (yalniz '@' iceren satirda: hiz)
                joined = _HANDLE.sub(self._handle, joined)
            out = self._ctx(self._rx_sub(self.rx_t if title else self.rx, joined), joined)
            if ("Kişi" in out or "[firma]" in out or self.code in out) and _URL_Q.search(out):   # L9: maskeli ana makine
                out = self._url_rx.sub(self._url_rest, out)
            return out
        finally:
            self._counting = False

    def sender(self, s):
        return self.labels.get(s, s) if s else s

    def media_name(self, real):
        """Adinda ad/telefon/e-posta/sohbet adi varsa notr 'medya-N.uzanti' adi (sohbet icinde sirayla).
        Parola/kod algilama dosya adina uygulanmaz (ek adi parola sanilip degistirilmez)."""
        if real in self.media:
            return self.media[real]
        stem, ext = os.path.splitext(real)
        flat = re.sub(r"[_\-.]+", " ", stem)
        if self.text(flat, title=True, cred=False) == flat and self.text(stem, title=True, cred=False) == stem:
            return real
        self.media[real] = f"medya-{len(self.media) + 1}{ext}"
        return self.media[real]


def redact_console(args):
    """Anonim modda konsola gercek ad / girdi adi / mesaj icerigi hicbir kosulda yazilmaz (tani icin --no-anonim)."""
    return bool(getattr(args, "anonim", True))


def safe_error(e):
    """Icerik/ad tasimayan hata aciklamasi (OSError mesajlari dosya adi, JSON hatalari metin tasiyabilir)."""
    if isinstance(e, json.JSONDecodeError):
        return t("json_error", line=e.lineno, col=e.colno)
    return type(e).__name__


# ---------------------------------------------------------------- cikti
def message_parts(m):
    """Mesaj -> [(kind, val)]. kind: text | file | omitted | quote | note.
    Telefon disa aktarimi ham satirlar verir (lines); web kaziyici hazir parcalar (parts)."""
    if "parts" in m:
        return list(m["parts"])
    parts = []
    for line in m["lines"]:
        parts.extend(split_line(line))
    return parts


# ---- ekler: tur ve kopyalama politikasi (anonim modda anonimlestirilemeyen belge turleri varsayilan kopyalanmaz)
_KINDS = [("görüntü", {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".bmp"}),
          ("video", {".mp4", ".3gp", ".mov", ".mkv", ".avi", ".webm"}),
          ("ses", {".opus", ".ogg", ".mp3", ".m4a", ".aac", ".wav", ".amr"}),
          ("kişi kartı", {".vcf"}),
          ("PDF", {".pdf"}),
          ("ofis belgesi", {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf", ".csv",
                            ".txt", ".pages", ".numbers", ".key"}),
          ("arşiv", {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"})]
COPY_KINDS = {"görüntü", "video", "ses"}   # anonim modda varsayilan yalniz bunlar kopyalanir (izin listesi); digerleri
#                                            (kisi karti, PDF, ofis, arsiv, bilinmeyen/uzantisiz) --belgeleri-kopyala ile
_FILE_EXT = set().union(*(exts for _, exts in _KINDS))
_TITLE_LINE = re.compile(r"\S.{0,200}\.[A-Za-z0-9]{2,5}$")      # ek basligi / dosya adi satiri


def media_kind(name):
    ext = os.path.splitext(name)[1].lower()
    return next((k for k, exts in _KINDS if ext in exts), "diğer")


def is_title_line(val, file_names):
    """Metin satiri dosya basligi mi (parola algilama uygulanmaz). file_names: mesajin eklerinin adlari (yoksa bos).
    Baslik: ekin dosya adinin ta kendisi; ':'/'=' icermeyen, bilinen uzantili dosya adi olup (a) yalniz kucuk harfli
    siradan sozcuklerden olusan en az iki sozcuklu ad ('şifre listesi.pdf') ya da (b) ekli mesajda tek sozcuklu ad
    (belgenin ozgun adi) ya da parola anahtar kelimesi icermeyen ad. Ekli olmayan mesajda tek sozcuklu satir
    ('Kartal.zip') ve anahtar kelime + rakam/buyuk harf/simge iceren ad ('şifre Kartal2024.docx') baslik sayilmaz:
    parola kurallari uygulanir. Kucuk harfli tek sozcuk parolayi parola kurallari zaten maskelemez ('şifre kartal');
    uzantili hali de ayni kalir. Ekli mesajda anahtar kelimeli satirin ardindaki tek sozcuk Anonymizer.text'te maskelenir."""
    v = nfc(val.strip())
    if v in file_names or os.path.basename(v.replace("\\", "/")) in file_names:
        return True
    if ":" in v or "=" in v:            # 'şifre: x', 'pin=1234': deger satiri; 'şifre listesi.pdf' ise dosya adi
        return False
    if not _TITLE_LINE.fullmatch(v) or os.path.splitext(v)[1].lower() not in _FILE_EXT:
        return False
    words = os.path.splitext(v)[0].split()
    if len(words) == 1:
        return bool(file_names)
    return all(w.isalpha() and w.islower() for w in words) or (bool(file_names) and not _KW_ANY.search(v))


def render(title, msgs, export, media_dir_name="media", anon=None, no_media=False, copy_docs=False, manifest=None):
    """-> (md_text, set(referenced existing files), missing_count). anon: Anonymizer veya None.
    manifest (dict) verilirse her ek icin gosterilen ad -> (tur, durum) doldurulur."""
    T = (lambda x, m=None, **kw: anon.text(x, m, count=True, **kw)) if anon else (lambda x, m=None, **kw: x)
    used, missing = {}, 0
    manifest = {} if manifest is None else manifest
    out = []
    people = []
    for m in msgs:
        if m["sender"] and m["sender"] not in people:
            people.append(m["sender"])
    real = [m for m in msgs if m["sender"]]
    if anon:
        title, people = anon.code, [anon.sender(p) for p in people]
    out.append(f"# {title}\n")
    out.append(f"- Katılımcılar: {', '.join(people) if people else '-'}")
    out.append(f"- Mesaj sayısı: {len(real)}")
    if msgs:
        out.append(f"- Tarih aralığı: {msgs[0]['dt']:%Y-%m-%d} – {msgs[-1]['dt']:%Y-%m-%d}")
    out.append("")
    day = None
    for m in msgs:
        d = m["dt"].date()
        if d != day:
            day = d
            out.append(f"## {d:%Y-%m-%d}\n")
        rendered = []
        quoted = []  # index of rendered items that are quotes
        parts = message_parts(m)
        files = {nfc(v.strip()) for k, v in parts if k == "file" and v}
        files |= {os.path.basename(v.replace("\\", "/")) for v in files}
        sysline = m["sender"] is None      # sistem satiri: sohbet adi da maskelenir (konu degisti, grubu olusturdu)
        for kind, val in parts:
            if kind == "text":
                ttl = is_title_line(val, files)   # ek basligi ya da siradan sozcuklu dosya adi: parola sanilmaz
                rendered.append(T(val, m, title=sysline or ttl, cred=not ttl))
            elif kind == "quote":
                quoted.append(len(rendered))
                rendered.append("\n".join("> " + l for l in T(val).split("\n")))
            elif kind == "note":
                rendered.append(f"_{T(val, title=sysline)}_")
            elif kind == "omitted":
                rendered.append("_(medya dahil edilmemiş)_")
            else:
                real_name = export.find(val) if export is not None else None
                if no_media:
                    shown = ((anon.media_name(real_name) if anon else real_name) if real_name
                             else (anon.media_name(os.path.basename(val.replace("\\", "/"))) if anon else val))
                    manifest.setdefault(shown, (media_kind(val), "kopyalanmadı (--medya-yok)"))
                    rendered.append("_(medya dahil edilmemiş)_")
                    continue
                if real_name is None:      # eksik ek: adi var olan medyayla ayni kuralla notr (medya-N) olur
                    missing += 1
                    shown = anon.media_name(os.path.basename(val.replace("\\", "/"))) if anon else val
                    manifest.setdefault(shown, (media_kind(val), "eksik (dışa aktarımda yok)"))
                    rendered.append(f"_(dosya eksik: {shown})_")
                    continue
                shown = anon.media_name(real_name) if anon else real_name
                kind_ = media_kind(real_name)
                if anon and kind_ not in COPY_KINDS and not copy_docs:
                    manifest.setdefault(shown, (kind_, "kopyalanmadı (kişisel veri içerebilir; --belgeleri-kopyala)"))
                    rendered.append(f"_(ek kopyalanmadı: {shown}, {kind_})_")
                else:
                    used[real_name] = True
                    manifest.setdefault(shown, (kind_, "kopyalandı, elle kontrol gerekli"))
                    url = f"{media_dir_name}/{quote(shown)}"
                    if os.path.splitext(real_name)[1].lower() in IMAGE_EXT:
                        rendered.append(f"![]({url})")
                    else:
                        rendered.append(f"[{shown}]({url})")
        if m["sender"] is None:
            out.append(f"_{m['dt']:%H:%M} – {' '.join(r for r in rendered)}_\n")
        else:
            out.append(f"**{anon.sender(m['sender']) if anon else m['sender']}** {m['dt']:%H:%M}")
            if rendered:
                out.append(join_rendered(rendered, quoted))
            out.append("")
    return "\n".join(out), list(used), missing


def join_rendered(rendered, quoted):
    """Parcalari birlestirir; alinti blogundan sonra bos satir (yoksa sonraki satir alintiya yapisir)."""
    out = rendered[0]
    for i in range(1, len(rendered)):
        out += ("\n\n" if (i - 1) in quoted else "  \n") + rendered[i]
    return out


def copy_media(export, names, dest, rename=None):
    os.makedirs(dest, exist_ok=True)
    copied = 0
    for n in names:
        size, opener = export.files[n]
        target = os.path.join(dest, rename(n) if rename else n)
        if os.path.isfile(target) and os.path.getsize(target) == size:
            continue
        with opener() as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        copied += 1
    return copied


def process(export, out_dir, args, chat_no=1, ref=None):
    ref = ref or t("ref_input", n=1)
    txt_stem = os.path.splitext(export.txt_name)[0]
    base = export.label if txt_stem.lower() == "_chat" else txt_stem
    chat = args.name or derive_name(base) or derive_name(export.label)
    if args.only:
        needles = [x.strip().lower() for x in args.only.split(",") if x.strip()]
        if not any(n in chat.lower() for n in needles):
            return None
    red = redact_console(args)
    who = ref if red else chat
    msgs, unparsed = parse(decode(export.txt_bytes))
    if not msgs:
        if red:  # yalniz sayi; ayrintili tani icin --no-anonim
            print(f"{t('err')} [{who}]: " + t("no_messages_count", n=len(unparsed)), file=sys.stderr)
            return False
        print(f"{t('err')} [{who}]: " + t("no_messages_lines"), file=sys.stderr)
        for l in unparsed[:3]:
            print(f"   > {l}", file=sys.stderr)
        if not unparsed:
            print(t("file_empty"), file=sys.stderr)
        return False
    group = is_group(msgs, chat)          # TUM dosyadan, tarih suzgecinden ONCE: --from olaylari/karsi tarafi disarida biraksa da
    msgs = mark_system_lines(chat, msgs, group)
    if args.date_from:
        msgs = [m for m in msgs if m["dt"].date() >= args.date_from]
    if args.date_to:
        msgs = [m for m in msgs if m["dt"].date() <= args.date_to]
    if not msgs:
        print(f"{t('warn')} [{who}]: " + t("empty_range"), file=sys.stderr)
        return False
    write_chat(chat, msgs, export, out_dir, anonim=getattr(args, "anonim", True), chat_no=chat_no,
               label=args.name, no_media=getattr(args, "no_media", False),
               copy_docs=getattr(args, "copy_docs", False), extra_names=getattr(args, "extra_names", None),
               group=group, review_dir=getattr(args, "review_dir", None), no_dict=getattr(args, "no_dict", False))
    return True


REVIEW_DIR = "_inceleme"      # eski konum (<out>/_inceleme); artik varsayilan kullanici durum klasoru, bkz. default_review_dir
_STAT_ORDER = ["gönderen", "sistem satırı", "ek ad", "sözlük", "hitap", "anma", "sohbet adı", "telefon", "e-posta",
               "kullanıcı adı", "iban", "tckn", "plaka", "parola", "kod", "yer/kurum belirsiz"]
_RUN_STAMP = []


def _count_line(stats):
    return ", ".join(f"{t_stat(k)} {stats[k]}" for k in [*_STAT_ORDER, *sorted(set(stats) - set(_STAT_ORDER))] if stats.get(k))


def state_dir():
    """Kullanici duzeyi durum klasoru (paylasilan/commit edilen ciktinin DISINDA): Windows %LOCALAPPDATA%\\wa2md,
    macOS ~/Library/Application Support/wa2md, digerleri ~/.local/state/wa2md; $XDG_STATE_HOME verilmisse her yerde o."""
    if os.environ.get("XDG_STATE_HOME"):
        base = os.environ["XDG_STATE_HOME"]
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "wa2md")


def default_review_dir(out_dir):
    """<durum>/inceleme/<calisma-zamani>-<cikti yolunun kisa ozeti>: her calisma ayri klasor (Sohbet-N konuma bagli)."""
    if not _RUN_STAMP:
        _RUN_STAMP.append(dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    h = hashlib.sha256(os.path.abspath(out_dir).encode("utf-8")).hexdigest()[:8]
    return os.path.join(state_dir(), "inceleme", f"{_RUN_STAMP[0]}-{h}")


def git_work_tree(path):
    """path (henuz yoksa bile) bir git calisma agacinin icindeyse o agacin koku, degilse None. Hem gercek yol
    (realpath: sembolik baglar cozulur, ornegin depoya isaret eden bag) hem mutlak yolun ust zinciri denetlenir."""
    for p in dict.fromkeys((os.path.realpath(path), os.path.abspath(path))):
        while True:
            if os.path.exists(os.path.join(p, ".git")):
                return p
            up = os.path.dirname(p)
            if up == p:
                break
            p = up
    return None


def writable_dir(path):
    """Klasor olusturulabilir ve icine yazilabilir mi (deneme dosyasiyla; sinama icin olusturulan bos klasorler geri
    silinir). -> None ya da hata turu (ad tasimaz)."""
    p = os.path.abspath(path)
    made, q = [], p
    while not os.path.isdir(q):
        made.append(q)
        up = os.path.dirname(q)
        if up == q:
            break
        q = up
    try:
        os.makedirs(p, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=p, prefix=".wa2md-yazma-sinamasi-"):
            pass
        return None
    except OSError as e:
        return type(e).__name__
    finally:
        for d in made:                    # en derinden yukari; yalniz bossa
            try:
                os.rmdir(d)
            except OSError:
                break


def anonim_preflight(args, out_dir):
    """Anonim calistirmanin on denetimi, HICBIR cikti yazilmadan once (wa2md ve wa_web ayni yol): ad sozlugu var mi
    (yoksa --sozluksuz gerekir), inceleme klasoru git calisma agacinin disinda ve yazilabilir mi. args.review_dir
    verilmemisse varsayilan konum atanir. -> None (devam) ya da cikis kodu 2 (Turkce mesaj stderr'de)."""
    miss = missing_name_lists()
    if miss and not getattr(args, "no_dict", False):
        print(f"{t('err')}: " + t("dict_missing", names=", ".join(miss), path=os.path.join(_HERE, "adlar")),
              file=sys.stderr)
        return 2
    args.review_dir = getattr(args, "review_dir", None) or default_review_dir(out_dir)
    if git_work_tree(args.review_dir):
        print(f"{t('err')}: " + t("review_in_git", path=args.review_dir), file=sys.stderr)
        return 2
    err = writable_dir(args.review_dir)
    if err:
        print(f"{t('err')}: " + t("review_unwritable", path=args.review_dir, err=err), file=sys.stderr)
        return 2
    return None


def write_manifest(folder, manifest):
    """Sohbet-N/ekler.md: her ek (anonim ad), turu ve durumu. -> (kopyalanan Counter, kopyalanmayan Counter)."""
    copied, skipped = {}, {}
    lines = ["# Ekler", "",
             "Her ekin durumu. **Kopyalanan her dosya elle kontrol edilmeli**: görüntü/video/ses içeriği (yüzler, ekran "
             "görüntüleri, sesler, belgelerdeki adlar) anonimleştirilmez.", "",
             "| Dosya | Tür | Durum |", "|---|---|---|"]
    for shown, (kind, status) in manifest.items():
        lines.append(f"| {shown.replace('|', '/')} | {kind} | {status} |")
        d = copied if status.startswith("kopyalandı") else skipped
        d[kind] = d.get(kind, 0) + 1
    with open(os.path.join(folder, "ekler.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return copied, skipped


def write_review(review_dir, shown, review):
    """<review_dir>/<Sohbet-N>-supheli-adlar.txt: maskelenmeden kalan, ad olabilecek sozcukler (yalniz operator icin).
    review_dir varsayilan olarak cikti klasorunun disinda (default_review_dir); git agacinin icine yazilmaz."""
    if git_work_tree(review_dir):
        raise RuntimeError(t("review_in_git_exc"))
    path = os.path.join(review_dir, sanitize(shown) + "-supheli-adlar.txt")
    if not review:
        if os.path.isfile(path):
            os.remove(path)
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prio = {"hitap": 0, "büyük": 1, "küçük": 2}
    rows = sorted(review.values(), key=lambda r: (prio.get(r[2], 3), -r[1], _key(r[0])))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(t("review_head", shown=shown))
        for word, n, why, ex in rows:
            reason = t("why_" + why) if why in prio else why
            f.write(f"{word}\t{n}\t{reason}\t" + " | ".join(e.replace("\t", " ") for e in ex) + "\n")
    return path


def write_chat(chat, msgs, export, out_dir, anonim=False, chat_no=1, label=None, no_media=False, copy_docs=False,
               extra_names=None, group=None, review_dir=None, no_dict=False):
    """Tek Markdown yazici: <out>/<chat>/<chat>.md + media/ + ekler.md. Telefon ve web yolu burayi kullanir.
    anonim=True: Anonymizer uygulanir, klasor/dosya 'Sohbet-<chat_no>' (label verilirse o); CLI'lar varsayilan True verir.
    Anonim modda gercek ad<->etiket iliskisi hicbir yere (dosya, konsol, log) yazilmaz; anonimlestirilemeyen belge
    turleri (COPY_KINDS disi) copy_docs olmadan kopyalanmaz; supheli kalan sozcukler review_dir'e (varsayilan:
    kullanici durum klasoru, cikti klasorunun disi) yazilir. Ad sozlugu (adlar/) yoksa no_dict olmadan hata.
    group: grup sohbeti mi (None: msgs'ten). -> (md_path, mesaj_sayisi, kopyalanan_medya, eksik_medya)"""
    msgs = mark_system_lines(chat, msgs, group)
    if anonim and missing_name_lists() and not no_dict:
        raise RuntimeError(t("dict_missing_exc"))
    anon = Anonymizer(chat, msgs, chat_no, label, extra=extra_names, group=group) if anonim else None
    shown = anon.code if anon else chat
    folder = os.path.join(out_dir, sanitize(shown))
    os.makedirs(folder, exist_ok=True)
    manifest = {}
    md, used, missing = render(chat, msgs, export, anon=anon, no_media=no_media, copy_docs=copy_docs, manifest=manifest)
    copied = copy_media(export, used, os.path.join(folder, "media"), anon.media_name if anon else None) if used else 0
    md_path = os.path.join(folder, sanitize(shown) + ".md")
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    real = sum(1 for m in msgs if m["sender"])
    print(t("summary", shown=shown, real=real, copied=copied, missing=missing, path=md_path))
    if manifest:
        c, sk = write_manifest(folder, manifest)
        fmt = lambda d: ", ".join(f"{k} {v}" for k, v in sorted(d.items(), key=lambda x: -x[1])) or "-"
        print(t("attach_warn", c=sum(c.values()), cd=fmt(c), s=sum(sk.values()), sd=fmt(sk),
                path=os.path.join(folder, "ekler.md")))
    if anon:
        if copied:
            print(t("media_warn", n=copied))
        print(t("masked", counts=_count_line(anon.stats) or "-"))
        if missing_name_lists():
            print(t("no_dict_warn"))
        path = write_review(review_dir or default_review_dir(out_dir), shown, anon.review)
        if path:
            first = sum(1 for r in anon.review.values() if r[2] != "küçük")
            print(t("review_summary", n=len(anon.review), first=first,
                    passes=sum(r[1] for r in anon.review.values()), path=path))
        else:
            print(t("review_zero"))
        print("   " + t("limit_note"))
    return md_path, real, copied, missing


def add_anonim_args(p):
    # English names are primary; the Turkish names are accepted aliases with identical behaviour (same dest, same default).
    # dest stays "anonim": it is an internal key read by wa2md.py, wa_web.py and the tests.
    p.add_argument("--anonymize", "--anonim", dest="anonim", action=argparse.BooleanOptionalAction, default=True,
                   help=t("help_anonymize"))
    p.add_argument("--extra-names", "--ek-adlar", dest="extra_names", type=parse_names, help=t("help_extra_names"))
    p.add_argument("--review-dir", "--inceleme-dizini", dest="review_dir", help=t("help_review_dir"))
    p.add_argument("--no-dictionary", "--sozluksuz", dest="no_dict", action="store_true", help=t("help_no_dict"))


def parse_names(s):
    """'Ad Soyad,Ad2' veya '@dosya' (satir basina bir ad, # aciklama) -> [ad]."""
    if s.startswith("@"):
        try:
            with open(s[1:], encoding="utf-8-sig") as f:
                items = [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
        except OSError as e:
            raise argparse.ArgumentTypeError(t("names_unreadable", kind=type(e).__name__))
    else:
        items = [x.strip() for x in s.split(",") if x.strip()]
    return [nfc(x) for x in items]


def parse_date(s):
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(t("bad_date", value=s))


def build_parser():
    ap = argparse.ArgumentParser(description=t("help_description"))
    ap.add_argument("inputs", nargs="+", help=t("help_inputs"))
    ap.add_argument("--out", required=True, help=t("help_out"))
    ap.add_argument("--only", help=t("help_only"))
    ap.add_argument("--from", dest="date_from", type=parse_date, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", type=parse_date, help="YYYY-MM-DD")
    ap.add_argument("--name", help=t("help_name"))
    ap.add_argument("--no-media", "--medya-yok", dest="no_media", action="store_true", help=t("help_no_media"))
    ap.add_argument("--copy-documents", "--belgeleri-kopyala", dest="copy_docs", action="store_true",
                    help=t("help_copy_documents"))
    add_anonim_args(ap)
    add_lang_arg(ap)
    return ap


def main(argv=None):
    try:
        return _main(argv)
    finally:
        reset_lang()


def _main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    init_lang(argv)
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.anonim:
        rc = anonim_preflight(args, args.out)
        if rc:
            return rc

    try:
        items = discover(args.inputs)
    except (FileNotFoundError, ValueError) as e:
        print(f"{t('err')}: {e}", file=sys.stderr)
        return 2
    done = failed = 0
    red = redact_console(args)
    for idx, (kind, path) in enumerate(items, 1):
        ref = t("ref_input", n=idx)
        try:
            export = load_zip(path) if kind == "zip" else load_dir(path)
            r = process(export, args.out, args, done + 1, ref)
        except zipfile.BadZipFile:
            print(f"{t('err')}: " + t("not_a_zip", who=ref if red else repr(path)), file=sys.stderr)
            failed += 1
            continue
        except ValueError as e:
            print(f"{t('err')}: {ref + ': ' + t('no_chat_in_input') if red else e}", file=sys.stderr)
            failed += 1
            continue
        except Exception as e:  # noqa: BLE001 - anonimde iz/yol (ad icerir) yerine yalniz tur
            if not red:
                raise
            print(f"{t('err')} [{ref}]: " + t("unexpected", kind=type(e).__name__), file=sys.stderr)
            failed += 1
            continue
        if r is True:
            done += 1
        elif r is False:
            failed += 1
    if done == 0 and failed == 0:
        print(t("no_match"), file=sys.stderr)
        return 1
    return 1 if failed and not done else 0


if __name__ == "__main__":
    sys.exit(main())
