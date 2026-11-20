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
import wa2md  # noqa: E402
import wa_web  # noqa: E402


_ENV = {}


def setUpModule():
    """Inceleme dosyasi varsayilan olarak kullanici durum klasorune gider: testlerde gecici klasor."""
    _ENV["old"] = os.environ.get("XDG_STATE_HOME")
    _ENV["dir"] = tempfile.mkdtemp(prefix="wa2md-state-")
    os.environ["XDG_STATE_HOME"] = _ENV["dir"]


def tearDownModule():
    if _ENV["old"] is None:
        os.environ.pop("XDG_STATE_HOME", None)
    else:
        os.environ["XDG_STATE_HOME"] = _ENV["old"]
    shutil.rmtree(_ENV["dir"], ignore_errors=True)

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
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
        self.assertIn("__waCollect", out)  # toplayici dosyanin kendisi gomulu
        self.assertIn("allow pasting", err)

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

    def part(self, no, final=False, rows=None, media=None, total=None, session="abc123", chat="Naime"):
        p = {"format": "wa-web-bundle", "version": 1, "session": session, "part": no, "chat": chat, "final": final,
             "media": media or []}
        if final:
            p.update({"total": total or no, "rows": rows or [], "today": "2026-11-16", "opts": {}})
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
