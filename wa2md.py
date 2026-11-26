#!/usr/bin/env python3
"""Converts WhatsApp "Export chat" output (zip / folder) to Markdown and anonymizes it.

Python standard library only. Usage:
    python wa2md.py <input> [<input>...] --out <folder> [--only "a,b"] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--name NAME]
                    [--no-media] [--copy-documents] [--extra-names "A B,C" | @file] [--review-dir DIR] [--no-dictionary]
                    [--no-anonymize] [--lang en|tr]
Default: the output is anonymized (direct identifiers are removed, see Anonymizer); --no-anonymize writes real names.
The Turkish option names (--medya-yok, --belgeleri-kopyala, --ek-adlar, --inceleme-dizini, --sozluksuz, --anonim,
--no-anonim) are accepted aliases. Help and console messages are English; --lang tr or WA2MD_LANG=tr selects Turkish
(one table: MSG); the same switch selects the output labels (Chat-N, Person N, [phone] / Sohbet-N, Kişi N, [telefon]).
--packs auto|en|tr|en,tr (WA2MD_PACKS) selects the language packs used on the chat text; default auto (per chat).
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
import types
import unicodedata
import zipfile
from urllib.parse import quote

try:
    import wa2md_lang
except ImportError:     # run as a script in isolated mode (python -I wa2md.py): the package sits next to this file
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import wa2md_lang

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
    packs = None
    for i, a in enumerate(argv):
        if a == "--packs" and i + 1 < len(argv):
            packs = argv[i + 1]
        elif a.startswith("--packs="):
            packs = a[len("--packs="):]
    _PACKS[0] = _norm_packs(packs) or _norm_packs(env.get("WA2MD_PACKS")) or "auto"
    raw = (env.get("WA2MD_PACKS") or "").strip()
    _PACKS_ENV_BAD[0] = raw if packs is None and raw and _norm_packs(raw) is None else None
    return _LANG[0]


def check_packs_env(parser):
    """An invalid WA2MD_PACKS value (without --packs) is a usage error like an invalid --packs (exit code 2)."""
    if _PACKS_ENV_BAD[0] is not None:
        parser.error(t("bad_packs_env", value=_PACKS_ENV_BAD[0], packs=",".join(wa2md_lang.PACKS)))


def reset_lang():
    """End of a main() call: library-style calls (import_bundles, write_chat, ...) follow WA2MD_LANG again."""
    _LANG[0] = None
    _PACKS[0] = None


def current_lang():
    return _LANG[0] or _norm_lang(os.environ.get("WA2MD_LANG")) or "en"


def _packs_arg(value):
    if _norm_packs(value) is None:
        raise argparse.ArgumentTypeError(t("bad_packs", value=value, packs=",".join(wa2md_lang.PACKS)))
    return value


def add_lang_arg(p):
    """--lang and --packs on the top-level parser and on every sub-command (SUPPRESS: a sub-command never overwrites
    the value; init_lang() reads both from argv before the parser runs)."""
    p.add_argument("--lang", type=str.lower, choices=LANGS, default=argparse.SUPPRESS, metavar="{en,tr}",
                   help=t("help_lang"))
    p.add_argument("--packs", type=_packs_arg, default=argparse.SUPPRESS, metavar="auto|en|tr|en,tr",
                   help=t("help_packs"))


def t(key, **kw):
    """Message text in the selected language; {placeholders} are filled from kw."""
    text = MSG[key][current_lang()]
    return text.format(**kw) if kw else text


def t_stat(cat):
    """Display name of an internal statistics category (internal ids are English and language-neutral)."""
    return STAT_LABEL.get(cat, {}).get(current_lang(), cat)


# internal statistics / origin id -> display name per message language
STAT_LABEL = {
    "sender": {"en": "sender", "tr": "gönderen"}, "system_line": {"en": "system line", "tr": "sistem satırı"},
    "extra_name": {"en": "extra name", "tr": "ek ad"}, "dictionary": {"en": "dictionary", "tr": "sözlük"},
    "honorific": {"en": "honorific", "tr": "hitap"}, "mention": {"en": "mention", "tr": "anma"},
    "contact": {"en": "contact", "tr": "iletişim"}, "signature": {"en": "signature", "tr": "imza"},
    "company": {"en": "company", "tr": "firma"}, "chat_name": {"en": "chat name", "tr": "sohbet adı"},
    "phone": {"en": "phone", "tr": "telefon"}, "email": {"en": "e-mail", "tr": "e-posta"},
    "username": {"en": "username", "tr": "kullanıcı adı"}, "iban": {"en": "iban", "tr": "iban"},
    "national_id": {"en": "national id", "tr": "tckn"}, "plate": {"en": "plate", "tr": "plaka"},
    "password": {"en": "password", "tr": "parola"}, "code": {"en": "code", "tr": "kod"},
    "place_unclear": {"en": "place/institution unclear", "tr": "yer/kurum belirsiz"}}

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
    "bad_packs": {"en": "Invalid --packs value '{value}' (auto or a list of: {packs})",
                  "tr": "Geçersiz --packs değeri '{value}' (auto ya da şunların listesi: {packs})"},
    "bad_packs_env": {"en": "Invalid WA2MD_PACKS value '{value}' (auto or a list of: {packs})",
                      "tr": "Geçersiz WA2MD_PACKS değeri '{value}' (auto ya da şunların listesi: {packs})"},
    # ---- per-chat summary (stdout) ----
    "summary": {"en": "[{shown}] {real} messages, {copied} media copied, {missing} media missing -> {path}",
                "tr": "[{shown}] {real} mesaj, {copied} medya kopyalandı, {missing} medya eksik -> {path}"},
    "packs_auto": {"en": "   Language packs (auto, from the chat text): {codes} - {n} of {total}",
                   "tr": "   Dil paketleri (otomatik, sohbet metninden): {codes} - {total} paketten {n}"},
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
    "why_honorific": {"en": "before an honorific, not in the dictionary (sentence start) - look at this first",
                  "tr": "hitaptan önce, sözlükte yok (cümle başı) - önce buna bak"},
    "why_capitalized": {"en": "name that is also an ordinary word, capitalized (sentence start) - look at this first",
                  "tr": "sözcük anlamı da olan ad, büyük harfle (cümle başı) - önce buna bak"},
    "why_lowercase": {"en": "name that is also an ordinary word, lower case (mostly ordinary words)",
                  "tr": "sözcük anlamı da olan ad, küçük harfle (çoğu sıradan sözcük)"},
    # ---- wa_web.py ----
    "web_not_bundle": {"en": "bundle part {no} is not a wa-web-bundle file.",
                       "tr": "paket parçası {no} bir wa-web-bundle dosyası değil."},
    "web_no_final": {"en": "Final bundle part not found: the collection may have been cut short.",
                     "tr": "Son paket (final) bulunamadı: toplama yarıda kesilmiş olabilir."},
    "web_missing_parts": {"en": "Missing bundle part(s): {parts}", "tr": "Eksik paket parçası: {parts}"},
    "web_incomplete": {"en": "   Note: the collection did not finish; the newest checkpoint (part {no}) was used, messages "
                             "collected after it are missing.",
                       "tr": "   Not: toplama bitmedi; en yeni ara kayıt (parça {no}) kullanıldı, ondan sonra toplanan "
                             "mesajlar eksik."},
    "web_stopped": {"en": "   Note: the collection was stopped early; older messages are not included.",
                    "tr": "   Not: toplama erken durduruldu; daha eski mesajlar dahil değil."},
    "web_seal_no_key": {"en": "the key of these sealed bundles is not in the user state folder (bundles from another computer "
                               "or user, or the key was already used and deleted).",
                        "tr": "bu mühürlü paketlerin anahtarı kullanıcı durum klasöründe yok (başka bilgisayarın ya da "
                              "kullanıcının paketleri, ya da anahtar kullanılıp silinmiş)."},
    "web_seal_bad": {"en": "sealed bundle part {no} failed the integrity check (damaged file or wrong key).",
                     "tr": "mühürlü paket parçası {no} bütünlük denetimini geçemedi (bozuk dosya ya da yanlış anahtar)."},
    "web_key_kept": {"en": "   Key kept: {done} of {total} sessions of this run are imported; the key is deleted when the last one is.",
                     "tr": "   Anahtar duruyor: bu koşunun {total} oturumundan {done} tanesi içe aktarıldı; sonuncusunda anahtar silinir."},
    "web_key_kept_bundles": {"en": "   Key kept: sealed bundle files of this run that were not converted are still in the input; "
                                   "the key is deleted when they are.",
                             "tr": "   Anahtar duruyor: bu koşunun dönüştürülmemiş mühürlü paket dosyaları girdide duruyor; "
                                   "onlar dönüşünce anahtar silinir."},
    "web_seal_format": {"en": "sealed bundle part {no} uses the seal format {alg}, which this version does not read (it is not a "
                              "damaged file); import it with the version of wa2md that wrote it.",
                        "tr": "mühürlü paket parçası {no} bu sürümün okumadığı mühür biçimini ({alg}) kullanıyor (bozuk dosya "
                              "değil); onu yazan wa2md sürümüyle içe aktarın."},
    "web_deleted": {"en": "   {n} converted bundle file(s) deleted (--keep-bundles keeps them).",
                    "tr": "   Dönüştürülen {n} paket dosyası silindi (--keep-bundles saklar)."},
    "web_parts_kept": {"en": "   The collection has no final part: the bundle files stay where they are; import them "
                             "again together with the final part if it turns up.",
                       "tr": "   Toplamanın son parçası yok: paket dosyaları yerinde kalır; son parça bulunursa "
                             "onunla birlikte yeniden içe aktarın."},
    "web_salvage": {"en": "   The collection did not finish: converting what was collected (checkpoints).",
                    "tr": "   Toplama bitmedi: toplananlar (ara kayıtlar) dönüştürülüyor."},
    "web_parts_left": {"en": "   Bundle parts that could not be converted are kept in {path}. They cannot be imported later: "
                             "the key of an `export` run lives only in memory, so the chat text in them (encrypted) can no "
                             "longer be opened; parts without text hold photos only. Delete the folder when you do not need them.",
                       "tr": "   Dönüştürülemeyen paket parçaları {path} klasöründe duruyor. Sonradan içe aktarılamazlar: "
                             "`export` koşusunun anahtarı yalnız bellekte durur, içlerindeki (şifreli) sohbet metni artık "
                             "açılamaz; metinsiz parçalar yalnız fotoğraf içerir. Gerekmiyorsa klasörü silin."},
    "web_run_stopped": {"en": "Stopped by the user: {n} remaining chat(s) were not collected.",
                        "tr": "Kullanıcı durdurdu: kalan {n} sohbet toplanmadı."},
    "web_delete_failed": {"en": "   {n} bundle file(s) could not be deleted; delete them by hand (they hold the unmasked chat).",
                          "tr": "   {n} paket dosyası silinemedi; elle silin (maskelenmemiş sohbeti içerir)."},
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
    "help_lang": {"en": "language of help, console messages and the labels written into the output (Chat-N, Person N, "
                        "[phone] / Sohbet-N, Kişi N, [telefon]); default: English; environment variable WA2MD_LANG",
                  "tr": "yardım, konsol iletileri ve çıktıya yazılan etiketlerin dili (Chat-N, Person N, [phone] / "
                        "Sohbet-N, Kişi N, [telefon]); varsayılan: İngilizce; ortam değişkeni WA2MD_LANG"},
    "help_packs": {"en": "language packs used to find names in the chat text: auto (default: chosen per chat from its "
                         "messages), or a list such as en, tr, en,tr; environment variable WA2MD_PACKS",
                   "tr": "sohbet metninde ad aramak için dil paketleri: auto (varsayılan: her sohbet için mesajlarından "
                         "seçilir) ya da en, tr, en,tr gibi bir liste; ortam değişkeni WA2MD_PACKS"},
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
                             "Person names become 'Person N', chat/folder/file name 'Chat-N' (N: position in this run), "
                             "phone -> [phone], e-mail -> [email], IBAN -> [iban], national ID -> [national-id], plate -> "
                             "[plate], trade name (a distinctive name before a sector word such as haulage/freight/logistics "
                             "or before a legal form such as Ltd/Limited/Inc/LLC; see docs/anonymization.md) and sector domain name -> "
                             "[company], the path of a link with a masked domain -> [path]; participant "
                             "names (senders and the people in system lines; full name, a first name alone when unambiguous, "
                             "inflected forms like \"Naime'ye\"), names found in the name dictionary, with an honorific, in a "
                             "contact field or next to a phone are masked in message text too; the chat name only in the "
                             "title, in system lines and in file names. The real name <-> label mapping is written nowhere "
                             "(file, console). This mode is 'removal of direct identifiers'; in the legal sense (for example under the "
                             "Turkish KVKK) it does NOT count as anonymous while content that identifies people remains in the "
                             "text/photos or while the original chat exists: names of non-participants, photo content (faces, "
                             "screenshots, documents; use --no-media if you will share), exact timestamps, places and writing "
                             "style can still identify a person. The labels follow --lang (English by default; Turkish "
                             "labels Kişi N, Sohbet-N, [telefon] ... with --lang tr; see docs/language-support.md)",
                       "tr": "anonimleştirme (doğrudan tanımlayıcıların kaldırılması); varsayılan AÇIK, kapatmak için "
                             "--no-anonim. Kişi adları 'Kişi N', sohbet/klasör/dosya adı 'Sohbet-N' (N: bu çalıştırmadaki "
                             "sıra), telefon -> [telefon], e-posta -> [e-posta], IBAN -> [iban], T.C. kimlik no -> [tckn], "
                             "plaka -> [plaka], ticari ad (nakliyat/nakliye/lojistik/taşımacılık önündeki ad ya da "
                             "Ltd./Şti./A.Ş. biçimli ad, ilan imi gerekmeden; kargo/transport/şirketi ile kurulan ad ve küçük "
                             "harfli ad yalnız telefonlu ya da iletişim alanlı ilan mesajında; dışlananlar: genel niteleme "
                             "listesi ve ilan sözlüğü, yalnız yer adı, hitap öbeği; bkz. docs/tr/anonymization.md) ve nakliye alan adı -> "
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
    "help_web_no_video": {"en": "do not open, play or download video, gif or audio messages (no sound); they are written as "
                                "\"[video: not exported]\"; photos are taken only when already loaded in the chat or by their "
                                "download button (the media viewer is not opened)",
                          "tr": "video, gif ve ses mesajlarını açma, oynatma, indirme (ses çıkmaz); \"[video: aktarılmadı]\" "
                                "olarak yazılır; fotoğraflar yalnız sohbette yüklüyse ya da indirme düğmesiyle alınır "
                                "(medya görüntüleyici açılmaz)"},
    "help_web_import_no_media": {"en": "leave media out of the output (photos in the bundle are not copied); photos are not "
                                       "anonymized (faces, screenshots, documents), recommended for output you will share",
                                 "tr": "medyayı çıktıya koyma (paketteki fotoğraflar kopyalanmaz); fotoğraflar anonimleştirilmez "
                                       "(yüzler, ekran görüntüleri, belgeler), paylaşılacak çıktı için önerilir"},
    "help_keep_bundles": {"en": "keep the bundle files after a successful conversion (default: they are deleted, "
                                "because they hold the unmasked chat)",
                          "tr": "başarılı dönüştürmeden sonra paket dosyalarını sakla (varsayılan: silinir, çünkü "
                                "maskelenmemiş sohbeti içerirler)"},
    "help_checkpoint_minutes": {"en": "write a checkpoint part with all rows collected so far every N minutes "
                                      "(default 10, 0 = off); an unfinished collection can be imported from it",
                                "tr": "her N dakikada bir o ana kadar toplanan tüm satırlarla bir ara kayıt parçası yaz "
                                      "(varsayılan 10, 0 = kapalı); bitmemiş bir toplama ondan içe aktarılabilir"},
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


# ---------------------------------------------------------------- language pack
# wa2md_lang is the ONE source of words, language-specific patterns and output labels (see docs/language-packs.md).
# Every module-level value derived from the pack is built by a function registered with @_on_pack: it runs once at
# import with the default pack, and use_pack() re-runs all of them in registration order (the same code both times).
_P = wa2md_lang.load_pack(wa2md_lang.DEFAULT_PACK)     # active pack
_L = _P.labels                                         # its output labels
_BUILDERS = []


def _on_pack(fn):
    _BUILDERS.append(fn)
    fn()
    return fn


def active_pack():
    """The language pack set in use (wa_web reads its export words here; they are the same in every pack set)."""
    return _P


# ---------------------------------------------------------------- pack selection (per chat) and output labels
# ONE rule, applied by select_packs() for every chat (phone export and WhatsApp Web path):
#   packs  = --packs, else WA2MD_PACKS, else "auto": detect_packs() on the chat's own message texts;
#   labels = the label set of the message language (--lang, else WA2MD_LANG, else English), see output_labels().
# The export's own words (system lines, attachment markers) are always those of every shipped pack, whatever the
# selection: a Turkish chat exported from an English-language phone has English system lines and Turkish messages.
_PACKS = [None]     # set by init_lang() for one main() call; None = follow WA2MD_PACKS / auto
_PACKS_ENV_BAD = [None]     # invalid WA2MD_PACKS value seen by init_lang() (reported by check_packs_env)
_PINNED = [False]   # use_pack(<pack>) pins a pack for library callers and tests; use_pack(None) returns to select_packs
_ACTIVE_KEY = [None]


def _norm_packs(value):
    """'auto' -> 'auto'; 'tr', 'en,tr', 'EN TR' -> ('tr', 'en') (shipped order); unknown or empty -> None."""
    v = (value or "").strip().lower()
    if v == "auto":
        return "auto"
    codes = [c for c in re.split(r"[,+\s]+", v) if c]
    if not codes or any(c not in wa2md_lang.PACKS for c in codes):
        return None
    return tuple(c for c in wa2md_lang.PACKS if c in codes)


def current_packs():
    return _PACKS[0] or _norm_packs(os.environ.get("WA2MD_PACKS")) or "auto"


def output_labels():
    """The output label set: the pinned pack's labels, else the label set of the message language."""
    return _L if _PINNED[0] else wa2md_lang.load_pack(current_lang()).labels


_WORD = re.compile(r"\w+(?:['’]\w+)?")
_SEL_FLOOR = 0.10       # best score below this: no language signal, every pack (third languages, emoji, media)
_SEL_MIN, _SEL_REL = 0.04, 0.35     # a further pack: at least this score and this share of the best score
_DOM_SHARE, _DOM_MIN = 0.75, 6      # dominant language: wins >= 3/4 of at least 6 voting messages
_DOMINANT = [None]      # code of the pack whose language clearly dominates the current chat (select_packs), or None


def pack_scores(msgs, available=None):
    """Selection evidence of a chat, one pass over the word tokens of its own messages (system lines and media markers
    excluded). -> (scores, votes): scores[i] = share of the tokens that are a stopword of pack i or contain one of its
    language-only letters; votes[i] = messages in which pack i has more hits than every other pack (ties: no vote)."""
    packs = [wa2md_lang.load_pack(c) for c in tuple(available or wa2md_lang.PACKS)]
    hits, votes, total = [0] * len(packs), [0] * len(packs), 0
    for m in msgs:
        if not m.get("sender") or m.get("system"):
            continue
        text = "\n".join(m.get("lines") or [p[1] for p in m.get("parts") or () if p[0] == "text"])
        mh = [0] * len(packs)
        for w in _WORD.findall(text):
            lw = w.lower()
            total += 1
            for i, p in enumerate(packs):
                if lw in p.stopwords or (p.detect_chars and any(c in p.detect_chars for c in w)):
                    mh[i] += 1
        top = max(mh, default=0)
        if top and mh.count(top) == 1:
            votes[mh.index(top)] += 1
        hits = [a + b for a, b in zip(hits, mh)]
    return [h / total if total else 0.0 for h in hits], votes


def _choose(available, scores):
    best = max(scores, default=0.0)
    if best < _SEL_FLOOR:
        return available
    return tuple(c for c, sc in zip(available, scores) if sc >= _SEL_MIN and sc >= _SEL_REL * best) or available


def detect_packs(msgs, available=None):
    """Chat-text packs for a chat (the "auto" rule, scores: pack_scores). Best score below _SEL_FLOOR (no signal:
    very short, word-less or third-language chats): every pack (over-masking is the safe side). Otherwise every pack
    scoring at least _SEL_MIN and at least _SEL_REL x the best score. In memory only."""
    available = tuple(available or wa2md_lang.PACKS)
    return _choose(available, pack_scores(msgs, available)[0])


def _dominant(codes, votes):
    """The pack of codes whose language clearly dominates (message votes, see pack_scores), or None: a balanced or
    short chat. Only a pack set of several packs has one."""
    vs = [votes[wa2md_lang.PACKS.index(c)] for c in codes]
    total, top = sum(vs), max(vs, default=0)
    if len(codes) < 2 or total < _DOM_MIN or top < _DOM_SHARE * total:
        return None
    return codes[vs.index(top)]


def select_packs(msgs):
    """Apply the selection rule (see above) for one chat; rebuilds the pack-derived patterns only when the pack set or
    the label set changes. Sets _DOMINANT for the chat (also for a pinned pack set). -> the active pack set."""
    codes = tuple(_P.code.split("+")) if _PINNED[0] else current_packs()
    scores, votes = pack_scores(msgs) if codes == "auto" or len(codes) > 1 else ((), ())
    if not _PINNED[0]:
        codes = _choose(wa2md_lang.PACKS, scores) if codes == "auto" else codes
        key = (codes, current_lang())
        if key != _ACTIVE_KEY[0]:
            _activate(wa2md_lang.merge(codes, labels=key[1]))
            _ACTIVE_KEY[0] = key
    _DOMINANT[0] = _dominant(codes, votes) if votes else None
    return _P


def use_pack(pack):
    """Pin a language pack (code, LanguagePack, or a merged pack set) for the following runs, bypassing
    select_packs(); use_pack(None) removes the pin and returns to the import state (DEFAULT_PACK) until the next chat
    selects its packs. Rebuilds every pack-derived pattern, reloads the dictionaries, clears the caches."""
    if pack is None:
        _PINNED[0] = False
        _ACTIVE_KEY[0] = None
        return _activate(wa2md_lang.load_pack(wa2md_lang.DEFAULT_PACK))
    new = wa2md_lang.load_pack(pack) if isinstance(pack, str) else pack
    _activate(new)
    _PINNED[0] = True
    return _P


def _activate(new):
    global _P, _L
    wa2md_lang.check_pack(new)
    old = _P
    _P, _L = new, new.labels
    _LISTS.clear()
    try:
        for fn in _BUILDERS:
            fn()
    except Exception:                 # a pattern of the new pack does not compile: keep the previous pack
        _P, _L = old, old.labels
        for fn in _BUILDERS:
            fn()
        raise
    for f in (_key, _is_sector, _is_strong_sector, title_event_line, _loose, _ordinary):
        f.cache_clear()
    return _P


IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
# yon isaretleri ve BOM silinir. Sifir genislikli karakterler ve yumusak tire metinde kalir (main gibi; ad
# eslesmesinde sozcuk siniridir); telefon kalibi rakamlar arasindakileri atlar (_ZWP). Bolunmus adlar kapsam disi.
INVISIBLE = re.compile("[\u200e\u200f\u202a-\u202e\ufeff]")

DATE = r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})"


@_on_pack
def _build_export():
    """Export locale of the pack: time markers, attachment / omitted tokens, chat-name strip patterns."""
    global TIME, ANDROID_RE, IOS_RE, ATTACH_ANDROID, ATTACH_IOS, OMITTED, STRIP_NAME, _PM
    TIME = r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?(?:\s*(" + _P.ampm + "))?"
    ANDROID_RE = re.compile(r"^" + DATE + r",?\s+" + TIME + r"\s+-\s+(.*)$")
    IOS_RE = re.compile(r"^\[" + DATE + r",?\s+" + TIME + r"\]\s*(.*)$")
    ATTACH_ANDROID = re.compile(r"^(.+?)\s+\((?:" + _P.attach_android + r")\)\s*$", re.I)
    ATTACH_IOS = re.compile(r"<(?:" + _P.attach_ios + r"):\s*([^>]+?)\s*>", re.I)
    OMITTED = re.compile(r"^<?[^<>]{0,30}(?:" + _P.omitted + r")>?$", re.I)
    STRIP_NAME = list(_P.strip_name)
    _PM = re.compile(_P.pm)


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
        name = _L.chat_fallback
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
        pm = bool(_PM.match(ap.lower()))
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
# Telefon: ulusal bicimler dil paketinden (_P.phone_national: TR'de onekli 0/90/+90 numara, sabit kaliplar, sozcuge
# yapisik oneksiz cep, parantezli alan kodu); evrensel bicimler burada: 00 + 1-3 haneli ulke kodu + ayrac + 6-12 hane
# ('0049 151 ...', butun dizi; ayracsiz '0012345678' referans numarasi olabilir, degil) ve +<8-15 hane>. Onekli bicimler bir
# rakam + tireden sonra da baslar ('...00-0500 ...' ikinci numara); ondalik ('1.5...') ve tarih ('05.11.2026') degil.
# Oneksiz bicimler (5xx..., (212)..., +...) harften sonra baslamaz.
# ilke 5: butun obekleri iki haneli dizi telefon degildir ('05-06-07-08-09', '00.30, 01.30'); virgul, alt cizgi, orta nokta
# yalniz telefon bicimli gruplamada ayractir (binlik gruplama '05,000,000,000' degil)
# (sinirli tekrar: telefon en cok ~15 hanedir; sinirsiz ileri bakis uzun rakam dizisinde her konumda sona kadar tarar)
_TWO_GROUPS = r"(?:\d{2}(?:[^\w\n]|_){1,4}){2,8}\d{2}(?!\w)"
_THOUSANDS = r"\d{1,3}(?:[,_\u00b7\u2022\u2219\u30fb]\d{3}){2,5}(?!\d)"
_PHONE_UNIVERSAL = [
    rf"(?<!\d[.,]){_dl(0)}{{2}}{_GS_T}?(?!{_dl(0)}){_DG}{{1,3}}{_GS}{_DG}(?:{_GS}?{_DG}){{5,11}}(?!{_GS0}?{_DG0})",   # 00 49 ...
    rf"(?<!\w)(?<!\d[.,\-])\+{_DG}(?:[ \-.() ]{{0,2}}{_DG}){{7,14}}",                                  # +<8-15 hane>
]


def _after_words(words, links):
    """Building block of national phone shapes: 'right after one of these words + link' (fixed-width lookbehinds, any
    case), e.g. words ('call', 'tel') and links (' ', ': ', ' me on ') -> matches after 'Call me on '. Strings of the
    same length share one lookbehind."""
    by_len = {}
    for w in words:
        for k in links:
            s = w + k
            by_len.setdefault(len(s), []).append(re.escape(s))
    if not by_len:
        return wa2md_lang.NEVER
    return "(?:" + "|".join(f"(?<=(?i:{'|'.join(sorted(set(v)))}))" for _, v in sorted(by_len.items())) + ")"


@_on_pack
def _build_phone_ids():
    """Phone pattern (national shapes of the pack + universal shapes) and the pack's identifiers (IBAN, national id,
    plate). The universal alternatives start with '00' or '+', a national one that can start there comes first."""
    global _GLUED, _PHONE, _PHONE_RX, _PHONE_NAT_RX, _IBAN, _TCKN, _PLAKA
    # sozcuge yapisik oneksiz cep numarasi yalniz iletisim sozcugunden sonra ('TEL500 000 00 00', 'GSM5000000000')
    _GLUED = "".join(f"|(?<={''.join(f'[{c.upper()}{c}]' for c in w)})" for w in _P.phone_glued_words)
    b = types.SimpleNamespace(dl=_dl, DG=_DG, DG0=_DG0, GS=_GS, GS0=_GS0, GS_T=_GS_T, SEP=_SEP, DATE_AHEAD=_DATE_AHEAD,
                              GLUED=_GLUED, after=_after_words)
    # extension suffix of the pack ('ext. 204'): part of the phone match; a pack without one adds nothing to the pattern
    ext = "" if _P.phone_extension == wa2md_lang.NEVER else rf"(?:{_P.phone_extension})?"
    # the national shapes of the selected packs, then the MOBILE shapes of every shipped pack whatever the selection
    # (a Turkish mobile in an English chat is a phone; each mobile shape carries its own false-positive guards)
    nat = list(dict.fromkeys([*_P.phone_national(b), *(x for c in wa2md_lang.PACKS
                                                         for x in wa2md_lang.load_pack(c).phone_mobile(b))]))
    _PHONE = (rf"(?=[\d+(])(?<![\d+])(?!{_TWO_GROUPS})(?!{_THOUSANDS})(?:"
              + "|".join([*nat, *_PHONE_UNIVERSAL]) + rf"){ext}(?!{_DG0})(?![.,]\d)")
    _PHONE_RX = re.compile(_PHONE)
    _PHONE_NAT_RX = re.compile("(?:" + "|".join(nat) + rf"){ext}")   # national shapes only
    _IBAN, _TCKN, _PLAKA = _P.iban, _P.national_id, _P.plate


# IBAN of any country (ISO 13616): country code, two check digits, 11-30 letters/digits in groups of up to four;
# masked only when the mod-97 check holds (_iban_valid). The pack's own IBAN shape (field iban) is tried first.
_IBAN_ANY = r"(?<![\w])[A-Z]{2}\d{2}(?:[ \u00a0]?[A-Z0-9]{4}){2,7}(?:[ \u00a0]?[A-Z0-9]{1,3})?(?!\w)"


def _iban_valid(s):
    s = re.sub(r"\s", "", s)
    if not 15 <= len(s) <= 34:
        return False
    return int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1


# surname of several capitalized parts joined by a hyphen or an apostrophe, right after a given name (one space)
_COMPOUND_SURNAME = re.compile(r" ((?:[^\W\d_]{1,12}['’\-])+[^\W\d_]{2,})(?![\w'’\-])")
_INITIAL_BEFORE = re.compile(r"(?<![\w.])([A-Z])\.[ \t]?\Z")      # 'J. ' right before a word


_PHONE_EXT_TAIL = re.compile(r"[\s,]*[^\W\d_]+\.?:?\s*\d{1,5}$")    # trailing '<word> <1-5 digits>' (extension)

try:        # optional (Apache-2.0): validates phone candidates; wa2md works the same without it (standard library only)
    import phonenumbers as _phonenumbers
except ImportError:
    _phonenumbers = None


def _phone_ok(text, start, end):
    """True when the phone candidate text[start:end] found by the pattern is kept. Without the optional 'phonenumbers'
    package every candidate is kept, and so is every candidate in a national shape of the pack set (whatever the
    package says). Otherwise ('+<country> ...', '00 <country> ...') it is kept when the package admits a number of
    that length for that country code (is_possible_number): unknown country codes and impossible lengths stay text."""
    if _phonenumbers is None or _PHONE_NAT_RX.fullmatch(text, start, end):
        return True
    s = unicodedata.normalize("NFKC", text[start:end]).strip()
    tail = _PHONE_EXT_TAIL.search(s)
    digits = re.sub(r"\D", "", s[:tail.start()] if tail else s)      # an extension is not part of the length
    try:
        return _phonenumbers.is_possible_number(
            _phonenumbers.parse("+" + (digits if s.startswith("+") else digits[2:]), None))
    except _phonenumbers.NumberParseException:
        return False


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


@_on_pack
def _build_fold():
    """Letter folding of the pack: keys (_key) and the per-letter classes of name patterns (_name_regex)."""
    global _FOLD_I, _FOLD_PAIRS, _TO_BASE, _KEY_TABLE, _I_ANY, _I_CAP
    _FOLD_I, _FOLD_PAIRS = _P.fold_i, dict(_P.fold_pairs)
    _TO_BASE = {x: b for b, xs in _FOLD_PAIRS.items() for x in xs}
    _KEY_TABLE = str.maketrans({**{c: "i" for c in _FOLD_I}, **_TO_BASE})
    _I_ANY = f"[{_FOLD_I}]"
    _I_CAP = "[" + "".join(c for c in _FOLD_I if c.isupper()) + "]"


@functools.lru_cache(maxsize=1 << 16)
def _key(s):
    """Buyuk/kucuk harf, Turkce i/I/ı/İ ve ASCII-katlama (ç->c, ğ->g, ö->o, ş->s, ü->u) duyarsiz anahtar."""
    return nfc(s).translate(_KEY_TABLE).lower()


def _name_regex(name, cap=False):
    """Buyuk/kucuk harf ve Turkce harf duyarsiz ad ifadesi. cap: her sozcugun ilk harfi yalniz buyuk harf (S3/S7: yalniz
    buyuk harfli bicimiyle yayilan ad; 'Sıcak Çorba' eslesir, 'sıcak çorba' eslesmez)."""
    out, head = [], True
    for c in nfc(name):
        if c in _FOLD_I:
            out.append(_I_CAP if cap and head else _I_ANY)
        elif c.isspace():
            out.append(r"\s+")
            head = True
            continue
        elif c.isalpha():
            b = _TO_BASE.get(c, c.lower())
            cls = {b, b.upper(), *_FOLD_PAIRS.get(b, "")} if b in _FOLD_PAIRS else {c, c.lower(), c.upper()}
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
@_on_pack
def _build_trade():
    """Sector words, their suffixes and the business-domain rule of the pack (one list for trade names and domains)."""
    global _SECTOR_W, _SECTOR_GENERIC, _SECTOR_SFX_W, _SECTOR_KEY, _SECTOR_WEAK, _SECTOR_STRONG_KEY, _WEB_KEYS, _WEB_AFFIX
    global _WEB_PRE, _WEB_SQ, _WEB_STRONG, _TR_SLD_NC, _WEB, _WEB_RX, _WEB_Q
    _SECTOR_W, _SECTOR_GENERIC, _SECTOR_SFX_W = list(_P.sector_words), set(_P.sector_generic), list(_P.sector_suffixes)
    sfx = "|".join(sorted({_key(w) for w in _SECTOR_SFX_W}, key=len, reverse=True))
    _SECTOR_KEY = re.compile("(?:" + "|".join(sorted({_key(w) for w in _SECTOR_W}, key=len, reverse=True)) + ")(?:"
                             + sfx + ")?")
    # ilke 4: GUCLU sektor sozcugu (ticari ad ilan imi olmadan da maskelenir); zayif tetikleyiciler (genel sektor
    # sozcukleri ve sector_weak_extra) ilan imi ister ('HTTP Transport ayarı', 'Annem Kargo'dan aldı').
    _SECTOR_WEAK = _SECTOR_GENERIC | set(_P.sector_weak_extra)
    _SECTOR_STRONG_KEY = re.compile("(?:" + "|".join(sorted({_key(w) for w in _SECTOR_W if w not in _SECTOR_WEAK},
                                                              key=len, reverse=True)) + ")(?:" + sfx + ")?")
    # F: ciplak isletme alan adi ('www.ornekfirmaNakliyat.com.tr', 'nakliyat.ornekfirma.com.tr'). Dar kural: yalniz
    # ticari uzantilar (_P.web_tld); yalniz kayitli ad ve hemen ustundeki alt alan (www/m on ekleri sayilmaz) bakilir;
    # bunlardan birinde genel olmayan sektor sozcugu varsa, bu iki etiketten AYIRT EDICI olan(lar) [firma] olur. Sektor
    # sozcugunu cikarinca yalniz ek kalan etiket ('nakliyat', 'transportation') genel sozcuktur, firma degildir. Ana
    # makine dogrusal eslesir ([\w-]+ etiketleri); sektor sozcugu _web()'de aranir. Buyuk/kucuk harf duyarsiz.
    _WEB_KEYS = tuple(sorted({_key(w) for w in _SECTOR_W if w not in _SECTOR_GENERIC}, key=len, reverse=True))
    _WEB_AFFIX = set(_P.web_affixes)
    _WEB_PRE = set(_P.web_prefixes)
    _WEB_SQ = re.compile("|".join(_WEB_KEYS))
    _WEB_STRONG = re.compile("|".join(w for w in _WEB_KEYS if w not in {_key(x) for x in _SECTOR_WEAK}))   # S9
    _TR_SLD_NC = set(_P.web_noncommercial)   # ulke uzantisi altinda ticari olmayan ikinci duzey etiketler
    _WEB = (r"(?i:(?<![\w\-.@/%])(?P<wbp>(?:https?://)?)(?P<wbh>(?:[\w\-]+\.)*?[\w\-]+)"
            r"(?P<wbt>" + _P.web_tld + r")(?![\w\-]|\.\w))")
    _WEB_RX = re.compile(_WEB)
    _WEB_Q = re.compile(r"(?i:" + _P.web_tld_quick + r"(?![\w\-]))")   # on suzgec: ticari uzanti yoksa kural calismaz


@functools.lru_cache(maxsize=1 << 14)
def _is_sector(k):
    """Anahtar bicimli sozcuk sektor sozcugu mu (ekli bicimi dahil: nakliyattan, lojistigi)."""
    return bool(_SECTOR_KEY.fullmatch(k))


@functools.lru_cache(maxsize=1 << 14)
def _is_strong_sector(k):
    return bool(_SECTOR_STRONG_KEY.fullmatch(k))


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
@_on_pack
def _build_suffix():
    """Closed suffix list of the pack (groups in order, each optional); a pack without suffixes gives an empty group."""
    global _SFX_RX
    _SFX_RX = "(?:" + "".join(f"{_alt(g)}?" for g in _P.name_suffixes) + ")"


# ---- parola / gizli anahtar maskeleme (sezgisel; ayni tek Anonymizer yolu)


@_on_pack
def _build_secrets():
    """Password keywords, one-time-code words and units of the pack."""
    global _KW_SUF, _KW_EXACT, _KW, _KW_RX, _KW_END, _KW_ANY, _OTP_KW, _OTP_NUM, _OTP_SHORT, _KW_SEP
    link = "" if _P.secret_link == wa2md_lang.NEVER else r"[ \t]+(?:" + _P.secret_link + r")[ \t]+|"   # "PIN is 4321"  # gitleaks:allow (compares a pack field with the never-matching regex; no secret)
    _KW_SEP = r"(?P<sep>[ \t]*[:=][ \t]*|[ \t]+[-–—][ \t]+|" + link + r"[ \t]+)"
    _KW_SUF, _KW_EXACT = list(_P.secret_keywords), list(_P.secret_keywords_exact)
    _KW = (r"(?<!\w)(?:" + _alt(_KW_SUF) + r"(?:['’]?\w*)|" + _alt(_KW_EXACT) + r"s?)(?!\w)")
    _KW_RX = re.compile(_KW + _KW_SEP)
    _KW_END = re.compile(_KW + r"[ \t]*[:=\-–—]?[ \t]*$")
    _KW_ANY = re.compile(_KW)
    _OTP_KW = re.compile(r"(?<!\w)(?:" + "|".join(_name_regex(x) + r"\w*" for x in _P.otp_words) + "|" + _P.otp_extra
                         + r")(?!\w)")
    _OTP_NUM = re.compile(r"(?<![\w.,:/\-+])\d{4,8}(?!\w|[.,:/]\d|\s?(?:" + _P.otp_units + r")\b)")
    _OTP_SHORT = re.compile(r"(?<!\w)(?:" + _P.otp_short + ")")


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


@_on_pack
def _build_units():
    global _UNITS, _NOT_SECRET, _STOP, _CODE_CTX
    _UNITS = r"(?:" + _P.units + ")"
    _NOT_SECRET = re.compile(r"(?i:\d[\d.,]*\+?" + _UNITS + r"|[\d.,:/\-+]+|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|#\d+)|[0-9a-f]{7,12}")
    _STOP = {_key(x) for x in _P.secret_stop}
    _CODE_CTX = re.compile(_P.code_context)


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
    return _L.masks["password"] + tok[len(core):]


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
        digits = 4 if _key(m.group(0)).startswith(_P.pin_word) else 0
        if (len(core) >= 3 if loose else _cred_like(tok, digits)):
            spans.append((m.end(), m.end() + len(tok), tok))
            pos = m.end() + len(tok)
    for a, b, tok in reversed(spans):
        line = line[:a] + _mask_tok(tok, sink) + line[b:]
    if _OTP_KW.search(line):     # a digit group inside a phone number is no code ('+44 7700 900789 for the gate code')
        ph = [mo.span() for mo in _PHONE_RX.finditer(line)] if _PHONE_Q.search(line) else ()
        line = _OTP_NUM.sub(lambda mo: mo.group(0) if any(a <= mo.start() < b for a, b in ph) else _L.masks["code"], line)
    pending = (not spans) and bool(_KW_END.search(line))
    return line, pending


# ---- sistem satirlarindaki kisiler (eklendi/katildi/ayrildi/...): Ingilizce ve Turkce yerel
_QUOTED = re.compile(r"([\"“])([^\"“”\n]{1,200})([\"”])")


@_on_pack
def _build_system():
    """System-line, group-event and notice patterns of the export locale (Android and iOS)."""
    global _SYS_PATTERNS, _SUBJECT, _SYS_SPLIT, _SYS_NOT, _SYS_BAD, _SYS_NOTICE, _GROUP_EVT, _GRP_ONLY, _GRP_WEAK
    global _EVT_WORDS, _SELF_REFS, _NAME_SFX_STRIP
    _SYS_PATTERNS = [re.compile(p, re.I) for p in _P.system_patterns]
    _SUBJECT = re.compile(_P.subject_change, re.I)
    _SYS_SPLIT = re.compile(_P.system_split)
    _SYS_NOT = set(_P.system_not_person)
    _SYS_BAD = re.compile(_P.system_bad, re.I)
    # iOS sistem satirlari gonderen yerinde grup adiyla gelir ('[..] Grup: Ali added Veli'); kisisiz bildirimler de oyle
    _SYS_NOTICE = re.compile(_P.system_notice, re.I)
    _GROUP_EVT = re.compile(_P.group_event, re.I)
    # Yalniz grupta olan olaylar (tam satir): sohbetin grup oldugunu ve iOS'ta grup adiyla gelen satirin sistem satiri
    # oldugunu yalniz bunlar soyler. Siradan mesajda da gecen sozcukler ('Kardeşim de katıldı.') sayilmaz.
    _GRP_ONLY = [re.compile(p, re.I) for p in _P.group_only_patterns]
    # grupta, grup adiyla gelen ad bicimli olay satiri ('Jorvik Plimm left'): yalniz donusturmede
    _GRP_WEAK = re.compile(r"^(?P<s>.+?),? (?:" + _P.group_weak + r")\.?$", re.I)
    # on eleme: olay, sistem satiri ve bildirim desenlerinin anahtar sozcuklerinden biri yoksa satir olay/bildirim degildir
    # (duz alt dize aramasi: buyuk mesaj akisinda hizli)
    _EVT_WORDS = tuple(_P.event_words)
    _SELF_REFS = set(_P.self_refs)
    _NAME_SFX_STRIP = re.compile(_P.name_suffix_strip)


def system_people(body):
    """Sistem satiri -> [(kisi, ayni_kisi_ise_onceki)]: eklenen/katilan/ayrilan/degistiren kisiler (numaralar dahil)."""
    body = INVISIBLE.sub("", body or "").strip()
    out = []

    def add(x, same=None):
        x = _NAME_SFX_STRIP.sub("", " ".join(x.split()).lstrip("~ ").strip(" .,;"))   # Naime'yi -> Naime
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


def _body(m):
    return " ".join(v for k, v in message_parts(m) if k == "text" and v) if ("parts" in m or "lines" in m) else ""


def _system_shaped(body):
    return bool(system_people(body) or _SUBJECT.search(body) or _SYS_NOTICE.search(body))


_EVT_MAX = 1000     # bundan uzun satir olay/sistem satiri sayilmaz (gercek olay satirlari birkac yuz karakter)


def _evt_quick(body):
    low = body.lower()
    return any(w in low for w in _EVT_WORDS)


def _name_shaped(x):
    """Sistem satirindaki kisi gibi mi: 1-5 sozcuk, harf iceren her sozcuk buyuk harfle (ya da numara, 'you/sizi')."""
    x = _NAME_SFX_STRIP.sub("", " ".join(x.split()).lstrip("~ ").strip(" .,;"))
    if _key(x) in _SELF_REFS or re.fullmatch(r"\+?\d[\d ()\-]{6,}\d", x):
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
_RAW = {}            # dictionary file -> raw lines (read once per process)
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")
_APOS = re.compile("['’]")
_GAP_INI = re.compile(r"[.!?…:;]")
_LM_NEXT = re.compile(r" ([^\W\d_]\w*)")            # tek bosluk + sozcuk (ozel ad obegi: araya noktalama girmez)
# iletisim sozcugu alan olarak: ardinda (dolgu etiketi sozcukleriyle) ':', '-', '.' ('Tel: ...', 'İRT. ...',
# 'Yetkili Kişi: ...'). Ilan imi: bu ya da satirda telefon (_ad_line); 'WhatsApp Web açılmıyor' alan degildir.
# ayrac: ':', '-', '.', ok ('İRTİBAT ⇒ AD'); sozcukle ayrac arasinda parantezli ek olabilir ('Tel (Ofis): Ad Soyad')
_FIELD_SEP = r"(?:=>|->|[:\-\u2013\u2014]|\.(?!\w)|[\u21d2\u2192\u279c\u2794]|\u27a1\ufe0f?)"
# ticari adin ayirt edici sozcugu (sagdan sola): kesme ekli ve tireli bicim de ('Kaplo-Tavro Nakliyat'); sektor
# sozcugune tireyle bagli ad da ('Tavro-Nakliyat' -> '[firma]-Nakliyat'); URL/e-posta/anma parcasi degil
_FIRM_PREV = re.compile(r"(?<![\w./@:#" + _DASH + r"])([^\W\d_]+(?:['\u2019][^\W\d_]+)?(?:[" + _DASH + r"][^\W\d_]+)*)"
                        r"(?:[ \t]+(?:&[ \t]+)?|[" + _DASH + r"])$")
_JOIN_GAP = re.compile(r"[ \t]{0,2}[+&][ \t]{0,2}|[ \t]")                    # 'Tavro+Kişi 2', 'Tavro Kişi 2'
_GAP_WS = re.compile(r"\s+")
_HAS_DIGIT = re.compile(r"\d")
# hiz: telefon en az 7 hanedir ve iki hanesi arasinda en cok 14 rakam disi karakter olur (tus kapagi 2 + grup ayraci _GS
# 11, ')' dahil + '('); bu on denetimden gecmeyen satirda telefon aranmaz
_PHONE_Q = re.compile(r"\d(?:\D{0,14}\d){6}")
# iletisim sozcugu/telefon ile ad arasi; 7. tur: telefon ve isaret emojisi, ok, '|', '*' da ilan ayracidir ('Ad Soyad
# <telefon emojisi> 0500...'); emoji secicisi U+FE0F ayrac sayisina girmez
_CTX_PUNCT = "☎\U0001f4de\U0001f4f1\U0001f4f2\U0001f448\U0001f449☛☞→⇒➡➜➔>=|*"
_CTX_GAP_AFTER = re.compile(r"(?:[\s:.\-\u2013\u2014,/()" + _CTX_PUNCT + r"]\ufe0f?){0,4}")
_CTX_GAP_BEFORE = re.compile(r"(?:[\s:.\-\u2013\u2014,/(" + _CTX_PUNCT + r"]\ufe0f?){0,4}")
_FIRM_GAP = re.compile(r"[ \t]+(?:&[ \t]+)?")
_COLON = re.compile(r"[ \t]*:")
_HWS = re.compile(r"[ \t]*")
_ALNUM = re.compile(r"[^\W_]")
# guzergah baglami (F3, ilke 2): ok/tire ile oteki ucu yer adi, ardinda yukleme sozcugu, '<yer>'dan ... 'a' / '...'dan <yer>'e
_ARROW = r"(?:\u27a1\ufe0f?|\u2192|\u21d2|\u279c|\u2794|->|=>|>|-|\u2013|\u2014)"
_ROUTE_PRE = re.compile(r"([^\W\d_]+)(?:['\u2019][^\W\d_]+)?[ \t]*" + _ARROW + r"[ \t]*$")
_ROUTE_POST = re.compile(r"[ \t]*" + _ARROW + r"[ \t]*([^\W\d_]+)")
_ROUTE_GAP = " \t:.,;/()-\u2013\u2014"


def _rx_lit(s):
    """Literal text as regex source (spaces stay readable)."""
    return re.escape(s).replace("\\ ", " ")


def _keys(words):
    return {_key(x) for x in words}


@_on_pack
def _build_names():
    """Name-context vocabulary of the pack: honorifics, titles, institutions, contact and filler words, ordinary-word
    test, trade-name chain words, listing vocabulary and route words (all matched in key form unless stated)."""
    global _SIGN_ALONE, _SIGN_LONE
    global _TAKVIM, _CAL_NAMES, _SIGN_OFF, _CAPWORD, _HON, _HON_ORG, _HON_STOP, _INST_ANY, _INST_CAP, _INST_ANY_K, _INST_CAP_K, _LM_HZ
    global _SURNAME_SFX, _FAMILY, _TITLE_STOP, _SAYIN, _NOT_NAME_SFX, _SAYIN_STOP, _CONTACT_W, _ORG_UNIT, _CONTACT
    global _FILLER_W, _FILLER, _ORD_SFX, _ORD_W, _FILLER_PFX, _CONTACT_FIELD, _LEGAL_W, _LEGAL_K, _LEGAL_STRONG
    global _LEGAL_FORM, _SAN, _TIC, _LEGAL_PAIR, _LEGAL_GLUED, _AS, _AS_Q, _FIRM_ITEM, _FIRM_TAIL, _FIRM_HYPH
    global _ILAN_PLACE, _ILAN, _KIN, _KIN_JOIN, _FIRM_FUNC, _FIRM_STOP, _HON_BASE, _HON_SG, _ADDR_ADJ, _CONTRACTION
    global _ROUTE_LOAD, _ROUTE_FROM, _ROUTE_TO, _ROUTE_FROM_K, _ROUTE_TO_K, _ROUTE_CONTACT, _ROUTE_CONTACT_END
    P = _P
    _TAKVIM = _keys(P.calendar_words)                   # ay ve gun adlari: ad degil
    _CAL_NAMES = _keys(P.calendar_names)                # calendar words that are names with a surname or a title
    _SIGN_OFF = (None if P.closing_phrases == wa2md_lang.NEVER else      # closing phrase + one capitalized word, alone
                 re.compile(r"[ \t]*(?i:" + P.closing_phrases + r")[ \t]*[,.!\-\u2013\u2014]?[ \t]+"
                            r"(?P<w>[^\W\d_][^\W\d_'’\-]{1,14})[ \t]*[.!]*[ \t]*"))
    _SIGN_ALONE = re.compile(r"[ \t]*(?i:" + P.closing_phrases + r")[ \t]*[,.!\-\u2013\u2014]?[ \t]*")   # line 1 of 2
    _SIGN_LONE = re.compile(r"[ \t]*(?P<w>[^\W\d_][^\W\d_'’\-]{1,14})[ \t]*[.!]*[ \t]*")             # line 2 of 2
    _CAPWORD = _keys(P.capitalized_words)               # hep buyuk harfle yazilan, ad olmayan sozcukler
    _HON = re.compile(P.honorific_after)                # _key bicimi
    _HON_ORG = re.compile(P.honorific_org)              # Dernek Başkanı: onundeki sozcuk kurum adidir
    _HON_STOP = _keys(P.honorific_stop)
    # yer/kurum adi: ad + bu sozcuk (ya da araya buyuk harfli sozcukler) -> dokunulmaz (Mimar Sinan Üniversitesi, Hz. Muhammed)
    _INST_ANY = re.compile("^(?:" + "|".join(_key(x) for x in P.institution_any) + ")")
    _INST_CAP = re.compile("^(?:" + "|".join(_key(x) for x in P.institution_cap) + ")$")
    _INST_ANY_K = tuple(_key(x) for x in P.institution_any)      # onek (Hastanesinde)
    _INST_CAP_K = frozenset(_key(x) for x in P.institution_cap)   # tam sozcuk
    _LM_HZ = re.compile(P.landmark_before)
    _SURNAME_SFX = re.compile(P.surname_suffix)        # Öztürkoğlu
    _FAMILY = _keys(P.family_words)
    _TITLE_STOP = _keys(P.chat_title_stop)
    _SAYIN = set(P.title_before)
    _NOT_NAME_SFX = re.compile(P.title_not_name_suffix)   # Sayın Üyelerimiz, Sayın Yetkililer
    _SAYIN_STOP = _keys(P.title_stop)
    # ---- nakliye ilanlari: iletisim baglami, ticari ad, ilan sozlugu (anahtar bicimi; tek kod yolu: Anonymizer._scan)
    # iletisim sozcugu: ardindaki (ayrac ya da satirda telefon varsa), onundeki ya da maskelenen telefonun yanindaki buyuk
    # harfli 1-3 sozcuk kisi adidir
    _CONTACT_W = list(P.contact_words)
    # S3c: birim adi ('Muhasebe Birimi', 'Satış Departmanı') kisi degildir: iletisim adi olarak alinmaz
    _ORG_UNIT = re.compile(P.org_unit)
    _CONTACT = _keys(_CONTACT_W)
    # dolgu ve alan etiketi sozcukleri: iletisim baglaminda hicbir zaman ad degildir; numara*/telefon*/... ekli bicimleri de
    _FILLER_W = list(P.filler_words)
    _FILLER = _keys(_FILLER_W)
    # ilke 3: siradan sozcuk testi (zayif kanit yalniz bundan gecerse maskelenir; guclu bulgu gecmezse yalniz o yerde kalir)
    _ORD_SFX = re.compile(P.ordinary_suffix)
    _ORD_W = _keys(P.ordinary_words)
    _FILLER_PFX = tuple(_key(x) for x in P.filler_prefixes)
    _CONTACT_FIELD = re.compile(r"(?<![\w.\-/@])" + _alt(_CONTACT_W) + r"(?!\w)(?:[ \t]+" + _alt(_FILLER_W)
                                + r"(?!\w)){0,2}(?:[ \t]*\([^()\n]{1,24}\))?[ \t]*" + _FIELD_SEP)
    # sektor sozcugu ve hukuki bicim: onlerindeki buyuk harfli sozcukler firma adinin ayirt edici kismidir -> [firma].
    # Hizmet sozcukleri zincirin parcasidir ('Kaplo Lojistik Hizmetleri Ltd. Şti.': tek maske).
    _LEGAL_W = list(P.legal_words)
    _LEGAL_K = _keys(_LEGAL_W)
    _LEGAL_STRONG = _keys(P.legal_strong)
    # hukuki bicim (ikinci ilan imi gerekmez); tek 'Şirketi' siradan sozcuktur ('Elektrik Şirketi aradı')
    _LEGAL_FORM = _keys(P.legal_form)
    _SAN, _TIC, _LEGAL_PAIR = _keys(P.legal_san), _keys(P.legal_tic), _keys(P.legal_pair)
    _LEGAL_GLUED = re.compile(P.legal_glued)                                     # 'Ltd.Şti.' tek parca yazimi
    _AS = re.compile(r"(?<!\w)" + P.legal_special + r"\.?(?!\w)")                # A.Ş.
    _AS_Q = re.compile("[" + re.escape(P.legal_special_chars) + "]" if P.legal_special_chars else wa2md_lang.NEVER)  # on suzgec
    _FIRM_ITEM = (r"(?:(?:" + _alt(_SECTOR_W) + r")(?:['\u2019]\w+|" + _alt(_SECTOR_SFX_W) + r")?|" + _alt(_LEGAL_W)
                  + r"|" + P.legal_special + r")\.?(?!\w)")
    _FIRM_TAIL = re.compile(r"(?<!\w)" + _FIRM_ITEM + r"(?:[ \t.]*" + _FIRM_ITEM + r")*")   # 'Lojistik San. Tic. Ltd. Şti.'
    _FIRM_HYPH = re.compile(r"[^\W\d_][" + _DASH + r"](?=" + _FIRM_ITEM + ")")   # on suzgec: tireli sozcuk sozcuk sayilmaz
    # ilan sozlugu: il adlarinin gayriresmi bicimleri, yuk merkezi semtleri, ulke/bolge, arac/dorse, birim, sik ilan
    # sozcukleri. Bunlar kisi ya da firma adi sayilmaz. Il ve ilce adlarinin TEK kaynagi yer listesidir (places()); il
    # adlari yuklenince bu sozluge katilir (_LISTS['ilan']).
    _ILAN_PLACE = _keys(P.listing_places)
    _ILAN = _keys([*P.listing_places, *P.listing_words])
    _KIN = _keys(P.kin)                                 # ticari adin icindeki akrabalik/baglac
    _KIN_JOIN = _keys(P.kin_join)
    # ilke 4a: ticari ad kuralinin durdurma listesi (genel nitelemeler; ayirt edici sozcuk degil). S4: dilbilgisi sozcukleri
    # (_FIRM_FUNC) hukuki bicimli zincirde de ad degildir
    _FIRM_FUNC = _keys(P.firm_func)
    _FIRM_STOP = _FIRM_FUNC | _keys(P.firm_stop)
    # ilke 4c: yalin hitap firma adi olabilir; S5: tekil iyelik ekli hitap ('Ustam Nakliyat') da (anahtar bicimi)
    _HON_BASE = _keys(P.hon_base)
    _HON_SG = re.compile(P.hon_singular)
    _ADDR_ADJ = _keys(P.address_adjectives)
    _CONTRACTION = _keys(P.contraction_suffixes)          # "don't": a contraction, not Don + suffix
    # S8: yalniz kisinin ozne olamayacagi bicimler ('X yüklemeli', 'X çıkışlı')
    _ROUTE_LOAD = re.compile(r"[ \t]+" + _alt(P.route_load) + r"(?!\w)")
    _ROUTE_FROM = re.compile(r"([^\W\d_]+)['\u2019](?:" + P.route_from + r")(?!\w)")
    _ROUTE_TO = re.compile(r"([^\W\d_]+)['\u2019](?:" + P.route_to + r")(?!\w)")
    _ROUTE_FROM_K, _ROUTE_TO_K = tuple(P.route_from_keys), tuple(P.route_to_keys)
    _ROUTE_CONTACT = re.compile(r"(?<!\w)" + _alt(_CONTACT_W) + r"(?!\w)")
    _ROUTE_CONTACT_END = re.compile(r"(?<!\w)" + _alt(_CONTACT_W) + r"$")


@_on_pack
def _build_label_patterns():
    """Patterns that contain output labels (a label is never a name; a name part joins a neighbouring label; a masked
    phone is evidence): built from the pack's labels, so another label set works the same way."""
    global _LABEL_AFTER, _LABEL_AT, _LABEL_END, _LABEL_BEFORE, _PHONE_CTX, _TEL_MASK, _SIG_TAIL, _SURNAME_POS
    global _PERSON_WORD, _PERSON_PREFIX, _UNKNOWN, _TEL, _FIRMA, _URL_LABELS
    L = _L
    _PERSON_WORD, _PERSON_PREFIX, _UNKNOWN = L.person_word, L.person_word + L.person_sep, L.person_unknown
    _TEL, _FIRMA = L.masks["phone"], L.masks["company"]
    pw, ps, unk, tel = (_rx_lit(x) for x in (L.person_word, L.person_sep, L.unknown_mark, _TEL))
    _LABEL_AFTER = re.compile(ps + r"(?:\d|" + unk + ")")              # 'Kişi 3', 'Kişi ?': etiketin kendisi ad sanilmaz
    _LABEL_AT = re.compile(pw + ps + r"(\d+)")
    _LABEL_END = re.compile(pw + ps + r"(?:\d+|" + unk + r")(?:(?:[ \t]+(?:" + "|".join(_P.kin_join) + r"))?[ \t]+|[" + _DASH + r"])$")   # firma adindaki etiket
    _LABEL_BEFORE = re.compile("(" + pw + ps + r"\d+)(?:[ \t]{0,2}[+&][ \t]{0,2}|[ \t])$")   # 'Kişi N <ad>'
    _PHONE_CTX = re.compile(tel + "|" + _PHONE)      # ham satirda telefon, ciktida maskesi
    _TEL_MASK = re.compile(tel)
    # L9: ana makinesinde maske olan URL (etiketin boslugu kategori adinda tire olur: 'www.Kişi-8.com')
    _URL_LABELS = pw + "[" + ps + r"\-](?:\d+|" + unk + ")|" + _rx_lit(_FIRMA)
    _SIG_TAIL = re.compile(r"[\s\-\u2013\u2014:.,/|()]*(?:" + tel + r"[\s\-\u2013\u2014:.,/|()]*)*")   # imza sonu
    # soyad konumu (ilan baglaminda bilinmeyen soyad): satir sonu, ayrac, telefon (ham ya da maskeli)
    _SURNAME_POS = re.compile(r"[ \t]*(?:$|[:\-\u2013\u2014,/|(]|\.(?!\w)|" + tel + ")")


def _ad_line(line):
    """Satir ilan imi tasiyor mu: telefon (ham ya da maskeli) ya da alan olarak iletisim sozcugu."""
    return (_TEL in line or (bool(_PHONE_Q.search(line)) and bool(_PHONE_CTX.search(line)))
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
    if pre.endswith(_TEL) or _ROUTE_CONTACT_END.search(pre):
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
    if sfx in _ROUTE_FROM_K:
        mo = _ROUTE_TO.search(s, end, end + 60)
        return bool(mo and _route_place(mo.group(1)))
    if sfx in _ROUTE_TO_K:
        mo = None
        for mo in _ROUTE_FROM.finditer(s, max(0, st - 60), st):
            pass
        return bool(mo and _route_place(mo.group(1)))
    return False


_ACT_RANK = {"company": 4, "join": 3, "rx": 2, "ctx": 1}


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
            if p[:2] == d[:2] and p[4] == d[4] == "rx" and p[5] == "signature":    # S7: ad kurali (main) imzadan gucludur
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
        res[-1] = (p[0], d[1], top[2] if top[4] == "join" else "" if top[4] == "company" else _key(disp), disp, top[4],
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
    None (karar yok -> maskelenir, 'place_unclear' sayilir): kurum sozcugune ulasildi ama bu dar bicim yok
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


def _read_list(fn, missing=None):
    """Words of one dictionary file (raw, '#' lines skipped; read once per run) -> list; places: (kind, name) pairs."""
    path = os.path.join(_HERE, _P.dictionary_dir, fn)
    if path not in _RAW:
        try:
            with open(path, encoding="utf-8") as fh:
                _RAW[path] = [ln.rstrip("\n") for ln in fh if not ln.startswith("#")]
        except OSError:
            _RAW[path] = None
    if _RAW[path] is None and missing is not None:
        missing.append(fn)
    return _RAW[path] or []


def _pack_files(kind_files):
    return (kind_files,) if isinstance(kind_files, str) else tuple(kind_files)     # tuple: merged pack set


def name_lists():
    """(adlar, soyadlar, sozcuk-olan-adlar) anahtar kumeleri; ayni yukleyici yer listesini de okur (places()). Dosya yoksa
    bos kume; missing_name_lists() eksikleri verir (anonim modda main bunu hata sayar, bkz. --sozluksuz).
    Several packs selected: a given name of one pack that is an ordinary word of another selected pack (its 'common'
    list) and no given name there is a word-name too ('x'; English 'Ben', 'Kim' are Turkish 'ben', 'kim')."""
    if not _LISTS:
        missing = []
        files = _P.dictionary_files
        for k, kind_files in (("g", files["given"]), ("f", files["surname"]), ("a", files["ambiguous"]),
                              ("p", files["places"]), ("c", files.get("common", ()))):
            s = {} if k == "p" else set()
            for fn in _pack_files(kind_files):
                for line in _read_list(fn, missing):
                    if k == "p":                  # '<tur><TAB><ad>' (TR: il | ilçe)
                        kind, _, name = line.partition("\t")
                        if name.strip():
                            s[_key(name.strip())] = kind
                    else:
                        s.update(_key(w) for w in line.split())
            _LISTS[k] = s
        _LISTS["missing"] = missing
        _LISTS["x"], _LISTS["lw"], _LISTS["xo"], _LISTS["gcap"] = set(), set(), {}, set()
        codes = _P.code.split("+")
        if len(codes) > 1:                    # cross-pack ordinary words (one rule for every pair of selected packs)
            per = {}
            for c in codes:
                df = wa2md_lang.load_pack(c).dictionary_files
                per[c] = [{_key(w) for fn in _pack_files(df.get(kind, ())) for ln in _read_list(fn) for w in ln.split()}
                          for kind in ("given", "common")]
            for c in codes:
                for o in codes:
                    if o != c:                    # xo[o]: the word-names whose word sense is pack o's
                        _LISTS["xo"].setdefault(o, set()).update((per[c][0] & per[o][1]) - per[o][0])
                        _LISTS["x"] |= _LISTS["xo"][o]
                    elif not wa2md_lang.load_pack(c).lower_case_context:    # merged set: lower case can be a name, but
                        _LISTS["lw"] |= per[c][0] & per[c][1]               # in this pack it is the word ('120 miles')
            _LISTS["a"] |= _LISTS["x"]
            lcc = {c: wa2md_lang.load_pack(c).lower_case_context for c in codes}   # gcap: given names only of packs
            _LISTS["gcap"] = (set().union(*(per[c][0] for c in codes if not lcc[c]))  # whose capitals mark names
                              - set().union(*(per[c][0] for c in codes if lcc[c])))
        _ordinary.cache_clear()               # sozluk yeniden yuklendi (testler _LISTS'i temizler): onbellek eskidi
        p, g, f = _LISTS["p"], _LISTS["g"], _LISTS["f"]
        region = set(_P.place_region_kind.split("|"))
        _LISTS["ilan"] = _ILAN | {k for k, v in p.items() if v in region}     # il adlari ilan sozlugudur
        # yalniz yer: il adi ya da ad/soyad sozlugunde olmayan ilce adi (Bozova, Gebze); Fatih, Kartal, Bozkurt belirsizdir
        _LISTS["pure"] = {k for k, v in p.items() if " " not in k and (v in region or (k not in g and k not in f))}
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
                or (a and a in ".-" and a2.isalnum()) or (m.group(0) == _PERSON_WORD and _LABEL_AFTER.match(line, en))):
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
        select_packs(msgs)
        self._prev_line = None                 # line before the scanned one in the same text ('Cheers,' / 'Gav')
        self._dom = _DOMINANT[0]               # language that dominates this chat (its word-names need strong evidence)
        self.chat = nfc(chat)
        self.code = code or _L.chat.format(n=chat_no)
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
                lab = _L.person(len(set(self.labels.values())) + 1)
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
            person(m.get("sender"), "sender")
        for m, ps in zip(msgs, mparts):
            if ps and (m.get("sender") is None or m["sender"] in titles):
                body = " ".join(v for k, v in ps if k == "text" and v)
                # grupta grup adiyla gelen ve sistem satirina cevrilmemis olay satiri (mark_system_lines atlanmissa):
                # kisileri yine toplanir (ayni kural: title_event_line)
                if m.get("sender") is None or title_event_line(body):
                    for real, same in system_people(body):
                        person(real, "system_line", same)
        for real in extra or []:
            person(nfc(real).strip(), "extra_name")
        if not self.group:
            person(self.chat, "chat_name")         # bire bir: baslik karsidaki kisi (hic yazmamis olsa da)
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
            nd = 4 if _OTP_SHORT.search(_key(mtext[i])) else 6
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
                self.by_key[k] = _UNKNOWN
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
            self.by_key[k] = next(iter(labs)) if len(labs) == 1 else _UNKNOWN   # iki katilimcida ortak: notr
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
            self._prev_line = None             # the previous text line of the same message (its lines are parts)
            for kind, v in ps:
                if not v or kind == "omitted" or kind != "text":
                    self._prev_line = None
                if not v or kind == "omitted":
                    continue
                if kind == "file":
                    v = re.sub(r"[_\-.]+", " ", os.path.splitext(v)[0])
                self._actx = (("s", v), v) if kind == "quote" else mctx
                self._sigok = kind == "text"
                for line in v.split("\n"):
                    self._ad_used = False
                    dec = self._scan(line)
                    self._prev_line = line
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
                    loc = [d for d in dec if d[4] in ("ctx", "company")]
                    # hiz: kararlarin hepsi nakliye iletisim/firma karari ise satir ciktida rx ve _pre_apply ile tamamen islenir;
                    # yeniden tarama yeni bir sey bulamaz (adlarin ilk taramadaki karari ayni ham satirdan cikar)
                    done = bool(dec) and all(d[4] == "learn" or (d[4] in ("rx", "ctx", "company")
                                                                    and d[5] in ("contact", "signature", "company")) for d in dec)
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
        self._url_rx = re.compile(r"(?:" + _URL_LABELS + "|" + re.escape(self.code) + r")[\w\-]*(?:\.[\w\-]+)*?"
                                  r"\.(?i:" + _URL_TLD + r")(?P<ur>[/?#][^\s]*)")

    @staticmethod
    def _compile(names, forms, sfx_names, caps=()):
        names = sorted((n for n in {nfc(x) for x in names} if n.strip()), key=len, reverse=True)
        alts = [f"(?P<wame>{_WAME})", f"(?P<social>{_SOCIAL})", f"(?P<iban>{_IBAN})", f"(?P<ibanx>{_IBAN_ANY})",
                f"(?P<email>{_EMAIL})"]
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
        lab = _L.person(len(self._label_counts) + 1)   # dort etiket sozlugundeki farkli etiket sayisi + 1 (_LabelMap)
        self.origin[lab] = origin
        return lab

    def _learn(self, disp, why):
        """Metinde bulunan ad (sozluk/hitap/anma) -> etiket; her bicimiyle maskelenir. Ad+Soyad ise ad da (belirsiz
        degilse). Daha once sozlukle bulunmus tek ad + soyad ayni kisidir (ayni etiket); katilimci adi + baska soyad
        baska kisidir (yeni etiket)."""
        k = _key(disp)
        by_contact = why in ("contact", "signature")      # nakliye iletisim kaniti; oteki nedenler ad kurallarinin (main) kanitidir
        known = k in self.by_key
        k0 = _key(disp.split()[0]) if len(disp.split()) == 2 else None
        if known and not by_contact and k not in self._contact_keys and not (k0 and why in ("mention", "honorific") and k0 in self._contact_keys):
            return self.by_key[k]              # (Sayın/@ kaniti ad parcasini da yayar: once baska kanitla ogrenilmis olsa da)
        parts = disp.split()
        g, f, a = name_lists()
        # S3: iletisim kanitli ad, hicbir parcasi ad sozlugunde degilse (b) yalniz o obek ve yalniz buyuk harfli bicimiyle
        # yayilir ('Sıcak Çorba', 'Mavi Kapak': soyad listesinde siradan sozcuk coktur, tek basina kanit degildir). S7: zayif
        # kanitli imza ('imza') da yalniz tam obek, buyuk harfli bicimiyle; tek parcalari yayilmaz.
        part_cap = why == "signature" or (why == "contact" and not any(_key(p) in g for p in parts))
        # 7. tur: katilimci ad parcasi iceren ad tam obek olarak main gibi her bicimiyle yayilir; parcalari S3'teki gibi
        # (part_cap: yalniz hitap/Sayın yaninda)
        cap = part_cap and (why == "signature" or not any(_key(p) in self._pkeys for p in parts))
        lower_word = _LISTS.get("lw" if _P.lower_case_context else "c", ())  # English: lower case of a common word is the word
        cap = cap or bool(lower_word and len(parts) == 1 and k in lower_word)   # ('Miles' masked, '120 miles' stays)
        # Issue #22: a one-word surname that is also an everyday word (word-name list, no given name: 'Açık', 'Yavaş') learned
        # from an honorific or a mention spreads only in its capitalised forms ("Açık'a", 'dün Açık geldi'): the lower-case
        # word ('kapı açık') stays. A given name that is a word stays as before (a lower-case 'yetkin yardim' after
        # '@Yetkin Yardim' is a person: tests/fixtures/etkilesim_main.json), and so does every other learned name.
        cap = cap or bool(why in ("honorific", "mention") and len(parts) == 1 and k in a and k not in g)
        if known:                              # 7. tur eki: kanit bilineni yalniz guclendirir, sira sonucu degistirmez
            lab = self.by_key[k]
            if (not by_contact and k in self._contact_keys) or (not cap and k in self._capk):   # main'in kaniti ya da yalniz buyuk harfli
                self._strengthen(k, disp, by_contact)              # adda guclu iletisim: ayni etiketle her bicimiyle; parcalar asagida
        else:
            first = (self.by_key.get(k0) or self.ctx_labels.get(k0)) if k0 and k0 not in self._partof else None
            if first and first not in self._people and first != self.code and first != _UNKNOWN:
                lab = first
            else:
                lab = (self.ctx_labels.get(k) or self._capparts.get(k)
                       or self._new_label("contact" if why == "signature" else why))
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
                        self._capparts[pk] = lab if self._capparts.get(pk, lab) == lab else _UNKNOWN
            if self._compiled:
                self._lazy.add(k)
        if k0 and k0 not in a and (k0 in g or why in ("mention", "honorific")):
            if k0 not in self.by_key:
                (self.found_cap if lower_word and k0 in lower_word else self.found)[parts[0]] = lab
                if lower_word and k0 in lower_word:
                    self._capk.add(k0)
                self.by_key[k0] = lab
                if by_contact:
                    self._contact_keys.add(k0)
                if self._compiled:
                    self._lazy.add(k0)
            elif not by_contact and k0 in self._contact_keys:
                self._strengthen(k0, parts[0])
        if why == "contact" and len(parts) > 1 and not part_cap:   # ilke 3, S3a: guclu kanitli adin parcalari da ayni etiketle
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
                elif self._partof.get(pk, k) != k and self.by_key.get(pk) not in (lab, _UNKNOWN):
                    self.by_key[pk] = _UNKNOWN        # N1: iki ogrenilmis adda ortak parca: notr etiket (main gibi)
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
                if lab is not None and (self._participant(lab) or lab == _UNKNOWN):
                    lab = None
            self.ctx_labels[k] = lab or self._capparts.get(k) or self._new_label(why)
        return self.ctx_labels[k]

    def _special(self, line, toks, bases, keys):
        """Nakliye ilani kurallari -> (kararlar, ad kurallarinin atlayacagi sozcuk indeksleri). Karar bicimi _scan ile
        ayni; karar: 'company' (ticari adin ayirt edici sozcukleri -> [firma]), 'rx'/'ctx' (iletisim baglamindaki kisi adi,
        neden 'contact'; ad testinden (sozluk adi ya da listede soyad) gecmeyen baglam bulgusu yalniz o geciste: 'ctx'),
        'join' (katilimci etiketine komsu ad parcasi etikete katilir; anahtar yerine etiket), 'mark' (ilk taramada join
        adayi: satir yeniden taranir, maske yok). Ilan sozlugu (_ILAN: il, arac, birim, ilan sozcugu) ve dolgu/alan etiketi
        sozcukleri (_FILLER) hicbir kurala aday olmaz. _ad_ctx(): mesajda ilan imi (telefon ya da alan olarak iletisim
        sozcugu); _sig_ctx(): satir, ayni mesajda ilan imli satira komsu (imza adayi)."""
        out, skip, n = [], set(), len(toks)
        il = ilan_words()
        firm = (n and (not _LEGAL_STRONG.isdisjoint(keys) or any(map(_is_sector, keys))
                       or ("." in line and _LEGAL_GLUED.search(line)) or (bool(_AS_Q.search(line)) and _AS.search(line)))
                or (bool(_DASH_RX.search(line)) and bool(_FIRM_HYPH.search(line))))
        contact = n and not _CONTACT.isdisjoint(keys)
        if not firm and not contact and not any(b[:1].isupper() and k not in il for b, k in zip(bases, keys)):
            return out, skip     # hiz: firma ve iletisim disindaki her kural buyuk harfli, ilan sozlugunde olmayan sozcuk ister
        phone = n and (_TEL in line or (not self._compiled and bool(_PHONE_Q.search(line))))
        join = n and ((_PERSON_PREFIX in line) if self._compiled else not self._pkeys.isdisjoint(keys))
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
            legal = bool(ck & _LEGAL_FORM or _AS.search(chain) or (ck & _SAN and ck & _TIC) or _LEGAL_PAIR <= ck)
            strong = legal or any(_is_strong_sector(k) for k in ck)
            if not strong and not ((ck & _LEGAL_STRONG or any(_is_sector(k) for k in ck)) and ad()):
                continue
            lowok = legal or None                      # kucuk harfli sozcukte sorulur (ilan imi: _ad_used yalniz gerekince)
            if legal and hon and not _P.lower_case_context:   # English: before a capitalized legal form a lower-case
                lowok = False                                   # word is an ordinary word ('with Redwood Holdings Inc.')
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
            fam = any(e[2] == "k" and _key(line[e[0]:e[1]]) not in _KIN_JOIN for e in el)
            while el and (el[0][2] == "t" and not fam or (el[0][2] == "k" and not line[el[0][0]:el[0][0] + 1].isupper())):
                el.pop(0)
            if any(e[2] == "d" for e in el) or (fam and any(e[2] != "l" for e in el)):
                st, en = el[0][0], len(line[:m.start()].rstrip(" \t" + _DASH_CH))
                out.append((st, en, "", line[st:en], "company", "company"))
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
            why = "signature" if sig and not strong else "contact"     # S7: zayif imza obegi buyuk harfli bicimiyle yayilir
            out.append((st, en, _key(disp), disp, "rx" if strong and clean and not local or why == "signature" else "ctx", why))
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
        dom_x = _LISTS["xo"].get(self._dom, ()) if self._dom else ()   # another pack's given names that are ordinary
        toks = _tokens(line)                                            # words of the chat's dominant language
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
                    self.stats["place_unclear"] = self.stats.get("place_unclear", 0) + 1
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

        tcl = []

        def title_case_line():
            """Most words of the line are capitalized (a heading or a shouted line: capitals mark nothing). The first word,
            calendar words (capitalized in any sentence) and names (dictionary or known: 'Michael Thornbury and Laura
            Vexley came' is no heading) are not counted."""
            if not tcl:
                ws = [t[2] for t, kk in zip(toks[1:], keys[1:]) if len(t[2]) >= 2 and t[2][:1].isalpha()
                      and kk not in _TAKVIM and kk not in g and kk not in f and kk not in self.by_key]
                tcl.append(len(ws) >= 4 and sum(w[:1].isupper() for w in ws) * 2 > len(ws))
            return tcl[0]

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
            own = nb == toks[j][2] or not _P.lower_case_context      # English: "Tom Okonkwo's" (possessive)
            if not (k in g and k not in a and own) or len(nb) < 4 or _ordinary(nk):
                return 0
            if not _P.lower_case_context:      # capitals mark names (English): a capitalized unknown word right after an
                return 2 if not nb.isupper() and nk not in _LISTS["c"] and not title_case_line() else 0   # unambiguous
                #                                                         given name is its surname (not a common word)
            e = toks[j][0] + len(nb)
            cnext = j + 1 < n and keys[j + 1] in _CONTACT and not line[e:toks[j + 1][0]].strip()   # 'AD SOYAD İRTİBAT'
            if not (cnext or _SURNAME_POS.match(line, e) or _PHONE_CTX.match(line, _HWS.match(line, e).end())):
                return 0                               # soyad konumu degil
            if k in _LISTS["gcap"] and not nb.isupper() and nk not in _LISTS["c"]:
                return 2                               # merged set: a given name of a capitals language ('Call Emily
                #                                        Zabrowski'): the surname position is enough
            # baglam: hemen ardinda iletisim sozcugu, ayni satirda guclu sektor sozcugu ('… NAKLİYAT AD SOYAD') ya da ilan imi
            return 2 if cnext or sector_line() or self._ad_ctx() else 0

        def pair(i, st, nxt, nb, why="dictionary", weak=False):
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

        if n == 1 and _SIGN_OFF is not None and self._prev_line and _SIGN_ALONE.fullmatch(self._prev_line):
            mo = _SIGN_LONE.fullmatch(line)                 # 'Cheers,' and then 'Gav' on the next line
        elif 2 <= n <= 4 and _SIGN_OFF is not None:      # 'Cheers, Gav': a lone capitalized word after a closing phrase
            mo = _SIGN_OFF.fullmatch(line)
        else:
            mo = None
        if mo:
            w, wk = mo.group("w"), _key(mo.group("w"))
            if (not w.isupper() and (n > 1 or w[:1].isupper()) and wk not in self.by_key and wk not in _LISTS["c"]
                    and not _ordinary(wk) and wk not in _SAYIN_STOP and wk not in _SAYIN and not _HON.fullmatch(wk)):
                emit(mo.start("w"), mo.end("w"), wk, w, "ctx", "signature")
        i = 0
        while i < n:                          # ilke 2: ad kurallari (main) ozel kararlardan bagimsiz; birlesim _merge'de
            st, en, w, ini, men = toks[i]
            base, k = bases[i], keys[i]
            i += 1
            if k in self._lazy and (k not in self._capk or base[:1].isupper()):   # derlemeden sonra ogrenilen ad
                emit(st - men, st + len(base), k, base, "rx", self.origin.get(self.by_key[k], "dictionary"))
                continue
            cap = base[:1].isupper()
            if men:                           # @anma: katilimci degilse ad gibi duran sozcuk maskelenir
                if not self._known(k) and len(base) >= 2 and (cap or k in g or k in f):
                    emit(st - 1, st + len(base), k, base, "rx", "mention")
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
                            or (tk in _TAKVIM and tk not in _CAL_NAMES) or _NOT_NAME_SFX.search(tk) or self._known(tk)
                            or len(tb) < 2):
                        break
                    run.append(tb)
                    prev, j = t[0] + len(tb), j + 1
                    if t[2] != tb:
                        break
                if run:
                    s0 = toks[i][0]
                    disp = line[s0:prev]
                    emit(s0, prev, _key(disp), disp, "rx", "honorific")
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
            if (cap and k in g and k not in a and (not _P.lower_case_context or k in _LISTS["gcap"])
                    and not base.isupper()):
                mc = _COMPOUND_SURNAME.match(line, st + len(base))   # 'Mary Smith-Jones', 'Liam O'Brien', 'Al-Rashid'
                if (mc and all(x[:1].isupper() for x in re.split(r"['’\-]", mc.group(1)))
                        and not self._known(_key(mc.group(1)))):
                    emit(st, mc.end(1), _key(line[st:mc.end(1)]), line[st:mc.end(1)], "ctx", "dictionary")
                    while i < n and toks[i][0] < mc.end(1):
                        i += 1
                    continue
            sl = k in g and cap and k not in _TAKVIM | _CAPWORD and nxt and surname_like(nb, nk, k, i)
            if sl and ini and k in a and nk in g and nk not in a and not _P.lower_case_context:
                sl = 0                        # 'Tell Harvey': a word-name opening the sentence before a given name is a word
            if not sl and k in _CAL_NAMES and cap and nxt and nk in f and surname_like(nb, nk, k, i) == 1:
                sl = 1                        # 'June Carter': a calendar word is a name only before a listed surname
            if sl and not pfull(i):
                i = pair(i, st, nxt, nb, weak=sl == 2)      # Ad + Soyad (+ ucuncu parca)
                continue
            if nxt and _HON.fullmatch(nk):
                if k in g:
                    emit(st, st + len(base), k, base, "ctx" if k in a else "rx", "honorific")
                elif cap and k not in _HON_STOP and k not in _TAKVIM and not _HON_ORG.fullmatch(nk):
                    if k in f:                # soyad + hitap (Karakoç Hoca, Şimşek abi): satir basinda da
                        act = "rx"            # a word-name ('Açık Bey') too: _learn spreads it in its capitalised forms only
                    else:                     # satir basinda bilinmeyen sozcuk supheli; ogrenilmis adin parcasi (_capparts) o yerde
                        act = ("ctx" if k in self._capparts else "review") if ini else "rx"
                    emit(st, st + len(base), k, base, act, "honorific")
                continue
            if (cap and k in f and not _P.lower_case_context and not base.isupper() and st >= 3
                    and _INITIAL_BEFORE.search(line, 0, st)):   # 'J. Smith': an initial before a listed surname
                s0 = _INITIAL_BEFORE.search(line, 0, st).start(1)
                emit(s0, st + len(base), _key(line[s0:st + len(base)]), line[s0:st + len(base)], "ctx", "dictionary")
                continue
            if k not in g or k in _TAKVIM or (w != base and _key(w[len(base) + 1:]) in _CONTRACTION):
                continue
            prv = toks[i - 2] if i >= 2 and not line[toks[i - 2][1]:st].strip() else None
            titled = any(t and t[2][:1].isupper() and (_key(_APOS.split(t[2], 1)[0]) not in g
                                                      or _key(_APOS.split(t[2], 1)[0]) in a)
                         for t in (prv, nxt))      # 'Temel Satranç Eğitimi', 'Türk Medeni Kanunu': baslik bicimi
            if k in _CAPWORD:
                titled = True                      # hep buyuk harfle yazilan ad olmayan sozcuk (Türk, Ege, Kuzey)
            if k not in a and not cap and k in _LISTS["c"] and (not _P.lower_case_context or k in _LISTS["lw"]):
                emit(st, st + len(base), k, base, "review", "dictionary")    # lower case is the common word ('120 miles')
            elif k not in a:
                emit(st, st + len(base), k, base, "rx", "dictionary")
            elif cap and not base.isupper() and (w != base or (not ini and not titled and k not in dom_x)):
                emit(st, st + len(base), k, base, "ctx", "dictionary")    # dom_x: capitals alone are no evidence
            elif not cap and (w != base or (_P.lower_case_context and k not in _LISTS["x"]
                                            and any(t and _key(_APOS.split(t[2], 1)[0]) in self.by_key for t in (prv, nxt)))):
                emit(st, st + len(base), k, base, "ctx", "dictionary")   # kucuk harf: yalniz kesme eki / yaninda bilinen ad
            else:
                emit(st, st + len(base), k, base, "review", "dictionary")
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
            self._prev_line = rlines[n - 1] if rlines is not None and n else (lines[n - 1] if n else None)
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
                       else _FIRMA if act == "company" else k)          # join: k katilimci etiketidir
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
                    why = ("honorific" if why == "honorific" else "capitalized" if disp[:1].isupper() else "lowercase")
                    r = self.review.setdefault(k, [disp, 0, why, []])
                    r[1] += 1
                    if len(r[3]) < 3:
                        mo = re.search(r"(?<!\w)" + re.escape(disp) + r"(?!\w)", line)
                        if mo:
                            r[3].append(line[max(0, mo.start() - 40):mo.end() + 40].strip())
        return "\n".join(lines)

    def _pre_apply(self, text, key, rx):
        """Ilk taramada bir satir icin verilmis yerel kararlar ('ctx': zayif kanitli ad, imza, sozcuk anlami da olan ad;
        'company': ticari ad) ayni satirda rx'ten ONCE uygulanir: rx satirdaki bir adi (sozluk adi, katilimci parcasi)
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
            inner = {d for d in dec if d[4] in ("ctx", "company")
                     and any(a <= d[0] and d[1] <= b and b - a > d[1] - d[0] for a, b in spans)}
            inner = {d for d in inner if not any(x not in inner and x[0] < b and a < x[1] for x in dec for a, b in spans
                                                     if a <= d[0] and d[1] <= b)}
            parts, pos = [], 0
            for st, en, k, disp, act, why in dec:
                if (st, en, k, disp, act, why) in inner:
                    continue
                lab = _FIRMA if act == "company" else self._ctx_label(k, why, disp)
                if self._counting:
                    cat = "company" if act == "company" else self.origin.get(lab, why)
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
            labels[c] = _FIRMA
        if self._counting:
            self.stats["company"] = self.stats.get("company", 0) + 1
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
        return m.string[m.start():m.start("ur")] + r[0] + _L.masks["path"] + r[end:]

    def _handle(self, m):
        if self._counting:
            self.stats["username"] = self.stats.get("username", 0) + 1
        return _L.masks["user"]

    def _cat(self, lab):
        return "chat_name" if lab == self.code else self.origin.get(lab, "sender")

    def _mask(self, m):
        """-> (yerine, kategori|None)."""
        if m.group("wame"):
            return m.group("wp") + _TEL, "phone"
        if m.group("social"):
            return m.group("sp") + _L.masks["user"], "username"
        if m.group("iban"):
            return _L.masks["iban"], "iban"
        if m.group("ibanx"):          # any country: only a valid check sum; otherwise the phone rule sees the text
            if _iban_valid(m.group("ibanx")):
                return _L.masks["iban"], "iban"
            hit = []
            txt = _PHONE_RX.sub(lambda p: (hit.append(1), _TEL)[1] if _phone_ok(p.string, *p.span()) else p.group(0),
                                m.group("ibanx"))
            return txt, ("phone" if hit else None)
        if m.group("email"):
            return _L.masks["email"], "email"
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
            return _L.masks["national_id"], "national_id"
        if m.group("plaka"):
            return _L.masks["plate"], "plate"
        if not _phone_ok(m.string, m.start("phone"), m.end("phone")):
            return m.group("phone"), None
        return _TEL, "phone"

    def _name_label(self, m, grp, count=True):
        """rx ad eslesmesinin (grp: 'nm' ya da 'nn') etiketi; maskelenmeyecekse (yer/kurum adinin parcasi, kanitli
        guzergahtaki yer adi) None. count=False: 'place_unclear' sayilmaz (yalniz yoklama: _pre_apply)."""
        lab = self.by_key.get(_key(" ".join(m.group(grp).split())))
        if lab is None or self._landmark_hit(m, grp, lab, count) or self._route_hit(m, grp):
            return None
        return lab

    def _participant(self, lab):
        """Etiket bir katilimcinin (gonderen, sistem satiri kisisi, ek ad, bire bir baslik; belirsiz ad parcasi 'Kişi ?')
        ya da kisi adli sohbet basliginin mi: bunlara hicbir istisna (yer/kurum, Hz.) uygulanmaz."""
        return lab is not None and (lab in self._people or lab == self.code or lab == _UNKNOWN)

    def _route_hit(self, m, grp):
        """F3: katilimci adinin yalniz ilk olmayan konumdaki, sozlukte ad/soyad olmayan tek parcasi ('Bozova') guzergah
        baglaminda yer adidir: 'Şanlıurfa ➡️ Bozova', 'Bozova yüklemeli', "Bozova'dan Mersin'e" maskelenmez."""
        return (bool(self._route_keys) and _key(m.group(grp)) in self._route_keys
                and _route(m.string, m.start(grp), m.end(grp), m.end()))

    def _landmark_hit(self, m, grp, lab, count=True):
        """Katilimci olmayan sozluk adi dar bicimli yer/kurum adinin parcasi mi (Mimar Sinan Üniversitesi, Hz. Muhammed).
        Karar yoksa maskelenir ve 'place_unclear' sayilir."""
        if self._participant(lab):
            return False
        lm = _landmark(m.string, m.start(grp), m.end(grp), m.end())
        if lm is None and self._counting and count:
            self.stats["place_unclear"] = self.stats.get("place_unclear", 0) + 1
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
                line = re.sub(r"^(%s*)%sd{6,8}$" % (chr(92) + "s", chr(92)), lambda x: x.group(1) + _L.masks["code"], line)
            if cand:
                line = " ".join(_mask_tok(t, self._secrets) if _cred_like(t, cand) else t for t in line.split(" "))
            for sec in sorted(self._secrets, key=len, reverse=True):
                if sec in line:
                    line = re.sub(r"(?<![\w])" + re.escape(sec) + r"(?!\w)", _L.masks["password"], line)
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
                for tag, cat in ((_L.masks["password"], "password"), (_L.masks["code"], "code")):
                    n = joined.count(tag) - s.count(tag)
                    if n > 0:
                        self.stats[cat] = self.stats.get(cat, 0) + n
            if title and _SUBJECT.search(joined):
                joined = _QUOTED.sub(lambda q: q.group(1) + self.code + q.group(3), joined)
                if count:
                    self.stats["chat_name"] = self.stats.get("chat_name", 0) + 1
            if self._actx[0] in self._pre_keys:   # ilk taramanin yerel kararlari, rx bir parcasini etiketleyip bolmeden once
                joined = self._pre_apply(joined, self._actx[0], self.rx_t if title else self.rx)
            if _WEB_Q.search(joined):     # nakliye isletmesi alan adi (yalniz ticari uzantili satirda: hiz)
                joined = _WEB_RX.sub(self._web, joined)
            if "@" in joined:             # tek basina sosyal kullanici adi (yalniz '@' iceren satirda: hiz)
                joined = _HANDLE.sub(self._handle, joined)
            out = self._ctx(self._rx_sub(self.rx_t if title else self.rx, joined), joined)
            if (_PERSON_WORD in out or _FIRMA in out or self.code in out) and _URL_Q.search(out):   # L9: maskeli ana makine
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
        self.media[real] = _L.media.format(n=len(self.media) + 1, ext=ext)
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
# tur kimlikleri dilden bagimsiz; gosterilen ad dil paketinin etiketidir (_L.kinds)
_KINDS = [("image", {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".bmp"}),
          ("video", {".mp4", ".3gp", ".mov", ".mkv", ".avi", ".webm"}),
          ("audio", {".opus", ".ogg", ".mp3", ".m4a", ".aac", ".wav", ".amr"}),
          ("contact", {".vcf"}),
          ("pdf", {".pdf"}),
          ("office", {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf", ".csv",
                            ".txt", ".pages", ".numbers", ".key"}),
          ("archive", {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"})]
COPY_KINDS = {"image", "video", "audio"}   # anonim modda varsayilan yalniz bunlar kopyalanir (izin listesi); digerleri
#                                            (kisi karti, PDF, ofis, arsiv, bilinmeyen/uzantisiz) --belgeleri-kopyala ile
_FILE_EXT = set().union(*(exts for _, exts in _KINDS))
_TITLE_LINE = re.compile(r"\S.{0,200}\.[A-Za-z0-9]{2,5}$")      # ek basligi / dosya adi satiri


def media_kind(name):
    ext = os.path.splitext(name)[1].lower()
    return next((k for k, exts in _KINDS if ext in exts), "other")


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
    L = _L
    out.append(f"- {L.participants}: {', '.join(people) if people else '-'}")
    out.append(f"- {L.message_count}: {len(real)}")
    if msgs:
        out.append(f"- {L.date_range}: {msgs[0]['dt']:%Y-%m-%d} – {msgs[-1]['dt']:%Y-%m-%d}")
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
                rendered.append(L.media_omitted)
            else:
                real_name = export.find(val) if export is not None else None
                if no_media:
                    shown = ((anon.media_name(real_name) if anon else real_name) if real_name
                             else (anon.media_name(os.path.basename(val.replace("\\", "/"))) if anon else val))
                    manifest.setdefault(shown, (L.kinds[media_kind(val)], L.status_no_media))
                    rendered.append(L.media_omitted)
                    continue
                if real_name is None:      # eksik ek: adi var olan medyayla ayni kuralla notr (medya-N) olur
                    missing += 1
                    shown = anon.media_name(os.path.basename(val.replace("\\", "/"))) if anon else val
                    manifest.setdefault(shown, (L.kinds[media_kind(val)], L.status_missing))
                    rendered.append(L.file_missing.format(name=shown))
                    continue
                shown = anon.media_name(real_name) if anon else real_name
                kind_ = media_kind(real_name)
                if anon and kind_ not in COPY_KINDS and not copy_docs:
                    manifest.setdefault(shown, (L.kinds[kind_], L.status_not_copied))
                    rendered.append(L.attachment_not_copied.format(name=shown, kind=L.kinds[kind_]))
                else:
                    used[real_name] = True
                    manifest.setdefault(shown, (L.kinds[kind_], L.status_copied))
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
_STAT_ORDER = ["sender", "system_line", "extra_name", "dictionary", "honorific", "mention", "chat_name", "phone",
               "email", "username", "iban", "national_id", "plate", "password", "code", "place_unclear",
               "company", "contact", "signature"]      # the last three: former alphabetical tail, order kept
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
    lines = list(_L.manifest_head)
    for shown, (kind, status) in manifest.items():
        lines.append(f"| {shown.replace('|', '/')} | {kind} | {status} |")
        d = copied if status == _L.status_copied else skipped
        d[kind] = d.get(kind, 0) + 1
    with open(os.path.join(folder, _L.manifest_file), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return copied, skipped


def write_review(review_dir, shown, review):
    """<review_dir>/<Sohbet-N>-supheli-adlar.txt: maskelenmeden kalan, ad olabilecek sozcukler (yalniz operator icin).
    review_dir varsayilan olarak cikti klasorunun disinda (default_review_dir); git agacinin icine yazilmaz."""
    if git_work_tree(review_dir):
        raise RuntimeError(t("review_in_git_exc"))
    path = os.path.join(review_dir, sanitize(shown) + _L.review_suffix)
    if not review:
        if os.path.isfile(path):
            os.remove(path)
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prio = {"honorific": 0, "capitalized": 1, "lowercase": 2}
    rows = sorted(review.values(), key=lambda r: (prio.get(r[2], 3), -r[1], _key(r[0])))
    shown_why = {"honorific": t("why_honorific"), "capitalized": t("why_capitalized"), "lowercase": t("why_lowercase")}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(t("review_head", shown=shown))
        for word, n, why, ex in rows:
            reason = shown_why.get(why, why)
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
    select_packs(msgs)
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
    if not _PINNED[0] and current_packs() == "auto":      # an explicit --packs / WA2MD_PACKS needs no report
        codes = _P.code.split("+")
        print(t("packs_auto", codes=", ".join(codes), n=len(codes), total=len(wa2md_lang.PACKS)))
    if manifest:
        c, sk = write_manifest(folder, manifest)
        fmt = lambda d: ", ".join(f"{k} {v}" for k, v in sorted(d.items(), key=lambda x: -x[1])) or "-"
        print(t("attach_warn", c=sum(c.values()), cd=fmt(c), s=sum(sk.values()), sd=fmt(sk),
                path=os.path.join(folder, _L.manifest_file)))
    if anon:
        if copied:
            print(t("media_warn", n=copied))
        print(t("masked", counts=_count_line(anon.stats) or "-"))
        if missing_name_lists():
            print(t("no_dict_warn"))
        path = write_review(review_dir or default_review_dir(out_dir), shown, anon.review)
        if path:
            first = sum(1 for r in anon.review.values() if r[2] != "lowercase")
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
    check_packs_env(ap)
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
