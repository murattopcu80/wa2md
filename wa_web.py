#!/usr/bin/env python3
"""Exports WhatsApp Web (web.whatsapp.com) chats, photos included, to Markdown.

Collection (DOM reading, scrolling, photo blobs) lives in ONE JavaScript file: wa_collect.js. Two transports:

  1) CONSOLE (the working path): `snippet` prints / copies the ready-made JS; you paste it into F12 -> Console in the
     WhatsApp tab; bundles (wa-bundle-*.json) land in Downloads; `import` converts them to Markdown.
  2) CDP (experimental, connection not verified): `export` attaches to a running Chrome with Playwright, runs the same
     wa_collect.js, takes the bundles directly and writes them through the same import code.

Both paths write the Markdown with wa2md.write_chat (one writer).

    python wa_web.py snippet --chats "Ali Veli,Sample Group" [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--max-messages N] [--no-media]
                                     [--no-video]  (video, gif and audio are not opened, played or downloaded)
    python wa_web.py import <bundle files or folder> --out <folder>
    python wa_web.py list                       (CDP)
    python wa_web.py export --chats "Naime" --out <folder> [...]   (CDP)

Options also accept the Turkish aliases (--medya-yok, --video-yok, --ek-adlar, --inceleme-dizini, --sozluksuz, --anonim, --no-anonim);
--lang tr or WA2MD_LANG=tr selects Turkish help and console messages.

READ-ONLY: it writes nothing, sends nothing, reacts, deletes, archives or mutes nothing. Opening a chat marks its
messages as "read" (the other side sees blue ticks). Message texts are untrusted data.
"""
import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import unicodedata

import wa2md
import wa2md_lang  # noqa: E402 - importable once wa2md has set up its path

HERE = os.path.dirname(os.path.abspath(__file__))
COLLECT_JS = os.path.join(HERE, "wa2md_assets", "wa_collect.js")

KEY_RE = re.compile(r"^[A-Za-z0-9-]{1,40}$")
BUNDLE_RE = re.compile(r"^wa-bundle-.+-([0-9a-z]+)-(\d{3})(?: \(\d+\))?\.json$")
EXT_BY_KIND = {"image": ".jpg", "gif": ".mp4", "video": ".mp4", "audio": ".ogg", "document": ".bin"}

# ------------------------------------------------------------------ SECTION: tarih/saat ayristirma
_PRE_A = re.compile(r"^\[" + wa2md.TIME + r",?\s*" + wa2md.DATE + r"\]\s*(.*?):\s*$")
_PRE_B = re.compile(r"^\[" + wa2md.DATE + r",?\s*" + wa2md.TIME + r"\]\s*(.*?):\s*$")
_TIME_ONLY = re.compile(wa2md.TIME)


def parse_pre_plain(s):
    """'[14:05, 14.11.2026] Ad: ' -> (raw7, ad) | None"""
    s = wa2md.INVISIBLE.sub("", s or "").strip()
    m = _PRE_A.match(s)
    if m:
        H, M, S, ap, a, b, y, name = m.groups()
    else:
        m = _PRE_B.match(s)
        if not m:
            return None
        a, b, y, H, M, S, ap, name = m.groups()
    return (int(a), int(b), int(y), int(H), int(M), int(S or 0), ap), name.strip()


def fold(s):
    """Accent-free lower case (day dividers); the i-letters of every shipped pack (Turkish dotless i) fold to 'i' (the
    dividers are the export's own words: they do not depend on the chat's pack selection)."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().translate(_FOLD_I_TABLE)


_FOLD_I_TABLE = {ord(c): "i" for code in wa2md_lang.PACKS for c in wa2md_lang.load_pack(code).fold_i if c.islower()}


def parse_divider(text, today):
    """Gun basligi -> ('raw', (a, b, y)) | ('date', date) | None (tarih degilse)."""
    t = fold((text or "").strip())
    P = wa2md.active_pack()
    m = re.match(r"^" + wa2md.DATE + r"$", t)
    if m:
        return "raw", tuple(int(x) for x in m.groups())
    if t in P.web_today:
        return "date", today
    if t in P.web_yesterday:
        return "date", today - dt.timedelta(days=1)
    if t in P.web_weekdays:
        wd = list(P.web_weekdays).index(t) % 7
        back = (today.weekday() - wd) % 7 or 7
        return "date", today - dt.timedelta(days=back)
    return None


def meta_time(meta):
    """Mesaj alt bilgisi ('17:17' + tik simgesi metni) -> (H, M, S, ampm) | None"""
    tm = _TIME_ONLY.search(wa2md.INVISIBLE.sub("", meta or ""))
    if not tm:
        return None
    H, M, S, ap = tm.groups()
    return int(H), int(M), int(S or 0), ap


# ------------------------------------------------------------------ SECTION: satirlar -> wa2md mesajlari
def resolve_when(rows, today):
    """Her satirin (tarih, (saat, dakika)) bilgisi. Kaynak sirasi: data-pre-plain-text (tam damga) >
    gun basligi (+ alt bilgi saati) > komsu satirlar (saat geriye gidiyorsa sonraki gune ait)."""
    pres = [parse_pre_plain(r["stamp"]) if r.get("stamp") else None for r in rows]
    divs, cache = [], {}
    for r in rows:
        t = r.get("divider")
        if t is not None and t not in cache:
            cache[t] = parse_divider(t, today)
        divs.append(cache.get(t))
    raws = [p[0] for p in pres if p]
    raws += [d[1] + (0, 0, 0, None) for d in divs if d and d[0] == "raw"]
    mdy = wa2md.detect_mdy(raws)
    out = []
    for r, p, dv in zip(rows, pres, divs):
        d = hm = None
        if p:
            full = wa2md.to_datetime(p[0], mdy)
            if full:
                d, hm = full.date(), (full.hour, full.minute)
        else:
            if dv:
                if dv[0] == "date":
                    d = dv[1]
                else:
                    f = wa2md.to_datetime(dv[1] + (0, 0, 0, None), mdy)
                    d = f.date() if f else None
            tm = meta_time(r.get("meta"))
            if tm:
                f = wa2md.to_datetime((1, 1, 2000) + tm, False)
                hm = (f.hour, f.minute) if f else None
        out.append([d, hm, bool(p)])
    # tarihi olmayanlar: komsu satirlardan (once onceki bilinen, sonra sonraki)
    n = len(out)
    prev = [None] * n
    last = None
    for i, o in enumerate(out):
        prev[i] = last
        if o[0] is not None:
            last = (o[0], o[1])
    nxt = [None] * n
    last = None
    for i in range(n - 1, -1, -1):
        nxt[i] = last
        if out[i][0] is not None:
            last = (out[i][0], out[i][1])
    for i, o in enumerate(out):
        if o[0] is not None:
            continue
        p, q = prev[i], nxt[i]
        if p and q and p[0] != q[0] and o[1] is not None and p[1] is not None and o[1] < p[1]:
            o[0] = q[0]  # saat geriye gitti: gun degisti
        else:
            o[0] = (p or q or (None,))[0]
    return [(o[0], o[1]) for o in out]


def build_messages(rows, title, today, media_files=None, staging=None, no_media=False, own_name=None, no_video=False):
    """Paket satirlari -> wa2md mesaj listesi (parts modeli). media_files: {anahtar: (yol, uzanti)} (staging icinde).
    Medya dosyalari <YYYYMMDD-HHMM>-<kisa id>[-n].<uzanti> adina tasinir. no_video: alinmamis video/gif/ses
    "[video: aktarilmadi]" notu olur (toplayici onlara dokunmadi)."""
    media_files = media_files or {}
    L = wa2md.output_labels()
    own_name = L.own_name if own_name is None else own_name
    whens = resolve_when(rows, today)
    for r in rows:  # kendi adin: giden bir satirdaki damgadan
        if r.get("out") and r.get("stamp"):
            got = parse_pre_plain(r["stamp"])
            if got:
                own_name = got[1] or own_name
                break
    msgs, prev_dt = [], None
    for r, (d, hm) in zip(rows, whens):
        if r.get("system") is not None and re.search(wa2md.active_pack().web_system_skip, r["system"], re.I):
            continue
        if d is None:
            continue
        if hm is None:
            hm = (prev_dt.hour, prev_dt.minute) if prev_dt and prev_dt.date() == d else (0, 0)
        when = dt.datetime(d.year, d.month, d.day, hm[0], hm[1])
        prev_dt = when
        m = {"dt": when, "sender": None, "parts": [], "id": r["id"]}
        if r.get("system") is not None:
            if r["system"]:
                m["parts"] = [("text", r["system"])]
                msgs.append(m)
            continue
        pre = parse_pre_plain(r["stamp"]) if r.get("stamp") else None
        m["sender"] = (pre[1] if pre and pre[1] else None) or (own_name if r.get("out") else (r.get("author") or title))
        parts = m["parts"]
        text = wa2md.INVISIBLE.sub("", r.get("text") or "").strip()
        if r.get("deleted") and not text:
            parts.append(("note", L.deleted))
        if r.get("forwarded"):
            parts.append(("note", L.forwarded))
        if r.get("quote"):
            parts.append(("quote", wa2md.INVISIBLE.sub("", r["quote"]).strip()))
        media = r.get("media") or []
        if media and no_media:
            parts.append(("omitted", None))
        else:
            for i, md in enumerate(media):
                parts.extend(_media_parts(r, md, i, len(media), when, media_files, staging, no_video))
        for line in text.split("\n"):
            if line.strip():
                parts.append(("text", line.strip()))
        if parts:
            msgs.append(m)
    return msgs


def short_id(msg_id):
    tail = re.split(r"_", msg_id)
    tail = tail[-1] if tail and len(tail[-1]) >= 6 else msg_id
    return re.sub(r"[^A-Za-z0-9]", "", tail)[-8:] or "x"


_QUOTED = re.compile(r'^["“](.+?)["”](?:\s|$)')


def _download_failed_rx():
    """Pattern of the pack's 'download failed' note (the fixed text between its placeholders)."""
    t = wa2md.output_labels().download_failed
    return re.compile(".*".join(re.escape(x) for x in re.split(r"\{\w+\}", t) if x.strip()))


def doc_name(label):
    """Belge baslik ozniteligi ('"ad.ext" <indirme ipucu>') -> yalniz dosya adi."""
    label = wa2md.INVISIBLE.sub("", label or "").strip()
    m = _QUOTED.match(label)
    return (m.group(1) if m else label).strip()


NO_VIDEO_KINDS = ("video", "gif", "audio")   # --no-video: the collector never touches these (wa_collect.js NO_VIDEO_KINDS)


def _media_parts(r, md, idx, total, when, media_files, staging, no_video=False):
    kinds = wa2md.output_labels().web_kinds
    kind = md.get("kind") if md.get("kind") in kinds else "document"
    stem = f"{when:%Y%m%d-%H%M}-{short_id(r['id'])}" + (f"-{idx + 1}" if total > 1 else "")
    got = media_files.get(md.get("key")) if md.get("key") else None
    if got and os.path.isfile(got[0]):
        name = stem + got[1]
        target = os.path.join(staging, name)
        if os.path.abspath(got[0]) != os.path.abspath(target):
            os.replace(got[0], target)
        return [("file", name)]
    if no_video and kind in NO_VIDEO_KINDS:
        return [("note", wa2md.output_labels().not_exported.format(kind=kinds[kind]))]
    if kind == "image":  # yazicinin mevcut "dosya eksik" isaretcisi
        return [("file", stem + EXT_BY_KIND["image"])]
    label = doc_name(md.get("label")) or kinds[kind]
    return [("note", wa2md.output_labels().download_failed.format(kind=kinds[kind], label=label))]


def filter_messages(msgs, date_from=None, date_to=None, max_messages=None):
    """--from/--to/--max-messages (en yeni N gercek mesaj) uygular."""
    if date_from:
        msgs = [m for m in msgs if m["dt"].date() >= date_from]
    if date_to:
        msgs = [m for m in msgs if m["dt"].date() <= date_to]
    if max_messages:
        real_idx = [i for i, m in enumerate(msgs) if m["sender"]]
        if len(real_idx) > max_messages:
            msgs = msgs[real_idx[-max_messages]:]
    return msgs


# ------------------------------------------------------------------ SECTION: muhur (issue #21)
# Toplayici satirlari ve sohbet adini sekmede, indirmeden once sifreler (wa_collect.js seal(); ayni belirtim):
#   kEnc = HMAC(K, "wa2md-seal-2 enc"), kMac = HMAC(K, "wa2md-seal-2 mac"); blok i = HMAC(kEnc, nonce16 || be32(i));
#   ct = utf8(JSON) XOR anahtar akisi; tag = HMAC(kMac, "wa2md-seal-2\0" || kid || "\0" || aad || "\0" || nonce || ct).
#   aad (kimligi dogrulanan baslik): session \0 parca no \0 final(0|1) \0 snapshot(0|1) \0 medya parcalari (virgullu): eski bir
#   ara kayit baslik elle degistirilerek "tam" parca gibi acilamaz. HMAC-SHA256.
# Standart kutuphanede AES yok: PRF (HMAC-SHA256) sayac kipi + sifrele-sonra-MAC. Anahtar (32 bayt) snippet'te uretilir ve
# kullanici durum klasorunde (indirilenler ve cikti klasorunun disi) tutulur; kosunun her oturumu son parcasiyla
# ice aktarilinca silinir (anahtar dosyasi kosunun oturum sayisini ve bitenleri tutar).
SEAL_ALG = "wa2md-seal-2"
KID_RE = re.compile(r"^[0-9a-f]{16}$")


def _seal_subkeys(key):
    return (hmac.digest(key, SEAL_ALG.encode() + b" enc", "sha256"), hmac.digest(key, SEAL_ALG.encode() + b" mac", "sha256"))


def _xor_stream(k_enc, nonce, data):
    n = len(data)
    ks = b"".join(hmac.digest(k_enc, nonce + i.to_bytes(4, "big"), "sha256") for i in range((n + 31) // 32))[:n]
    return (int.from_bytes(data, "big") ^ int.from_bytes(ks, "big")).to_bytes(n, "big") if n else b""


def header_aad(part):
    """Parca basliginin dogrulanan alanlari (wa_collect.js headerAad ayni dizgiyi kurar): session, parca no, final, snapshot,
    mediaParts, varsa runChats (kosuda baslayan sohbet sayisi; yoksa alan da yok: runChats'siz parcalar acilir)."""
    try:
        no = int(part.get("part") or 0)
        media = ",".join(str(int(i)) for i in (part.get("mediaParts") or []))
    except (TypeError, ValueError):
        return "\0invalid"          # hicbir muhurle eslesmez
    fields = [str(part.get("session", "")), str(no), "1" if part.get("final") else "0", "1" if part.get("snapshot") else "0", media]
    if part.get("runChats") is not None:     # final part of a run: how many chats the run started (issue #21); absent in older parts
        try:
            fields.append(str(int(part["runChats"])))
        except (TypeError, ValueError):
            return "\0invalid"
    return "\0".join(fields)


def _seal_tag(k_mac, kid, aad, nonce, ct):
    return hmac.digest(k_mac, SEAL_ALG.encode() + b"\0" + kid.encode("ascii") + b"\0" + aad.encode("utf-8") + b"\0" + nonce + ct,
                       "sha256")


def seal(obj, key, kid, nonce=None, aad=""):
    """Python esi (testler ve bilinen cevap): JSON.stringify ile ayni bayt dizisi (ensure_ascii=False, ayiricisiz).
    aad: header_aad(parca basligi)."""
    nonce = nonce or secrets.token_bytes(16)
    k_enc, k_mac = _seal_subkeys(key)
    ct = _xor_stream(k_enc, nonce, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {"alg": SEAL_ALG, "kid": kid, "nonce": b64(nonce), "ct": b64(ct), "tag": b64(_seal_tag(k_mac, kid, aad, nonce, ct))}


def unseal(sealed, key, aad=""):
    """Muhurlu yuk -> nesne. Butunluk denetimi (sabit zamanli; yukle birlikte aad = parca basligi) gecmezse ValueError."""
    if not isinstance(sealed, dict) or sealed.get("alg") != SEAL_ALG or not KID_RE.match(str(sealed.get("kid", ""))):
        raise ValueError("seal")   # (load_session names an older / unknown format before it gets here)
    nonce, ct, tag = (base64.b64decode(sealed.get(k, ""), validate=True) for k in ("nonce", "ct", "tag"))
    k_enc, k_mac = _seal_subkeys(key)
    if len(nonce) != 16 or not hmac.compare_digest(tag, _seal_tag(k_mac, sealed["kid"], aad, nonce, ct)):
        raise ValueError("seal")
    return json.loads(_xor_stream(k_enc, nonce, ct).decode("utf-8"))


def _key_dir():
    return os.path.join(wa2md.state_dir(), "keys")


def _key_path(kid):
    return os.path.join(_key_dir(), kid + ".key")


def _write_key_file(kid, rec, exclusive=False):
    """Anahtar dosyasi (JSON: key, sessions, done), 0600; degisiklik gecici dosya + yeniden adlandirma."""
    os.makedirs(_key_dir(), exist_ok=True)
    path = _key_path(kid)
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    else:
        path += ".tmp"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        json.dump(rec, f)
    if not exclusive:
        os.replace(path, _key_path(kid))


def new_seal(store=True, sessions=1):
    """Kosu anahtari -> {"kid", "key"(hex)}. store: kullanici durum klasorune yaz (0600; konsol yolu); sessions: kosuda
    istenen sohbet sayisi (her biri bir oturum: anahtar hepsinin son parcasi ice aktarilinca silinir). CDP yolunda anahtar
    yalniz bellekte kalir (store=False)."""
    kid, key = secrets.token_hex(8), secrets.token_bytes(32)
    if store:
        _write_key_file(kid, {"key": key.hex(), "sessions": max(1, int(sessions)), "done": []}, exclusive=True)
    return {"kid": kid, "key": key.hex()}


def _read_key_file(kid):
    if not KID_RE.match(kid or ""):
        return None
    try:
        with open(_key_path(kid), encoding="ascii") as f:
            rec = json.load(f)
        bytes.fromhex(rec["key"])
        return rec
    except (OSError, ValueError, KeyError, TypeError):
        return None


def load_key(kid):
    """Durum klasorundeki anahtar | None."""
    rec = _read_key_file(kid)
    return bytes.fromhex(rec["key"]) if rec else None


def drop_key(kid):
    if KID_RE.match(kid or ""):
        try:
            os.remove(_key_path(kid))
        except OSError:
            pass


def session_imported(kid, sid, chats=None):
    """Oturumun son parcasi ice aktarildi ve paketleri silindi: anahtar dosyasina isle. chats: son parcanin basliginda
    (dogrulanmis) kosuda gercekte baslayan sohbet sayisi; kosunun oturum sayisi bundan buyuk kalamaz (durdurma ya da
    bulunamayan sohbet). Anahtari BURADA silmeyen karar: release_keys. -> (biten, toplam); anahtar dosyasi yoksa None."""
    rec = _read_key_file(kid)
    if rec is None:
        return None
    rec["done"] = sorted(set(rec.get("done") or []) | {sid})
    total = max(1, int(rec.get("sessions") or 1))
    try:
        if chats is not None and int(chats) >= 1:
            total = rec["sessions"] = min(total, int(chats))
    except (TypeError, ValueError):
        pass
    _write_key_file(kid, rec)
    return len(rec["done"]), total


_SEALED_KID_RX = re.compile(rb'"sealed"\s*:\s*\{[^{}]{0,200}?"kid"\s*:\s*"([0-9a-f]{16})"')


def sniff_sealed_kid(path):
    """Paket dosyasi muhurluysa muhrun anahtar kimligi (dosyayi yuklemeden, parca parca taranir) | None."""
    try:
        with open(path, "rb") as f:
            tail = b""
            while chunk := f.read(1 << 20):
                m = _SEALED_KID_RX.search(tail + chunk)
                if m:
                    return m.group(1).decode("ascii")
                tail = chunk[-400:]
    except OSError:
        pass
    return None


def release_keys(inputs, kids):
    """Ice aktarimdan sonra: kosunun TUM oturumlari ice aktarildiysa VE girdilerde bu anahtarla muhurlu, donusturulmemis
    paket kalmadiysa anahtari sil (issue #21: ayni parca iki kosuda calistiginda ya da bir oturum donusturulemediginde
    anahtar, kalan paketin tek acilis yolu olarak durur); yoksa neden durdugunu yaz (yalniz sayilar)."""
    if not kids:
        return
    left = {sniff_sealed_kid(p) for parts in find_bundle_files(inputs).values() for p in parts.values()}
    for kid in sorted(kids):
        rec = _read_key_file(kid)
        if rec is None:
            continue
        done, total = len(rec.get("done") or []), max(1, int(rec.get("sessions") or 1))
        if done < total:
            print(wa2md.t("web_key_kept", done=done, total=total))
        elif kid in left:
            print(wa2md.t("web_key_kept_bundles"))
        else:
            drop_key(kid)


# ------------------------------------------------------------------ SECTION: paket okuma + import
def ext_for(mime, kind="image"):
    mime = (mime or "").split(";")[0].strip().lower()
    fixed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
             "video/mp4": ".mp4", "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "application/pdf": ".pdf"}
    return fixed.get(mime) or mimetypes.guess_extension(mime) or EXT_BY_KIND.get(kind, ".bin")


_HEAD_RE = re.compile(r'"format"\s*:\s*"wa-web-bundle".*?"session"\s*:\s*"([0-9a-z]+)"\s*,\s*"part"\s*:\s*(\d+)', re.S)


def sniff_bundle(path):
    """Dosya adi wa-bundle-*.json degilse (or. Chrome yedek yolunda GUID adi verir): baslik JSON'undan (oturum, parca)."""
    try:
        with open(path, "rb") as f:
            head = f.read(2048).decode("utf-8", "replace")
    except OSError:
        return None
    m = _HEAD_RE.search(head)
    return (m.group(1), int(m.group(2))) if m else None


def find_bundle_files(inputs):
    """Dosya/klasor listesi -> {oturum: {parca_no: yol}}. Klasorde yalniz wa-bundle-*.json adlari taranir; acikca
    verilen dosya baska ad tasisa da basligi paket ise kabul edilir."""
    sessions = {}
    for inp in inputs:
        explicit = not os.path.isdir(inp)
        paths = [inp] if explicit else [os.path.join(inp, n) for n in sorted(os.listdir(inp))]
        for p in paths:
            if not os.path.isfile(p):
                continue
            m = BUNDLE_RE.match(os.path.basename(p))
            if m:
                sessions.setdefault(m.group(1), {})[int(m.group(2))] = p
            elif explicit and (got := sniff_bundle(p)):
                sessions.setdefault(got[0], {})[got[1]] = p
    return sessions


def load_session(parts, staging, keys=None):
    """Bir oturumun parcalarini sirayla oku: medyayi staging'e yaz, satir parcasini don. Satir parcasi son parcadir
    (final); o yoksa en yeni ara kayittir (snapshot, issue #20: sekme kapanmis ya da toplama yarida kalmis).
    Gerekli parcalar: bicim 2'de satir parcasinin kendisi ve dayandigi medya parcalari (mediaParts; eski ara kayitlar
    gerekmez), bicim 1'de 1..total. Muhurlu parca (issue #21) bellekte acilir: keys(kid) -> anahtar | None.
    -> (satir_parcasi, {anahtar: (yol, uzanti)}, tamam_mi, muhur_kimligi | None)"""
    final, snap, files, kid = None, None, {}, None
    for no in sorted(parts):
        with open(parts[no], encoding="utf-8") as f:
            part = json.load(f)
        if part.get("format") != "wa-web-bundle":
            raise ValueError(wa2md.t("web_not_bundle", no=no))
        for item in part.get("media") or []:
            key = item.get("key", "")
            if not KEY_RE.match(key):
                continue  # guvensiz ad (yol gecisi vb.) yok sayilir
            ext = ext_for(item.get("mime"))
            path = os.path.join(staging, key + ".tmp")
            with open(path, "wb") as out:
                out.write(base64.b64decode(item.get("b64", "")))
            files[key] = (path, ext)
        if part.get("sealed") is not None:
            alg = part["sealed"].get("alg") if isinstance(part["sealed"], dict) else None
            if alg != SEAL_ALG:   # an older (wa2md-seal-1) or unknown format is not a damaged file: say what it is
                raise ValueError(wa2md.t("web_seal_format", no=no, alg=alg if re.fullmatch(r"wa2md-seal-\d{1,3}", str(alg)) else "?"))
            kid = str((part["sealed"] or {}).get("kid", "")) if isinstance(part["sealed"], dict) else ""
            key = keys(kid) if keys else None
            if key is None:
                raise ValueError(wa2md.t("web_seal_no_key"))
            try:   # the header (session, part number, final / snapshot flags, media parts) is part of the MAC (issue #21 review)
                if part.get("part") != no:
                    raise ValueError("part")
                inner = unseal(part.pop("sealed"), key, header_aad(part))
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError(wa2md.t("web_seal_bad", no=no)) from None
            part["chat"], part["rows"] = inner.get("chat"), inner.get("rows")
        if part.get("final"):
            final = part
        elif part.get("snapshot") and isinstance(part.get("rows"), list):
            snap = part                    # parcalar sirayla okunur: en yeni ara kayit kalir
        del part
    head = final or snap
    if head is None:
        raise ValueError(wa2md.t("web_no_final"))
    if isinstance(head.get("mediaParts"), list):
        need = {int(i) for i in head["mediaParts"]} | {int(head.get("part", 0))}
    else:
        need = set(range(1, int(head.get("total") or 0) + 1))
    missing = sorted(i for i in need if i not in parts)
    if missing:
        raise ValueError(wa2md.t("web_missing_parts", parts=", ".join(str(i) for i in missing)))
    return head, files, final is not None, kid


def import_bundles(inputs, out_dir, date_from=None, date_to=None, max_messages=None, anonim=False,
                   chat_start=1, no_media=False, ref_start=1, extra_names=None, review_dir=None, no_dict=False,
                   keep_bundles=False, seal_keys=None, keep_incomplete=True):
    """Paketleri Markdown'a cevir (wa2md.write_chat; wa2md ile ayni secenekler: ek adlar, inceleme klasoru, sozluksuz).
    Grup karari tarih/sayi suzgecinden ONCE tum paketten verilir (wa2md.is_group). Basariyla yazilan oturumun paket
    dosyalari silinir, son parcasi olmayan (yalniz ara kayit) oturumunki silinmez (maskelenmemis sohbeti tasirlar;
    keep_bundles saklar; issue #20; keep_incomplete=False: son parca gelmeyecek (CDP yolu), ara kayit donusunce silinir).
    Muhurlu paketin anahtari seal_keys'te (CDP: yalniz bellekte) ya da kullanici durum
    klasorunde aranir; durum klasorundeki anahtar, kosunun HER oturumu son parcasiyla ice aktarilip paketleri silinince
    silinir (anahtar dosyasi kosunun oturum sayisini tutar; issue #21: eksik oturum ya da yalniz bir kismi verilen
    kosuda anahtar kalir, onun paketleri hala o anahtarla acilir). -> (yazilan, atlanan)"""
    sessions = find_bundle_files(inputs)
    seal_keys = seal_keys or {}
    if not sessions:
        print(f"{wa2md.t('err')}: " + wa2md.t("web_no_bundles"), file=sys.stderr)
        return 0, 1
    done = failed = 0
    touched = set()   # keys of the sealed sessions converted in this call
    red = anonim  # anonimde konsolda ad / dosya adi / icerik yok
    for k, (sid, parts) in enumerate(sorted(sessions.items())):
        staging = tempfile.mkdtemp(prefix="wa_web_")
        ref = wa2md.t("ref_input", n=ref_start + k)
        try:
            try:
                final, files, complete, kid = load_session(parts, staging, lambda k: seal_keys.get(k) or load_key(k))
            except (ValueError, OSError, json.JSONDecodeError) as e:
                msg = e if not red else (e if type(e) is ValueError else wa2md.safe_error(e))
                print(f"{wa2md.t('err')} [{ref if red else sid}]: {msg}", file=sys.stderr)
                failed += 1
                continue
            title = final.get("chat") or sid
            today = dt.date.fromisoformat(final["today"]) if final.get("today") else dt.date.today()
            o = final.get("opts") or {}
            d_from = date_from or (dt.date.fromisoformat(o["from"]) if o.get("from") else None)
            d_to = date_to or (dt.date.fromisoformat(o["to"]) if o.get("to") else None)
            maxm = max_messages or o.get("max") or None
            msgs = build_messages(final["rows"], title, today, files, staging, bool(o.get("noMedia")) or no_media,
                                  no_video=bool(o.get("noVideo")))
            group = wa2md.is_group(msgs, title)
            msgs = filter_messages(msgs, d_from, d_to, maxm)
            if not msgs:
                print(f"{wa2md.t('warn')} [{ref if red else title}]: " + wa2md.t("empty_range_web"), file=sys.stderr)
                failed += 1
                continue
            export = wa2md.Export("web", "", b"", wa2md.scan_files(staging))
            wa2md.write_chat(title, msgs, export, out_dir, anonim=anonim, chat_no=chat_start + done, group=group,
                             extra_names=extra_names, review_dir=review_dir, no_dict=no_dict)
            failed_note = _download_failed_rx()
            skipped = sum(1 for m in msgs for k, v in m["parts"] if k == "note" and failed_note.search(v))
            if skipped:
                print(wa2md.t("web_skipped_media", n=skipped))
            if final.get("olderOnPhone"):
                print(wa2md.t("web_older_on_phone"))
            if not complete:
                print(wa2md.t("web_incomplete", no=final.get("part")))
            elif final.get("stopped"):
                print(wa2md.t("web_stopped"))
            done += 1
            if complete and not keep_bundles:
                if _delete_bundles(parts.values()) == 0 and kid and kid not in seal_keys:
                    session_imported(kid, sid, final.get("runChats"))   # release_keys (below) decides when the key goes
                    touched.add(kid)
            elif not complete and keep_incomplete:
                print(wa2md.t("web_parts_kept"))  # eksik oturum: son parca sonradan inebilir, parcalar yerinde kalir
            elif not complete and not keep_bundles:
                _delete_bundles(parts.values())   # son parca gelmeyecek: ara kayit donustu, parcalar gerekmez
        except Exception as e:  # noqa: BLE001 - anonimde iz/yol (ad icerir) yerine yalniz tur
            if not red:
                raise
            print(f"{wa2md.t('err')} [{ref}]: " + wa2md.t("unexpected", kind=type(e).__name__), file=sys.stderr)
            failed += 1
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    release_keys(inputs, touched)
    print(wa2md.t("web_done", done=done, failed=failed))
    return done, failed


def _delete_bundles(paths):
    """Donusturulen oturumun paket dosyalarini sil; konsola yalniz sayilar (dosya adi sohbet adini tasir)."""
    gone = bad = 0
    for p in paths:
        try:
            os.remove(p)
            gone += 1
        except OSError:
            bad += 1
    if gone:
        print(wa2md.t("web_deleted", n=gone))
    if bad:
        print(wa2md.t("web_delete_failed", n=bad), file=sys.stderr)
    return bad


# ------------------------------------------------------------------ SECTION: komut satiri -> toplayici secenekleri
def collector_opts(args, chats):
    return {"chats": chats, "from": args.date_from.isoformat() if args.date_from else None,
            "to": args.date_to.isoformat() if args.date_to else None, "max": args.max_messages or 0,
            "noMedia": bool(args.no_media), "noVideo": bool(getattr(args, "no_video", False)), "olderFromPhone": bool(getattr(args, "older_from_phone", False)),
            "pace": float(os.environ.get("WA_PACE", "1")), "lang": wa2md.current_lang(),
            "checkpointMin": max(0.0, float(getattr(args, "checkpoint_minutes", 10) or 0))}


def read_collector():
    with open(COLLECT_JS, encoding="utf-8") as f:
        return f.read()


def split_chats(s):
    return [c.strip() for c in s.split(",") if c.strip()]


def copy_to_clipboard(text):
    """Windows panosuna kopyala (clip.exe; metin ASCII). Basarisizsa False."""
    try:
        subprocess.run(["clip"], input=text.encode("ascii"), check=True, capture_output=True, timeout=20)
        return True
    except (OSError, subprocess.SubprocessError, UnicodeEncodeError):
        return False


def cmd_snippet(args):
    chats = split_chats(args.chats)
    if not chats:
        print(f"{wa2md.t('err')}: " + wa2md.t("web_chats_empty"), file=sys.stderr)
        return 2
    opts = collector_opts(args, chats)
    opts["seal"] = new_seal(sessions=len(chats))   # issue #21: satirlar sekmede muhurlenir; anahtar kullanici durum klasorunde
    # ensure_ascii=True: Turkce karakterler \u kacisi olur; pano/konsol ASCII kalir
    js = "window.__WA_OPTS = " + json.dumps(opts, ensure_ascii=True) + ";\n" + read_collector()
    copied = copy_to_clipboard(js)
    print(js)
    print(wa2md.t("web_snippet_ready", kb=len(js) // 1024,
                  copied=wa2md.t("web_copied" if copied else "web_not_copied")) + wa2md.t("web_snippet_steps"),
          file=sys.stderr)
    return 0


def anon_kwargs(args):
    """wa2md.add_anonim_args seceneklerini import_bundles'a aktarir (wa2md.main ile ayni anlam)."""
    return {"extra_names": getattr(args, "extra_names", None), "review_dir": getattr(args, "review_dir", None),
            "no_dict": bool(getattr(args, "no_dict", False))}


def cmd_import(args):
    if args.anonim:
        rc = wa2md.anonim_preflight(args, args.out)   # wa2md ile ayni on denetim: sozluk, inceleme klasoru
        if rc:
            return rc
    done, _ = import_bundles(args.paths, args.out, args.date_from, args.date_to, args.max_messages,
                             anonim=args.anonim, no_media=args.no_media, keep_bundles=args.keep_bundles,
                             **anon_kwargs(args))
    return 0 if done else 1


# ------------------------------------------------------------------ SECTION: CDP tasimasi (deneysel)
class NotReady(Exception):
    pass


def default_user_data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.environ.get("WA_CHROME_USER_DATA_DIR") or os.path.join(base, "Google", "Chrome", "User Data")


def read_ws_endpoint(user_data_dir):
    """DevToolsActivePort (satir1 port, satir2 yol) -> ws://127.0.0.1:port/yol."""
    p = os.path.join(user_data_dir, "DevToolsActivePort")
    try:
        with open(p, encoding="utf-8") as f:
            lines = [l.strip() for l in f.read().split("\n") if l.strip()]
    except OSError:
        raise NotReady(wa2md.t("web_required_step")) from None
    try:
        port = int(lines[0])
        path = lines[1]
    except (IndexError, ValueError):
        raise NotReady(wa2md.t("web_bad_port_file", path=p) + "\n" + wa2md.t("web_required_step")) from None
    return f"ws://127.0.0.1:{port}{path}"


def attach(pw, user_data_dir, timeout_ms=120000):
    """Calisan Chrome'a baglan; web.whatsapp.com sekmesini bul, yoksa AYNI tarayicida bir sekme ac.
    -> (browser, page, opened_by_us)"""
    ws = read_ws_endpoint(user_data_dir)
    print(wa2md.t("web_connecting"), flush=True)
    try:
        browser = pw.chromium.connect_over_cdp(ws, timeout=timeout_ms)
    except Exception as e:  # noqa: BLE001
        raise NotReady(wa2md.t("web_connect_failed", kind=type(e).__name__) + "\n" + wa2md.t("web_required_step")) from None
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    for pg in ctx.pages:
        if pg.url.startswith("https://web.whatsapp.com"):
            return browser, pg, False
    pg = ctx.new_page()
    pg.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")
    return browser, pg, True


def inject_collector(page):
    page.evaluate(read_collector())  # IIFE: window.__waCollect tanimlar (WA_OPTS yok -> otomatik calismaz)


def list_chats(page):
    inject_collector(page)
    return page.evaluate("() => window.__waCollect.listChats()")


def export_chat_cdp(page, name, args, staging, seal_cfg=None):
    """Ayni wa_collect.js'i sayfada calistirir; paketleri staging'e yazar. -> sonuc dict"""
    os.makedirs(staging, exist_ok=True)
    hold = getattr(page, "_wa_hold", None)
    if hold is None:  # sayfa basina bir kez (ayni sayfada birden cok sohbet)
        hold = page._wa_hold = {"dir": staging}

        def on_part(part_json, fname):
            with open(os.path.join(hold["dir"], os.path.basename(fname)), "w", encoding="utf-8") as f:
                f.write(part_json)

        page.expose_function("waEmit", on_part)
        if not wa2md.redact_console(args):  # toplayici ilerleme satirlari sohbet adi icerir: anonimde yutulur
            page.on("console", lambda m: print(m.text, flush=True) if m.text.startswith("[wa]") else None)
    hold["dir"] = staging
    inject_collector(page)
    opts = collector_opts(args, [name])
    if seal_cfg:
        opts["seal"] = seal_cfg   # yalniz bellekte (CDP): staging'e de muhurlu parca yazilir
    return page.evaluate(
        "async (o) => { o.emit = (p, n) => window.waEmit(JSON.stringify(p), n);"
        " return await window.__waCollect.run(o); }", opts)


def run_with_page(args, fn):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"{wa2md.t('err')}: " + wa2md.t("web_no_playwright"), file=sys.stderr)
        return 2
    with sync_playwright() as pw:
        try:
            browser, page, ours = attach(pw, args.user_data_dir or default_user_data_dir())
            try:
                return fn(page)
            finally:
                if ours:
                    page.close()  # yalniz bizim actigimiz sekme; kullanicinin sekmelerine dokunulmaz
        except NotReady as e:
            print(f"{wa2md.t('err')}: {e}", file=sys.stderr)
            return 2


def cmd_list(args):
    def go(page):
        names = list_chats(page)
        for n in names:
            print(n)
        print(wa2md.t("web_total", n=len(names)), file=sys.stderr)
        return 0
    return run_with_page(args, go)


def _stop_pressed(page):
    """True when "Stop and save" was pressed (or __waCollect.stop() run) after the previous chat's run ended."""
    try:
        return bool(page.evaluate("() => !!(window.__waCollect && window.__waCollect.stopped && window.__waCollect.stopped())"))
    except Exception:  # noqa: BLE001 - tab gone: the next collection reports it
        return False


def _salvage_staging(staging, args, chat_start, ref_no, seal_keys=None):
    """Convert the parts of a collection that did not finish (issue #20): checkpoints keep what was collected.
    Parts that cannot be converted (no checkpoint yet) stay in the staging folder, whose
    path is printed so that `import` can be run on it later. -> number of chats written"""
    if not find_bundle_files([staging]):
        return 0
    print(wa2md.t("web_salvage"))
    d, _ = import_bundles([staging], args.out, args.date_from, args.date_to, args.max_messages,
                          anonim=getattr(args, "anonim", True), chat_start=chat_start,
                          no_media=bool(getattr(args, "no_media", False)), ref_start=ref_no, seal_keys=seal_keys,
                          keep_incomplete=False, **anon_kwargs(args))
    return d   # no final part follows in this path: import_bundles deleted the parts it converted


def _remove_staging(staging):
    """Remove the staging folder unless bundle parts are left in it (they hold the chat: tell the user where)."""
    if find_bundle_files([staging]):
        print(wa2md.t("web_parts_left", path=staging))
        return
    shutil.rmtree(staging, ignore_errors=True)


def cmd_export(args):
    wanted = split_chats(args.chats)
    if not wanted:
        print(f"{wa2md.t('err')}: " + wa2md.t("web_chats_empty"), file=sys.stderr)
        return 2
    if getattr(args, "anonim", True):
        rc = wa2md.anonim_preflight(args, args.out)
        if rc:
            return rc

    seal_cfg = new_seal(store=False)
    keys = {seal_cfg["kid"]: bytes.fromhex(seal_cfg["key"])}

    def go(page):
        done = failed = 0
        red = wa2md.redact_console(args)
        for i, name in enumerate(wanted, 1):
            if i > 1 and _stop_pressed(page):
                print(wa2md.t("web_run_stopped", n=len(wanted) - i + 1))
                break
            staging = tempfile.mkdtemp(prefix="wa_cdp_")
            collected = False   # collection finished without error: the normal import below converts it
            stopped = False
            try:
                try:
                    status = export_chat_cdp(page, name, args, staging, seal_cfg)
                except NotReady:
                    raise
                except Exception as e:  # noqa: BLE001
                    if not red:
                        raise
                    print(f"{wa2md.t('err')} [{wa2md.t('ref_input', n=i)}]: " + wa2md.t("web_collect_failed_kind", kind=type(e).__name__),
                          file=sys.stderr)
                    failed += 1
                    continue
                res = (status.get("results") or [{}])[0] if status else {}
                stopped = bool(status and status.get("stopped"))
                if status.get("state") != "done" or res.get("error"):
                    failed_msg = wa2md.t("web_collect_failed")
                    detail = failed_msg if red else (status.get('error') or res.get('error') or failed_msg)
                    print(f"{wa2md.t('err')} [{wa2md.t('ref_input', n=i) if red else name}]: {detail}", file=sys.stderr)
                    failed += 1
                    continue
                collected = True
                d, f = import_bundles([staging], args.out, args.date_from, args.date_to, args.max_messages,
                                      anonim=getattr(args, "anonim", True), chat_start=done + 1,
                                      no_media=bool(getattr(args, "no_media", False)),
                                      ref_start=i, seal_keys=keys, **anon_kwargs(args))
                done += d
                failed += f
            finally:
                # A failed or cut-short collection (tab closed, error) leaves checkpoints in the staging folder (issue #20):
                # convert what was collected (masked as usual); whatever cannot be converted stays on disk and is announced.
                if not collected:
                    done += _salvage_staging(staging, args, done + 1, i, keys)
                _remove_staging(staging)
            if stopped:   # "Stop and save" ends the whole run, not only the current chat (issue #20)
                if i < len(wanted):
                    print(wa2md.t("web_run_stopped", n=len(wanted) - i))
                break
        print(wa2md.t("web_done", done=done, failed=failed))
        return 0 if done else 1
    return run_with_page(args, go)


# ------------------------------------------------------------------ SECTION: arguman ayristirma
def parse_date(s):
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(wa2md.t("bad_date", value=s))


def add_filter_args(p, with_media=True):
    p.add_argument("--from", dest="date_from", type=parse_date, help="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", type=parse_date, help="YYYY-MM-DD")
    p.add_argument("--max-messages", type=int, help=wa2md.t("help_max_messages"))
    if with_media:
        p.add_argument("--no-media", "--medya-yok", dest="no_media", action="store_true",
                       help=wa2md.t("help_web_no_media"))
        p.add_argument("--no-video", "--video-yok", dest="no_video", action="store_true",
                       help=wa2md.t("help_web_no_video"))
        p.add_argument("--older-from-phone", action="store_true", help=wa2md.t("help_older_from_phone"))
        p.add_argument("--checkpoint-minutes", type=float, default=10, metavar="N", help=wa2md.t("help_checkpoint_minutes"))


def build_parser():
    ap = argparse.ArgumentParser(description=wa2md.t("help_web_description"))
    ap.add_argument("--user-data-dir", help=wa2md.t("help_user_data_dir"))
    wa2md.add_lang_arg(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sn = sub.add_parser("snippet", help=wa2md.t("help_snippet"))
    sn.add_argument("--chats", required=True, help=wa2md.t("help_chats"))
    add_filter_args(sn)
    wa2md.add_lang_arg(sn)
    im = sub.add_parser("import", help=wa2md.t("help_import"))
    im.add_argument("paths", nargs="+", help=wa2md.t("help_bundle_paths"))
    im.add_argument("--out", required=True, help=wa2md.t("help_out"))
    add_filter_args(im, with_media=False)
    im.add_argument("--no-media", "--medya-yok", dest="no_media", action="store_true",
                    help=wa2md.t("help_web_import_no_media"))
    im.add_argument("--keep-bundles", "--paketleri-sakla", dest="keep_bundles", action="store_true",
                    help=wa2md.t("help_keep_bundles"))
    wa2md.add_anonim_args(im)
    wa2md.add_lang_arg(im)
    lc = sub.add_parser("list", help=wa2md.t("help_list"))
    wa2md.add_lang_arg(lc)
    ex = sub.add_parser("export", help=wa2md.t("help_export"))
    ex.add_argument("--chats", required=True, help=wa2md.t("help_chats"))
    ex.add_argument("--out", required=True, help=wa2md.t("help_out"))
    add_filter_args(ex)
    wa2md.add_anonim_args(ex)
    wa2md.add_lang_arg(ex)
    return ap


def main(argv=None):
    try:
        return _main(argv)
    finally:
        wa2md.reset_lang()


def _main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    wa2md.init_lang(argv)
    ap = build_parser()
    args = ap.parse_args(argv)
    wa2md.check_packs_env(ap)
    return {"snippet": cmd_snippet, "import": cmd_import, "list": cmd_list, "export": cmd_export}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
