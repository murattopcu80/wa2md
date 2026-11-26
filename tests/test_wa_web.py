"""wa_web.py (paket -> Markdown) ve wa_collect.js (DOM ayristirma) testleri.

DOM ayristirma testleri ayni wa_collect.js'i gercek (basliksiz) Chrome'da calistirir; fixture'lar 14.11.2026'da
gercek WhatsApp Web DOM'unda gozlenen yapiyi UYDURMA metinlerle taklit eder (tests/fixtures/web).
Chrome/playwright yoksa tarayici testleri atlanir; saf Python testleri her zaman kosar."""
import base64
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "fixtures", "web")
sys.path.insert(0, os.path.dirname(HERE))
import _pin  # noqa: E402  (Turkish pack set and labels, issue #2)
import wa2md  # noqa: E402
import wa_web  # noqa: E402


_ENV = {}


def setUpModule():
    """Inceleme dosyasi varsayilan olarak kullanici durum klasorune gider: testlerde gecici klasor."""
    _pin.pin()
    # these tests assert the Turkish console text: pin the message table to Turkish (English is covered by test_i18n.py)
    _ENV["old_lang"] = os.environ.get("WA2MD_LANG")
    os.environ["WA2MD_LANG"] = "tr"
    _ENV["old"] = os.environ.get("XDG_STATE_HOME")
    _ENV["dir"] = tempfile.mkdtemp(prefix="wa2md-state-")
    os.environ["XDG_STATE_HOME"] = _ENV["dir"]


def tearDownModule():
    if _ENV["old_lang"] is None:
        os.environ.pop("WA2MD_LANG", None)
    else:
        os.environ["WA2MD_LANG"] = _ENV["old_lang"]
    if _ENV["old"] is None:
        os.environ.pop("XDG_STATE_HOME", None)
    else:
        os.environ["XDG_STATE_HOME"] = _ENV["old"]
    shutil.rmtree(_ENV["dir"], ignore_errors=True)
    _pin.unpin()

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
# WA2MD_TEST_CHROME: path of a Chrome / Chromium for the browser tests (default: the usual Windows install)
CHROME = os.environ.get("WA2MD_TEST_CHROME") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
TODAY = dt.date(2026, 11, 16)  # Pazartesi


def html(name):
    with open(os.path.join(WEB, name + ".html"), encoding="utf-8") as f:
        return f.read()


def synth(i, **kw):
    """Elle yazilmis paket satiri (parseRow ciktisi bicimi)."""
    r = {"id": "AC%030d" % i, "system": None, "out": False, "stamp": None, "meta": None, "author": None, "text": "",
         "quote": None, "deleted": False, "forwarded": False, "media": [], "divider": None}
    r.update(kw)
    return r


# ------------------------------------------------------------------ saf Python
class Dividers(unittest.TestCase):
    def test_formats(self):
        p = wa_web.parse_divider
        self.assertEqual(p("07.11.2026", TODAY), ("raw", (7, 11, 2026)))
        self.assertEqual(p("BUGÜN", TODAY), ("date", TODAY))
        self.assertEqual(p("Dün", TODAY), ("date", dt.date(2026, 11, 15)))
        self.assertEqual(p("Perşembe", TODAY), ("date", dt.date(2026, 11, 12)))
        self.assertEqual(p("SALI", TODAY), ("date", dt.date(2026, 11, 10)))
        self.assertEqual(p("Salı", TODAY), ("date", dt.date(2026, 11, 10)))
        self.assertEqual(p("Yesterday", TODAY), ("date", dt.date(2026, 11, 15)))
        self.assertIsNone(p("Okunmamış", TODAY))

    def test_media_only_gets_date_from_divider_and_time_from_meta(self):
        rows = [synth(1, meta="14:20wds-ic-read", out=True, divider="13.11.2026", media=[{"kind": "image", "key": None, "label": ""}])]
        (m,) = wa_web.build_messages(rows, "Grup", TODAY, no_media=True)
        self.assertEqual(m["dt"], dt.datetime(2026, 11, 13, 14, 20))

    def test_divider_word_resolves_relative_to_export_day(self):
        rows = [synth(1, meta="09:05", divider="Dün", text="x")]
        (m,) = wa_web.build_messages(rows, "G", TODAY)
        self.assertEqual(m["dt"], dt.datetime(2026, 11, 15, 9, 5))

    def test_media_only_between_rows_inherits_neighbour_date(self):
        rows = [synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="a"), synth(2, meta="14:20", text="b"),
                synth(3, stamp="[14:30, 14.11.2026] Naime: ", text="c")]
        msgs = wa_web.build_messages(rows, "G", TODAY)
        self.assertEqual(msgs[1]["dt"], dt.datetime(2026, 11, 14, 14, 20))

    def test_media_only_after_midnight_goes_to_next_day(self):
        rows = [synth(1, stamp="[23:50, 14.11.2026] Naime: ", text="a"), synth(2, meta="00:10", text="b"),
                synth(3, stamp="[00:30, 15.11.2026] Naime: ", text="c")]
        msgs = wa_web.build_messages(rows, "G", TODAY)
        self.assertEqual(msgs[1]["dt"], dt.datetime(2026, 11, 15, 0, 10))

    def test_us_date_order_detected(self):
        rows = [synth(1, stamp="[2:05 PM, 11/14/2026] Jane: ", text="x")]
        (m,) = wa_web.build_messages(rows, "J", TODAY)
        self.assertEqual(m["dt"], dt.datetime(2026, 11, 14, 14, 5))


class Build(unittest.TestCase):
    def test_sender_rules(self):
        rows = [synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="a"),
                synth(2, stamp="[14:06, 14.11.2026] Deniz Test: ", text="b", out=True),
                synth(3, meta="14:07", author="Mehmet Kaya", media=[{"kind": "image", "key": None, "label": ""}], divider="14.11.2026"),
                synth(4, meta="14:08", out=True, divider="14.11.2026", media=[{"kind": "image", "key": None, "label": ""}]),
                synth(5, meta="14:09", divider="14.11.2026", media=[{"kind": "image", "key": None, "label": ""}])]
        msgs = wa_web.build_messages(rows, "Sohbet", TODAY, no_media=True)
        # giden damgasiz satir: kendi ad (giden damgadan), gelen damgasiz: etiket yoksa sohbet basligi
        self.assertEqual([m["sender"] for m in msgs], ["Naime", "Deniz Test", "Mehmet Kaya", "Deniz Test", "Sohbet"])

    def test_system_rows_and_encryption_note(self):
        rows = [synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="a"),
                synth(2, system="Bu sohbetteki mesajlar uçtan uca şifrelidir."), synth(3, system="Mehmet gruba katıldı")]
        msgs = wa_web.build_messages(rows, "Sohbet", TODAY)
        self.assertEqual([m["sender"] for m in msgs], ["Naime", None])
        self.assertEqual(msgs[1]["parts"], [("text", "Mehmet gruba katıldı")])

    def test_parts_quote_forwarded_deleted_document(self):
        doc = {"kind": "document", "key": None, "label": '"rapor.pdf" dosyasını indir'}
        rows = [synth(1, stamp="[14:05, 14.11.2026] A: ", text="Cevap", quote="Naime: Merhaba", forwarded=True),
                synth(2, stamp="[14:06, 14.11.2026] A: ", deleted=True),
                synth(3, stamp="[14:07, 14.11.2026] A: ", media=[doc])]
        msgs = wa_web.build_messages(rows, "S", TODAY)
        self.assertEqual(msgs[0]["parts"], [("note", "Yönlendirilmiş mesaj"), ("quote", "Naime: Merhaba"), ("text", "Cevap")])
        self.assertEqual(msgs[1]["parts"], [("note", "Bu mesaj silindi")])
        self.assertEqual(msgs[2]["parts"], [("note", "belge indirilemedi: rapor.pdf")])

    def test_no_media_flag(self):
        img = {"kind": "image", "key": None, "label": ""}
        rows = [synth(1, stamp="[14:05, 14.11.2026] A: ", text="Açıklama", media=[img, img])]
        (m,) = wa_web.build_messages(rows, "S", TODAY, no_media=True)
        self.assertEqual(m["parts"], [("omitted", None), ("text", "Açıklama")])

    def test_no_video_marks_video_gif_and_audio_not_exported(self):
        kinds = [{"kind": k, "key": None, "label": ""} for k in ("video", "gif", "audio", "image")]
        rows = [synth(i + 1, stamp=f"[14:0{i}, 14.11.2026] A: ", media=[md]) for i, md in enumerate(kinds)]
        msgs = wa_web.build_messages(rows, "S", TODAY, no_video=True)
        self.assertEqual([m["parts"] for m in msgs[:3]], [[("note", "[video: aktarılmadı]")], [("note", "[gif: aktarılmadı]")],
                                                       [("note", "[ses: aktarılmadı]")]])
        self.assertEqual(msgs[3]["parts"][0][0], "file")   # fotograf etkilenmez (eksikse dosya eksik isaretcisi)
        msgs = wa_web.build_messages(rows, "S", TODAY)        # secenek yokken eski davranis
        self.assertEqual(msgs[0]["parts"], [("note", "video indirilemedi: video")])

    def test_album_files_get_numbered_stems_and_missing_marker(self):
        img = {"kind": "image", "key": None, "label": ""}
        rows = [synth(1, stamp="[14:05, 14.11.2026] A: ", media=[img, img])]
        (m,) = wa_web.build_messages(rows, "S", TODAY)
        self.assertEqual([k for k, _ in m["parts"]], ["file", "file"])
        self.assertTrue(m["parts"][0][1].endswith("-1.jpg") and m["parts"][1][1].endswith("-2.jpg"))

    def test_filter_from_to_max(self):
        rows = [synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="a"), synth(2, stamp="[14:06, 14.11.2026] B: ", text="b"),
                synth(3, stamp="[10:00, 15.11.2026] Naime: ", text="c")]
        msgs = wa_web.build_messages(rows, "S", TODAY)
        f = wa_web.filter_messages
        self.assertEqual(len(f(msgs, dt.date(2026, 11, 15))), 1)
        self.assertEqual(len(f(msgs, None, dt.date(2026, 11, 14))), 2)
        self.assertEqual([m["sender"] for m in f(msgs, max_messages=2)], ["B", "Naime"])
        self.assertEqual(len(f(msgs, dt.date(2026, 11, 16))), 0)

    def test_doc_name(self):
        self.assertEqual(wa_web.doc_name('"a b.zip" dosyasını indir'), "a b.zip")
        self.assertEqual(wa_web.doc_name("düz ad.pdf"), "düz ad.pdf")
        self.assertEqual(wa_web.doc_name(None), "")


class Attach(unittest.TestCase):
    def test_missing_port_file_points_to_snippet_route(self):
        d = tempfile.mkdtemp()
        try:
            with self.assertRaises(wa_web.NotReady) as cm:
                wa_web.read_ws_endpoint(d)
            msg = str(cm.exception)
            self.assertIn("chrome://inspect/#remote-debugging", msg)
            self.assertIn("snippet", msg)
            self.assertIn("import", msg)
        finally:
            shutil.rmtree(d)

    def test_endpoint_from_devtools_active_port(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "DevToolsActivePort"), "w") as f:
                f.write("61545\n/devtools/browser/abc-123\n")
            self.assertEqual(wa_web.read_ws_endpoint(d), "ws://127.0.0.1:61545/devtools/browser/abc-123")
            with open(os.path.join(d, "DevToolsActivePort"), "w") as f:
                f.write("garbage")
            with self.assertRaises(wa_web.NotReady):
                wa_web.read_ws_endpoint(d)
        finally:
            shutil.rmtree(d)


class Snippet(unittest.TestCase):
    def run_snippet(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        real_clip = wa_web.copy_to_clipboard
        wa_web.copy_to_clipboard = lambda text: False
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = wa_web.main(["snippet", *argv])
        finally:
            wa_web.copy_to_clipboard = real_clip
        return rc, out.getvalue(), err.getvalue()

    def test_no_video_option_and_turkish_alias(self):
        for flag in ("--no-video", "--video-yok"):
            with self.subTest(flag=flag):
                rc, out, _ = self.run_snippet("--chats", "Naime", flag)
                self.assertEqual(rc, 0)
                opts = json.loads(out.split(";\n", 1)[0][len("window.__WA_OPTS = "):])
                self.assertEqual((opts["noVideo"], opts["noMedia"]), (True, False))

    def test_options_baked_in_and_ascii_only(self):
        rc, out, err = self.run_snippet("--chats", "Naime,Aile grubu", "--from", "2026-11-01", "--max-messages", "50",
                                        "--no-media")
        self.assertEqual(rc, 0)
        self.assertTrue(out.isascii())  # panoya/konsola guvenli
        head = out.split(";\n", 1)[0]
        opts = json.loads(head[len("window.__WA_OPTS = "):])
        self.assertEqual(opts["chats"], ["Naime", "Aile grubu"])
        self.assertEqual((opts["from"], opts["to"], opts["max"], opts["noMedia"], opts["olderFromPhone"]),
                         ("2026-11-01", None, 50, True, False))
        self.assertFalse(opts["noVideo"])
        self.assertIn("__waCollect", out)  # toplayici dosyanin kendisi gomulu
        self.assertIn("allow pasting", err)
        self.assertEqual(opts["checkpointMin"], 10)   # issue #20: varsayilan ara kayit araligi
        seal = opts["seal"]                             # issue #21: kosu anahtari durum klasorunde
        self.assertEqual(wa_web.load_key(seal["kid"]), bytes.fromhex(seal["key"]))

    def test_checkpoint_minutes_option(self):
        rc, out, _ = self.run_snippet("--chats", "Naime", "--checkpoint-minutes", "0")
        self.assertEqual(rc, 0)
        opts = json.loads(out.split(";\n", 1)[0][len("window.__WA_OPTS = "):])
        self.assertEqual(opts["checkpointMin"], 0)

    def test_empty_chats_rejected(self):
        rc, _, err = self.run_snippet("--chats", " , ")
        self.assertEqual(rc, 2)
        self.assertIn("--chats", err)


class Bundles(unittest.TestCase):
    """Paket dosyalari -> Markdown (konsol yolunun Python yarisi)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def part(self, no, final=False, rows=None, media=None, total=None, session="abc123", chat="Naime", **extra):
        p = {"format": "wa-web-bundle", "version": 1, "session": session, "part": no, "chat": chat, "final": final,
             "media": media or []}
        if final:
            p.update({"total": total or no, "rows": rows or [], "today": "2026-11-16", "opts": {}})
        elif rows is not None:   # ara kayit (snapshot)
            p["rows"] = rows
        p.update(extra)
        path = os.path.join(self.tmp, f"wa-bundle-naime-{session}-{no:03d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f)
        return path

    def run_import(self, *paths, **kw):
        with redirect_stdout(io.StringIO()) as o, redirect_stderr(io.StringIO()) as e:
            res = wa_web.import_bundles(list(paths), self.out, **kw)
        return res, o.getvalue(), e.getvalue()

    def md(self, name="Naime"):
        with open(os.path.join(self.out, name, name + ".md"), encoding="utf-8") as f:
            return f.read()

    def img(self, key, data=b"\xff\xd8jpegdata"):
        return {"key": key, "mime": "image/jpeg", "b64": base64.b64encode(data).decode()}

    def test_media_warning_on_the_web_path_when_anonymized(self):
        rows = [synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Bak",
                      media=[{"kind": "image", "key": "AAAA0001-1", "label": ""}])]
        a = self.part(1, final=True, rows=rows, total=1, media=[self.img("AAAA0001-1")])
        res, out, err = self.run_import(a, anonim=True)
        self.assertEqual(res, (1, 0), err)
        self.assertIn("   UYARI: 1 medya/ek dosyası olduğu gibi kopyalandı ve anonimleştirilmedi", out)
        self.assertEqual(out.count("anonimleştirilmedi"), 1)

    def test_two_part_bundle_with_media(self):
        rows = [synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Merhaba"),
                synth(2, stamp="[14:10, 14.11.2026] Naime: ", text="Bak", media=[{"kind": "image", "key": "AAAA0002-1", "label": ""}]),
                synth(3, meta="14:12", out=True, stamp=None, divider="14.11.2026",
                      media=[{"kind": "image", "key": "AAAA0003-1", "label": ""}, {"kind": "image", "key": "AAAA0003-2", "label": ""}])]
        a = self.part(1, media=[self.img("AAAA0002-1")])
        b = self.part(2, final=True, rows=rows, total=2, media=[self.img("AAAA0003-1"), self.img("AAAA0003-2", b"x")])
        (res, out, err) = self.run_import(b, a)  # sira onemli degil
        self.assertEqual(res, (1, 0))
        self.assertIn("3 mesaj, 3 medya kopyalandı, 0 medya eksik", out)
        md = self.md()
        self.assertNotIn("olduğu gibi kopyalandı ve anonimleştirilmedi", out)  # not anonymized: no media warning
        self.assertIn("**Naime** 14:05\nMerhaba", md)
        self.assertEqual(md.count("![](media/20261114-"), 3)
        self.assertEqual(len(os.listdir(os.path.join(self.out, "Naime", "media"))), 3)

    def test_folder_input_groups_sessions_and_reports_missing_part(self):
        self.part(1, media=[self.img("K1")])  # son parca yok / eksik
        self.part(2, final=True, total=3, rows=[synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")])
        (res, out, err) = self.run_import(self.tmp)
        self.assertEqual(res, (0, 1))
        self.assertIn("Eksik paket parçası: 3", err)

    def test_explicit_file_with_guid_name_is_recognised_by_its_header(self):
        # Chrome'un "yeni sekmede indir" yedek yolu dosyaya rastgele (GUID) ad verir; klasorde yok sayilir, acikca verilince okunur
        p = self.part(1, final=True, rows=[synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Merhaba")])
        guid = os.path.join(self.tmp, "c95cbe4e-c105-4089-927c-45de3330cccc")
        os.replace(p, guid)
        (res, out, err) = self.run_import(self.tmp)
        self.assertEqual(res, (0, 1))
        (res, out, err) = self.run_import(guid)
        self.assertEqual(res, (1, 0))
        self.assertIn("**Naime** 14:05\nMerhaba", self.md())

    def test_no_final_part(self):
        p = self.part(1, media=[self.img("K1")])
        (res, out, err) = self.run_import(p)
        self.assertEqual(res, (0, 1))
        self.assertIn("Son paket", err)

    def test_unsafe_media_key_ignored(self):
        evil = self.img("../evil")
        p = self.part(1, final=True, media=[evil], rows=[synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")])
        res, _, _ = self.run_import(p)
        self.assertEqual(res, (1, 0))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil.tmp")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "evil.tmp")))

    def test_filters_and_bundle_options(self):
        rows = [synth(1, stamp="[14:05, 13.11.2026] A: ", text="eski"), synth(2, stamp="[14:05, 14.11.2026] A: ", text="yeni")]
        p = self.part(1, final=True, rows=rows)
        res, out, _ = self.run_import(p, date_from=dt.date(2026, 11, 14))
        self.assertEqual(res, (1, 0))
        md = self.md()
        self.assertNotIn("eski", md)
        self.assertIn("yeni", md)

    # ---- issue #20: checkpoints, stop, deleting converted bundles
    def snap(self, no, rows, media_parts, **extra):
        """Ara kayit parcasi (bicim 2): o ana kadarki tum satirlar; yalniz yazilmis medya parcalarina dayanir."""
        return self.part(no, rows=rows, version=2, snapshot=True, mediaParts=media_parts, today="2026-11-16", opts={},
                         **extra)

    def test_unfinished_collection_imports_the_newest_checkpoint(self):
        r1 = synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Bak", media=[{"kind": "image", "key": "AAAA0001-1", "label": ""}])
        r2 = synth(2, stamp="[14:06, 14.11.2026] Naime: ", text="Ikinci ara kayitta")
        self.part(1, media=[self.img("AAAA0001-1")], version=2)
        self.snap(2, [r1], [1])
        self.snap(3, [r1, r2], [1])                      # son parca yok: sekme kapandi
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertIn("2 mesaj, 1 medya kopyalandı, 0 medya eksik", out)
        self.assertIn("en yeni ara kayıt (parça 3) kullanıldı", out)
        self.assertIn("Ikinci ara kayitta", self.md())

    def test_final_part_needs_only_its_media_parts_not_older_checkpoints(self):
        r1 = synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Bak", media=[{"kind": "image", "key": "AAAA0001-1", "label": ""}])
        a = self.part(1, media=[self.img("AAAA0001-1")], version=2)
        b = self.part(4, final=True, total=4, rows=[r1], version=2, mediaParts=[1])   # 2 ve 3: indirilmemis eski ara kayitlar
        res, out, err = self.run_import(a, b)
        self.assertEqual(res, (1, 0), err)
        self.assertNotIn("ara kayıt", out)

    def test_checkpoint_without_its_media_part_is_reported(self):
        self.snap(2, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], [1])
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (0, 1))
        self.assertIn("Eksik paket parçası: 1", err)

    def test_stopped_collection_is_noted(self):
        p = self.part(1, final=True, rows=[synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], version=2, mediaParts=[],
                      stopped=True)
        res, out, err = self.run_import(p)
        self.assertEqual(res, (1, 0), err)
        self.assertIn("toplama erken durduruldu", out)

    def test_converted_bundles_are_deleted_unless_kept(self):
        rows = [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")]
        a = self.part(1, media=[self.img("K1")])
        b = self.part(2, final=True, total=2, rows=rows)
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertFalse(os.path.exists(a) or os.path.exists(b))
        self.assertIn("Dönüştürülen 2 paket dosyası silindi", out)
        self.assertNotIn("naime", out.lower().split("silindi")[1])   # konsola dosya adi (sohbet adi) yazilmaz
        a = self.part(1, media=[self.img("K1")])
        b = self.part(2, final=True, total=2, rows=rows)
        shutil.rmtree(self.out)
        res, out, err = self.run_import(self.tmp, keep_bundles=True)
        self.assertEqual(res, (1, 0), err)
        self.assertTrue(os.path.exists(a) and os.path.exists(b))
        self.assertNotIn("silindi", out)

    def test_incomplete_session_keeps_its_parts_until_the_final_part_arrives(self):
        """Issue #20 review: only a checkpoint reached the folder (Chrome blocked the second download): converting it
        must not delete the parts; the final part downloaded later then imports and gives the complete chat."""
        r1 = synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Bak", media=[{"kind": "image", "key": "AAAA0001-1", "label": ""}])
        r2 = synth(2, stamp="[14:06, 14.11.2026] Naime: ", text="Ikinci")
        r3 = synth(3, stamp="[14:07, 14.11.2026] Naime: ", text="Ucuncu satir")
        a = self.part(1, media=[self.img("AAAA0001-1")], version=2)
        b = self.snap(2, [r1, r2], [1])
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertTrue(os.path.exists(a) and os.path.exists(b))          # parts stay: the session is not finished
        self.assertNotIn("silindi", out)
        self.assertNotIn("Ucuncu satir", self.md())
        c = self.part(3, final=True, total=3, rows=[r1, r2, r3], version=2, mediaParts=[1])
        shutil.rmtree(self.out)
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertNotIn("Eksik paket", err)
        self.assertIn("Ucuncu satir", self.md())
        self.assertEqual(len(os.listdir(os.path.join(self.out, "Naime", "media"))), 1)
        self.assertFalse(any(os.path.exists(p) for p in (a, b, c)))        # now complete: all three deleted

    def test_failed_sessions_keep_their_bundles(self):
        no_final = self.part(1, media=[self.img("K1")], session="aaa111")
        empty = self.part(1, final=True, rows=[synth(1, stamp="[14:05, 13.11.2026] A: ", text="eski")], session="bbb222")
        res, out, err = self.run_import(self.tmp, date_from=dt.date(2026, 11, 14))
        self.assertEqual(res, (0, 2))
        self.assertTrue(os.path.exists(no_final) and os.path.exists(empty))

    # ---- issue #21: sealed bundles (rows and chat title encrypted in the tab)
    def sealed_part(self, no, rows, cfg, session="abc123", chat="Naime", final=True, snapshot=False, media_parts=(), **extra):
        p = {"format": "wa-web-bundle", "version": 2, "session": session, "part": no, "final": final, "media": [],
             "mediaParts": list(media_parts), "today": "2026-11-16", "opts": {}}
        if snapshot:
            p["snapshot"] = True
        if final:
            p["total"] = no
        p.update(extra)
        p["sealed"] = wa_web.seal({"chat": chat, "rows": rows}, bytes.fromhex(cfg["key"]), cfg["kid"],
                                  aad=wa_web.header_aad(p))
        path = os.path.join(self.tmp, f"wa-bundle-sealed-{session}-{no:03d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f)
        return path

    def edit_part(self, path, **changes):
        with open(path, encoding="utf-8") as f:
            part = json.load(f)
        part.update(changes)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(part, f)

    def key_exists(self, cfg):
        return os.path.exists(self.key_path(cfg))

    def key_path(self, cfg):
        return os.path.join(wa_web._key_dir(), cfg["kid"] + ".key")

    def test_seal_round_trip_and_tamper_check(self):
        key, kid = bytes(range(32)), "000000000000000a"
        obj = {"chat": "Naime Çağ 🚚", "rows": [synth(1, text="Şifre: x")]}
        aad = wa_web.header_aad({"session": "abc123", "part": 2, "final": False, "snapshot": True, "mediaParts": [1]})
        box = wa_web.seal(obj, key, kid, aad=aad)
        self.assertEqual(wa_web.unseal(box, key, aad), obj)
        for other in ({"session": "abc124", "part": 2, "final": False, "snapshot": True, "mediaParts": [1]},   # session
                      {"session": "abc123", "part": 3, "final": False, "snapshot": True, "mediaParts": [1]},   # part number
                      {"session": "abc123", "part": 2, "final": True, "snapshot": True, "mediaParts": [1]},    # final flag
                      {"session": "abc123", "part": 2, "final": False, "snapshot": False, "mediaParts": [1]},  # snapshot flag
                      {"session": "abc123", "part": 2, "final": False, "snapshot": True, "mediaParts": []}):   # media part list
            with self.assertRaises(ValueError, msg=other):
                wa_web.unseal(box, key, wa_web.header_aad(other))
        bad = dict(box, ct=base64.b64encode(bytes([base64.b64decode(box["ct"])[0] ^ 1]) + base64.b64decode(box["ct"])[1:]).decode())
        with self.assertRaises(ValueError):
            wa_web.unseal(bad, key, aad)
        with self.assertRaises(ValueError):
            wa_web.unseal(box, bytes(32), aad)

    def test_sealed_bundle_holds_no_text_imports_and_drops_its_key(self):
        cfg = wa_web.new_seal()
        self.assertTrue(os.path.isfile(self.key_path(cfg)))
        if os.name == "posix":
            self.assertEqual(os.stat(self.key_path(cfg)).st_mode & 0o777, 0o600)
        p = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Gizli metin 12345")], cfg)
        with open(p, encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("Gizli", raw)
        self.assertNotIn("Naime", raw)                       # sohbet adi ne baslikta ne dosya adinda
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertIn("Gizli metin 12345", self.md())
        self.assertFalse(os.path.exists(p))
        self.assertFalse(os.path.exists(self.key_path(cfg)))   # anahtar kullanildi: eski kopyalar artik acilmaz

    def test_sealed_bundle_without_its_key_fails_and_keeps_files(self):
        cfg = wa_web.new_seal(store=False)
        p = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], cfg)
        res, out, err = self.run_import(p)
        self.assertEqual(res, (0, 1))
        self.assertIn("anahtarı kullanıcı durum klasöründe yok", err)
        self.assertTrue(os.path.exists(p))
        res, out, err = self.run_import(p, seal_keys={cfg["kid"]: bytes.fromhex(cfg["key"])})   # CDP: bellekteki anahtar
        self.assertEqual(res, (1, 0), err)

    def test_key_stays_while_a_session_of_the_run_failed(self):
        cfg = wa_web.new_seal(sessions=2)
        self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], cfg, session="aaa111")
        self.sealed_part(2, [synth(1, stamp="[14:05, 14.11.2026] B: ", text="y")], cfg, session="bbb222", total=2,
                         mediaParts=[1])                      # medya parcasi 1 eksik
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 1))
        self.assertTrue(os.path.exists(self.key_path(cfg)))

    # ---- issue #21 review: the key lives until every session of the run has imported its final part
    def test_incomplete_sealed_session_keeps_parts_and_key_until_the_final_part_arrives(self):
        cfg = wa_web.new_seal()
        r1 = synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Ilk")
        r2 = synth(2, stamp="[14:06, 14.11.2026] Naime: ", text="Ikinci")
        snap = self.sealed_part(1, [r1], cfg, final=False, snapshot=True)       # only a checkpoint reached the folder
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertTrue(os.path.exists(snap) and self.key_exists(cfg))            # parts and key stay
        self.assertNotIn("Ikinci", self.md())
        fin = self.sealed_part(2, [r1, r2], cfg, media_parts=[])                  # the final part is downloaded later
        shutil.rmtree(self.out)
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertIn("Ikinci", self.md())
        self.assertFalse(os.path.exists(snap) or os.path.exists(fin) or self.key_exists(cfg))   # now everything is gone

    def test_key_stays_when_only_some_sessions_of_the_run_are_imported(self):
        cfg = wa_web.new_seal(sessions=2)
        a = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="birinci")], cfg, session="aaa111", chat="Aile")
        b = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] B: ", text="ikinci")], cfg, session="bbb222", chat="Is")
        res, out, err = self.run_import(a)                                       # the user passes one session only
        self.assertEqual(res, (1, 0), err)
        self.assertFalse(os.path.exists(a))
        self.assertTrue(self.key_exists(cfg))                                    # session bbb222 still needs the key
        self.assertIn("2 oturumundan 1 tanesi", out)
        res, out, err = self.run_import(b)                                       # the second session, later
        self.assertEqual(res, (1, 0), err)
        self.assertFalse(os.path.exists(b) or self.key_exists(cfg))

    def test_key_stays_with_keep_bundles(self):
        cfg = wa_web.new_seal()
        p = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], cfg)
        res, out, err = self.run_import(p, keep_bundles=True)
        self.assertEqual(res, (1, 0), err)
        self.assertTrue(os.path.exists(p) and self.key_exists(cfg))

    # ---- issue #21 review 2: the key is kept while a sealed bundle of it is left in the input
    def test_two_runs_of_one_snippet_import_together_and_the_key_goes_at_the_end(self):
        cfg = wa_web.new_seal(sessions=2)            # one snippet for 2 chats, pasted twice: 4 sessions share one key
        for sid, chat in (("aaa111", "Aile"), ("bbb222", "Is"), ("ccc333", "Okul"), ("ddd444", "Spor")):
            self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="metin " + chat)], cfg, session=sid, chat=chat)
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (4, 0), err)           # before: the key went after the first 2 and the others failed
        self.assertFalse(self.key_exists(cfg))
        self.assertEqual(sorted(os.listdir(self.out)), ["Aile", "Is", "Okul", "Spor"])

    def test_key_stays_while_a_sealed_bundle_of_it_is_left_in_the_input(self):
        cfg = wa_web.new_seal(sessions=1)
        good = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="birinci")], cfg, session="aaa111")
        bad = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] B: ", text="ikinci")], cfg, session="bbb222")
        self.edit_part(bad, runChats=7)              # fails the integrity check: stays in the folder, unconverted
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 1))
        self.assertFalse(os.path.exists(good))
        self.assertTrue(os.path.exists(bad) and self.key_exists(cfg))       # 1 of 1 sessions done, but a bundle is left
        self.assertIn("dönüştürülmemiş mühürlü paket", out)
        self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] B: ", text="ikinci")], cfg, session="bbb222")   # a good copy
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertFalse(self.key_exists(cfg))

    def test_a_stop_before_all_chats_started_does_not_keep_the_key(self):
        cfg = wa_web.new_seal(sessions=3)            # the snippet asked for 3 chats; "Stop and save" ended the run in chat 1
        p = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], cfg, runChats=1, stopped=True)
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertFalse(os.path.exists(p) or self.key_exists(cfg))
        self.assertNotIn("Anahtar duruyor", out)

    def test_a_chat_that_was_not_found_does_not_keep_the_key(self):
        cfg = wa_web.new_seal(sessions=3)            # 3 chats asked, the 2nd was not found: 2 sessions exist
        a = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], cfg, session="aaa111", chat="Aile", runChats=3)
        res, out, err = self.run_import(a)
        self.assertEqual(res, (1, 0), err)
        self.assertTrue(self.key_exists(cfg))        # the first final part cannot know yet: 3 chats may follow
        self.assertIn("3 oturumundan 1 tanesi", out)
        c = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] C: ", text="y")], cfg, session="ccc333", chat="Is", runChats=2)
        res, out, err = self.run_import(c)
        self.assertEqual(res, (1, 0), err)
        self.assertFalse(self.key_exists(cfg))       # the last chat's final part says how many chats were started

    def test_run_chats_is_authenticated(self):
        cfg = wa_web.new_seal(sessions=3)
        rows = [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")]
        p = self.sealed_part(1, rows, cfg, runChats=3)
        self.edit_part(p, runChats=1)                # lowering it would make the key go while sessions are missing
        res, out, err = self.run_import(p)
        self.assertEqual(res, (0, 1))
        self.assertIn("bütünlük denetimini geçemedi", err)
        p = self.sealed_part(1, rows, cfg, runChats=3)
        with open(p, encoding="utf-8") as f:
            part = json.load(f)
        del part["runChats"]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(part, f)
        res, out, err = self.run_import(p)
        self.assertEqual((res, "bütünlük denetimini geçemedi" in err), ((0, 1), True))
        self.assertTrue(self.key_exists(cfg))

    def test_a_part_without_run_chats_still_opens_and_falls_back_to_the_recorded_count(self):
        cfg = wa_web.new_seal(sessions=2)
        self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], cfg)
        res, out, err = self.run_import(self.tmp)
        self.assertEqual(res, (1, 0), err)
        self.assertTrue(self.key_exists(cfg))

    def test_old_seal_format_is_named_not_reported_as_damaged(self):
        cfg = wa_web.new_seal()
        p = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], cfg)
        with open(p, encoding="utf-8") as f:
            part = json.load(f)
        part["sealed"]["alg"] = "wa2md-seal-1"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(part, f)
        res, out, err = self.run_import(p)
        self.assertEqual(res, (0, 1))
        self.assertIn("mühür biçimini (wa2md-seal-1)", err)
        self.assertNotIn("bütünlük", err)
        self.assertTrue(os.path.exists(p) and self.key_exists(cfg))

    # ---- issue #21 review: the MAC covers session, part number, final / snapshot flag and media part list
    def test_header_fields_are_authenticated(self):
        cfg = wa_web.new_seal()
        rows = [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")]
        for change in ({"final": True, "total": 1},            # an old checkpoint relabelled as the final part
                       {"snapshot": False},                    # a checkpoint stripped of its flag
                       {"mediaParts": [1]},                    # media part list changed
                       {"session": "abc124"},                  # another session id
                       {"part": 2}):                           # another part number
            with self.subTest(change=change):
                p = self.sealed_part(1, rows, cfg, final=False, snapshot=True)
                self.edit_part(p, **change)
                res, out, err = self.run_import(p)
                self.assertEqual(res, (0, 1), err)
                self.assertIn("bütünlük denetimini geçemedi", err)
                os.remove(p)

    def test_damaged_sealed_part_is_reported(self):
        cfg = wa_web.new_seal()
        p = self.sealed_part(1, [synth(1, stamp="[14:05, 14.11.2026] A: ", text="x")], cfg)
        with open(p, encoding="utf-8") as f:
            part = json.load(f)
        part["sealed"]["tag"] = base64.b64encode(bytes(32)).decode()
        with open(p, "w", encoding="utf-8") as f:
            json.dump(part, f)
        res, out, err = self.run_import(p)
        self.assertEqual(res, (0, 1))
        self.assertIn("bütünlük denetimini geçemedi", err)

    def test_no_bundle_found(self):
        res, _, err = self.run_import(self.tmp)
        self.assertEqual(res, (0, 1))
        self.assertIn("wa-bundle", err)

    def test_failed_image_uses_writers_missing_marker_and_placeholder_for_documents(self):
        rows = [synth(1, stamp="[14:05, 14.11.2026] A: ", media=[{"kind": "image", "key": None, "label": ""}]),
                synth(2, stamp="[14:06, 14.11.2026] A: ", media=[{"kind": "document", "key": None, "label": '"rapor.pdf" indir'}])]
        p = self.part(1, final=True, rows=rows)
        res, out, _ = self.run_import(p)
        self.assertIn("1 medya eksik", out)
        self.assertIn("1 video/ses/belge indirilemedi", out)
        md = self.md()
        self.assertIn("_(dosya eksik: 20261114-1405-", md)
        self.assertIn("_belge indirilemedi: rapor.pdf_", md)


class CdpFailure(unittest.TestCase):
    """Issue #20 review: a CDP collection that fails (tab closed, collector error) keeps what was collected."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "out")
        self.args = type("A", (), {"chats": "Naime", "out": self.out, "anonim": False, "date_from": None, "date_to": None,
                                   "max_messages": None, "no_media": False})()
        self.orig = (wa_web.run_with_page, wa_web.export_chat_cdp)
        wa_web.run_with_page = lambda args, fn: fn(object())

    def tearDown(self):
        wa_web.run_with_page, wa_web.export_chat_cdp = self.orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def parts(self, staging, snapshot=True):
        rows = [synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Ilk satir"), synth(2, stamp="[14:06, 14.11.2026] Naime: ", text="Ikinci satir")]
        if snapshot:
            p = {"format": "wa-web-bundle", "version": 2, "session": "cdp111", "part": 1, "chat": "Naime", "final": False,
                 "snapshot": True, "rows": rows, "media": [], "mediaParts": [], "today": "2026-11-16", "opts": {}}
        else:
            p = {"format": "wa-web-bundle", "version": 2, "session": "cdp111", "part": 1, "chat": "Naime", "final": False,
                 "media": []}
        with open(os.path.join(staging, "wa-bundle-naime-cdp111-001.json"), "w", encoding="utf-8") as f:
            json.dump(p, f)

    def export(self):
        with redirect_stdout(io.StringIO()) as o, redirect_stderr(io.StringIO()) as e:
            try:
                rc = wa_web.cmd_export(self.args)
            except RuntimeError as ex:
                rc = ex
        return rc, o.getvalue(), e.getvalue()

    def test_tab_closed_after_a_checkpoint_converts_the_checkpoint(self):
        kept = []

        def fake(page, name, args, staging, seal_cfg=None):
            kept.append(staging)
            self.parts(staging)
            raise RuntimeError("Target closed")                  # the tab was closed mid-collection
        wa_web.export_chat_cdp = fake
        rc, out, err = self.export()
        self.assertIsInstance(rc, RuntimeError)
        with open(os.path.join(self.out, "Naime", "Naime.md"), encoding="utf-8") as f:
            self.assertIn("Ikinci satir", f.read())
        self.assertIn("ara kayıt", out)
        self.assertNotIn("Dönüştürülemeyen", out)
        self.assertNotIn("yerinde kalır", out)                   # the parts are deleted in this path: do not say they stay
        self.assertFalse(wa_web.find_bundle_files([kept[0]]))

    def test_collector_error_after_a_checkpoint_converts_it_and_counts_the_chat_as_failed(self):
        def fake(page, name, args, staging, seal_cfg=None):
            self.parts(staging)
            return {"state": "error", "error": "boom", "results": []}
        wa_web.export_chat_cdp = fake
        rc, out, err = self.export()
        self.assertEqual(rc, 0)                                   # one chat was written from the checkpoint
        self.assertTrue(os.path.isfile(os.path.join(self.out, "Naime", "Naime.md")))
        self.assertIn("Bitti: 1 sohbet yazıldı, 1 atlandı/hatalı", out)

    def test_sealed_checkpoint_is_converted_with_the_memory_key_after_a_failure(self):
        def fake(page, name, args, staging, seal_cfg=None):
            head = {"format": "wa-web-bundle", "version": 2, "session": "cdp222", "part": 1, "final": False, "snapshot": True,
                    "media": [], "mediaParts": [], "today": "2026-11-16", "opts": {}}
            rows = [synth(1, stamp="[14:05, 14.11.2026] Naime: ", text="Gizli satir")]
            head["sealed"] = wa_web.seal({"chat": "Naime", "rows": rows}, bytes.fromhex(seal_cfg["key"]), seal_cfg["kid"],
                                         aad=wa_web.header_aad(head))
            with open(os.path.join(staging, "wa-bundle-sealed-cdp222-001.json"), "w", encoding="utf-8") as f:
                json.dump(head, f)
            return {"state": "error", "error": "boom", "results": []}
        wa_web.export_chat_cdp = fake
        rc, out, err = self.export()
        self.assertEqual(rc, 0)
        with open(os.path.join(self.out, "Naime", "Naime.md"), encoding="utf-8") as f:
            self.assertIn("Gizli satir", f.read())

    def test_parts_that_cannot_be_converted_stay_on_disk_and_the_path_is_printed(self):
        kept = []

        def fake(page, name, args, staging, seal_cfg=None):
            kept.append(staging)
            self.parts(staging, snapshot=False)                   # only a media part reached the folder
            return {"state": "error", "error": "boom", "results": []}
        wa_web.export_chat_cdp = fake
        rc, out, err = self.export()
        self.assertEqual(rc, 1)
        self.assertTrue(os.path.isfile(os.path.join(kept[0], "wa-bundle-naime-cdp111-001.json")))
        self.assertIn(kept[0], out)
        self.assertNotIn("wa_web.py import", out)                  # the key lived in memory only: do not offer an import that cannot work
        self.assertIn("yalnız bellekte", out)
        shutil.rmtree(kept[0], ignore_errors=True)

    def test_clean_failure_without_parts_leaves_no_folder(self):
        kept = []

        def fake(page, name, args, staging, seal_cfg=None):
            kept.append(staging)
            return {"state": "error", "error": "boom", "results": []}
        wa_web.export_chat_cdp = fake
        self.export()
        self.assertFalse(os.path.exists(kept[0]))


# ------------------------------------------------------------------ wa_collect.js (gercek Chrome)
@unittest.skipUnless(sync_playwright and os.path.isfile(CHROME), "Chrome veya playwright yok")
class CollectorDom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROME, headless=True)
        cls.page = cls.browser.new_page()
        cls.page.set_content("<body></body>")
        cls.page.evaluate(wa_web.read_collector())

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def parse(self, name):
        self.page.set_content("<body>" + html(name) + "</body>")
        self.page.evaluate(wa_web.read_collector())
        return self.page.evaluate("""() => { const r = document.querySelector('[role=row]');
            const g = __waCollect.parseRow(r, document.body);
            return g && {row: g.row, items: g.items.map(i => ({kind: i.kind, label: i.label}))}; }""")

    def test_text_incoming(self):
        r = self.parse("text_in")["row"]
        self.assertEqual(r["text"], "Merhaba, nasılsın?")
        self.assertEqual(r["stamp"], "[14:05, 14.11.2026] Naime: ")
        self.assertEqual((r["out"], r["author"], r["meta"], r["media"]), (False, "Naime", "14:05", []))

    def test_outgoing_by_tail_and_by_tick_alone(self):
        a = self.parse("text_out")["row"]
        self.assertTrue(a["out"])
        self.assertIsNone(a["author"])  # 'Sen:' etiketi gonderen sayilmaz
        self.assertEqual(a["meta"], "14:07")  # tik simgesinin basligi (wds-ic-read) metne karismaz
        self.assertTrue(self.parse("text_out_no_tail")["row"]["out"])
        self.assertFalse(self.parse("text_in_no_tail")["row"]["out"])

    def test_multiline_emoji_list_link(self):
        self.assertEqual(self.parse("multiline")["row"]["text"], "Selam\nikinci satır 😀\nüçüncü")
        self.assertEqual(self.parse("emoji_img")["row"]["text"], "Tamam 👍 oldu")
        self.assertEqual(self.parse("list")["row"]["text"], "Liste:\n1. Birinci\n2. İkinci")
        self.assertEqual(self.parse("link")["row"]["text"], "https://example.org/x")  # onizleme metne girmez

    def test_quote_is_not_part_of_text(self):
        r = self.parse("quote")["row"]
        self.assertEqual((r["text"], r["quote"]), ("Cevap geldi", "Naime: Merhaba, nasılsın?"))
        self.assertTrue(r["out"])

    def test_quoted_image_is_not_media(self):
        p = self.parse("quote_media")
        self.assertEqual(p["row"]["quote"], "Naime: Fotoğraf")
        self.assertEqual((p["row"]["text"], p["row"]["media"], p["items"]), ("Bu fotoğrafa cevap", [], []))

    def test_forwarded_flag(self):
        r = self.parse("forwarded")["row"]
        self.assertTrue(r["forwarded"])
        self.assertEqual(r["text"], "İletilen metin")
        self.assertFalse(self.parse("text_in")["row"]["forwarded"])

    def test_media_only_row_has_no_stamp_but_meta_and_label(self):
        p = self.parse("image_in_no_stamp")
        self.assertIsNone(p["row"]["stamp"])
        self.assertEqual((p["row"]["meta"], p["row"]["author"], p["row"]["text"]), ("14:21", "Naime", ""))
        self.assertEqual([m["kind"] for m in p["row"]["media"]], ["image"])
        self.assertTrue(self.parse("image")["row"]["out"])

    def test_image_with_caption_has_stamp_and_text(self):
        r = self.parse("image_caption")["row"]
        self.assertEqual(r["stamp"], "[14:22, 14.11.2026] Naime: ")
        self.assertEqual(r["text"], "Bu bir açıklama")
        self.assertEqual(len(r["media"]), 1)

    def test_album_has_one_item_per_thumb_and_pending_image_still_listed(self):
        self.assertEqual([m["kind"] for m in self.parse("album")["row"]["media"]], ["image", "image"])
        self.assertEqual(len(self.parse("image_pending")["items"]), 1)

    def test_document_label_and_reaction_ignored(self):
        d = self.parse("document")["row"]
        self.assertEqual([(m["kind"], m["label"]) for m in d["media"]], [("document", '"rapor.pdf" dosyasını indir')])
        r = self.parse("reaction")["row"]
        self.assertEqual(r["text"], "")  # tepki emojisi metne girmez
        self.assertEqual(len(r["media"]), 1)

    def test_virtualized_shell_row_has_no_content(self):
        self.assertIsNone(self.parse("shell"))

    def test_unverified_structures_deleted_and_system(self):  # secici tahmini: gercek ornek gorulmedi
        self.assertTrue(self.parse("deleted_unverified")["row"]["deleted"])
        self.assertEqual(self.parse("system_join_unverified")["row"]["system"], "Mehmet gruba katıldı")

    def test_pick_chat(self):
        titles = ["Naime Yılmaz", "Naime", "Aile grubu", "Aile Eğitim", "Mehmet Kaya (Siz)"]
        pick = lambda q: self.page.evaluate("([q, t]) => __waCollect.pickChat(q, t)", [q, titles])  # noqa: E731
        self.assertEqual(pick("naime"), {"status": "ok", "title": "Naime"})
        self.assertEqual(pick("NAIME YILMAZ"), {"status": "ok", "title": "Naime Yılmaz"})
        self.assertEqual(pick("grubu"), {"status": "ok", "title": "Aile grubu"})
        self.assertEqual(pick("aile")["status"], "ambiguous")
        self.assertEqual(pick("yok"), {"status": "none"})
        self.assertEqual(pick("mehmet kaya"), {"status": "ok", "title": "Mehmet Kaya (Siz)"})

    def test_pick_chat_normalisation(self):
        titles = ["🚛🚛Örnek ÇUKUROVA Nakliyat 🚛🚛", "Merkezi  Test   hibu", "ILIK Liman", "Deneme Grup A", "Deneme Grup B",
                  "Köy 👨‍👩‍👧 Haberleri Grubu"]
        pick = lambda q, t=titles: self.page.evaluate("([q, t]) => __waCollect.pickChat(q, t)", [q, t])  # noqa: E731
        self.assertEqual(pick("Örnek ÇUKUROVA Nakliyat"), {"status": "ok", "title": titles[0]})
        self.assertEqual(pick("ORNEK cukurova nakliyat"), {"status": "ok", "title": titles[0]})
        self.assertEqual(pick("🚛 Örnek ÇUKUROVA Nakliyat"), {"status": "ok", "title": titles[0]})  # sorguda emoji de olabilir
        self.assertEqual(pick("Merkezi Test hibu"), {"status": "ok", "title": titles[1]})
        self.assertEqual(pick("MerkeziTest-hibu"), {"status": "ok", "title": titles[1]})  # sıkıştırılmış eşleşme
        self.assertEqual(pick("ılık liman"), {"status": "ok", "title": titles[2]})
        self.assertEqual(pick("ILIK LİMAN"), {"status": "ok", "title": titles[2]})
        self.assertEqual(pick("köy haberleri grubu"), {"status": "ok", "title": titles[5]})  # ZWJ aile emojisi, NBSP
        self.assertEqual(pick("deneme grup"), {"status": "ambiguous", "count": 2})  # yalniz sayi, ad yok
        self.assertEqual(pick("deneme grup a"), {"status": "ok", "title": "Deneme Grup A"})
        self.assertEqual(pick("yok böyle"), {"status": "none"})
        self.assertEqual(pick("🚛🚛"), {"status": "none"})  # emoji-only sorgu hicbir seye eslesmez
        # bos-sonrasi esit: yalniz emojiyle ayrilan iki baslik belirsizdir
        self.assertEqual(pick("Grup X", ["Grup X", "🚛Grup X"]), {"status": "ambiguous", "count": 2})
        norm = lambda s: self.page.evaluate("(s) => __waCollect.normName(s)", s)  # noqa: E731
        self.assertEqual(norm("  İSTANBUL‍  Işık (Siz)"), "istanbul isik")

    def test_part_blob_equals_json_stringify(self):
        out = self.page.evaluate("""async () => {
            const part = {format: 'wa-web-bundle', version: 1, part: 2, final: false, skip: undefined,
                          media: [{key: 'a', mime: 'image/png', b64: 'AAAA'}, {key: 'b', mime: '', b64: ''}], rows: [{id: 'x', text: 'ş"\\n'}]};
            const a = await __waCollect.partBlob(part).text();
            const e = await __waCollect.partBlob({n: 1, media: []}).text();
            return [a === JSON.stringify(part), JSON.parse(e).media.length];
        }""")
        self.assertEqual(out, [True, 0])

    def test_blob_to_b64_chunks_match_btoa(self):
        out = self.page.evaluate("""async () => {
            const n = 7 * 1024 * 1024 + 5; const u = new Uint8Array(n);
            for (let i = 0; i < n; i++) u[i] = (i * 31 + 7) & 255;
            const b64 = await __waCollect.blobToB64(new Blob([u]));
            let bin = ''; for (let i = 0; i < n; i += 65536) bin += String.fromCharCode.apply(null, u.subarray(i, i + 65536));
            return b64 === btoa(bin);
        }""")
        self.assertTrue(out)

    def test_js_seal_matches_the_python_reference(self):
        # issue #21: bir belirtim, iki uygulama (sekme muhurler, Python acar): sabit anahtar ve nonce ile bayt bayt ayni
        key, kid, nonce = bytes(range(32)), "00000000000000bb", bytes(range(16))
        obj = {"chat": "Naime Çağ 🚚", "rows": [synth(i, text=f"Mesaj {i} şifre: Ab{i}") for i in range(900)]}  # >64 KB: 2048 blok sinirini gecer
        # WebCrypto yalniz guvenli baglamda (web.whatsapp.com gibi https): sahte https sayfasi (ag yok)
        self.page.route("https://wa2md.test/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<body></body>"))
        self.page.goto("https://wa2md.test/")
        self.page.evaluate(wa_web.read_collector())
        # the authenticated header (session, part number, final / snapshot flag, media part list), spelled as the bundler does
        head = {"session": "k1abc", "part": 3, "final": False, "snapshot": True, "mediaParts": [1, 2]}
        aad = wa_web.header_aad(head)
        self.assertEqual(aad, "\0".join(["k1abc", "3", "0", "1", "1,2"]))
        self.assertEqual(self.page.evaluate("(p) => __waCollect.headerAad(p)", head), aad)       # the JS side builds the same string
        last = dict(head, final=True, snapshot=False, runChats=2)   # a final part also authenticates how many chats the run started
        self.assertEqual(wa_web.header_aad(last), "\0".join(["k1abc", "3", "1", "0", "1,2", "2"]))
        self.assertEqual(self.page.evaluate("(p) => __waCollect.headerAad(p)", last), wa_web.header_aad(last))
        js = self.page.evaluate("async ([o, cfg, n, a]) => await __waCollect.seal(o, cfg, n, a)",
                                [obj, {"kid": kid, "key": key.hex()}, list(nonce), aad])
        self.assertGreater(len(base64.b64decode(js["ct"])), 2048 * 32)
        self.assertEqual(js, wa_web.seal(obj, key, kid, nonce, aad))
        self.assertEqual(wa_web.unseal(js, key, aad), obj)
        with self.assertRaises(ValueError):          # the header is part of the MAC: another flag does not open
            wa_web.unseal(js, key, wa_web.header_aad(dict(head, final=True)))

    def test_merge_order_inserts_before_and_after_anchors(self):
        o = self.page.evaluate("""() => { const o = ['c', 'd'];
            __waCollect.mergeOrder(o, ['a', 'b', 'c']); __waCollect.mergeOrder(o, ['d', 'e']); return o; }""")
        self.assertEqual(o, ["a", "b", "c", "d", "e"])

    def test_short_id_and_stamp_day(self):
        self.assertEqual(self.page.evaluate("() => __waCollect.shortId('AC000000000000000000000000000016')"), "00000016")
        self.assertEqual(self.page.evaluate("() => __waCollect.stampDay('[14:05, 14.11.2026] A: ', false)"), 20261114)
        self.assertEqual(self.page.evaluate("() => __waCollect.stampDay('[2:05 PM, 11/14/2026] A: ', true)"), 20261114)

    def test_fixtures_to_markdown_through_the_single_writer(self):
        """Gercek-yapi fixture'larindan (JS ayristirma) -> build_messages -> wa2md.write_chat."""
        names = ["text_in", "multiline", "quote", "forwarded", "image_in_no_stamp", "image_caption", "album", "document",
                 "text_next_day"]
        rows, keys = [], {}
        for n in names:
            row = self.parse(n)["row"]
            for i, m in enumerate(row["media"]):
                if m["kind"] == "image":
                    m["key"] = f"K{len(keys)}"
                    keys[m["key"]] = b"\xff\xd8" + bytes([len(keys)])
            if not row["stamp"]:
                row["divider"] = "14.11.2026"
            rows.append(row)
        tmp = tempfile.mkdtemp()
        try:
            staging = os.path.join(tmp, "stage")
            os.makedirs(staging)
            files = {}
            for k, data in keys.items():
                p = os.path.join(staging, k + ".tmp")
                with open(p, "wb") as f:
                    f.write(data)
                files[k] = (p, ".jpg")
            ids = {r["id"] for r in rows}
            self.assertEqual(len(ids), len(rows))
            msgs = wa_web.build_messages(rows, "Naime", TODAY, files, staging)
            export = wa2md.Export("web", "", b"", wa2md.scan_files(staging))
            with redirect_stdout(io.StringIO()):
                path, real, copied, missing = wa2md.write_chat("Naime", msgs, export, os.path.join(tmp, "out"))
            with open(path, encoding="utf-8") as f:
                md = f.read()
            self.assertIn("## 2026-11-14", md)
            self.assertIn("## 2026-11-15", md)
            self.assertIn("**Naime** 14:05\nMerhaba, nasılsın?", md)
            self.assertIn("Selam  \nikinci satır 😀  \nüçüncü", md)
            self.assertIn("_Yönlendirilmiş mesaj_  \nİletilen metin", md)
            self.assertIn("> Naime: Merhaba, nasılsın?\n\nCevap geldi", md)
            self.assertIn("**Deniz Test** 14:15", md)
            self.assertIn(".jpg)  \nBu bir açıklama", md)
            self.assertEqual(md.count("![](media/"), 4)  # 1 + 1 + albumde 2
            self.assertIn("_belge indirilemedi: rapor.pdf_", md)
            self.assertEqual((copied, missing), (4, 0))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
