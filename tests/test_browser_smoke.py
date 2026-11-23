"""Gercek Chrome + Playwright duman testi: kendi gecici Chrome'umuzu (ayri profil, uzak hata ayiklama portu)
baslatir, DevToolsActivePort'u okuyup wa_web.attach ile baglanir ve SAHTE bir WhatsApp Web sayfasinda
list/export (CDP tasimasi) + wa_collect.js akisini kosar. Kullanicinin gercek Chrome'una dokunmaz.
Chrome/playwright yoksa atlanir. (Bu test CDP tasimasinin KENDI Chrome'umuzla calistigini gosterir; kullanicinin
Chrome'una baglanti dogrulanmadi.)"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import wa_web  # noqa: E402

# WA2MD_TEST_CHROME: path of a Chrome / Chromium for the browser tests (default: the usual Windows install)
CHROME = os.environ.get("WA2MD_TEST_CHROME") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

with open(os.path.join(HERE, "fixtures", "web", "fake_wa.html"), encoding="utf-8") as _f:
    FAKE = _f.read()


class Args:
    def __init__(self, **kw):
        self.no_media = False
        self.max_messages = None
        self.date_from = self.date_to = None
        self.out = None
        self.older_from_phone = False
        self.checkpoint_minutes = 10
        self.__dict__.update(kw)


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return int.from_bytes(head[16:20], "big")


@unittest.skipUnless(sync_playwright and os.path.isfile(CHROME), "Chrome veya playwright yok")
class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["WA_PACE"] = "0.02"
        cls.udd = tempfile.mkdtemp(prefix="wa_smoke_")
        cls.proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--user-data-dir={cls.udd}", "--remote-debugging-port=0",
             "--no-first-run", "--no-default-browser-check", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while not os.path.isfile(os.path.join(cls.udd, "DevToolsActivePort")) and time.time() < deadline:
            time.sleep(0.2)
        # sahte sayfayi web.whatsapp.com adresine yonlendir (ag yok); wa_web.attach bu sekmeyi bulur
        cls.pw1 = sync_playwright().start()
        cls.b1 = cls.pw1.chromium.connect_over_cdp(wa_web.read_ws_endpoint(cls.udd))
        ctx = cls.b1.contexts[0]
        cls.fake = ctx.new_page()
        cls.fake.route("https://web.whatsapp.com/**", lambda r: r.fulfill(status=200, content_type="text/html",
                                                                         body=FAKE))
        cls.fake.goto("https://web.whatsapp.com/")
        cls.pw1.stop()  # sayfa Chrome'da kalir; ikinci (test edilen) baglanti onu yeniden kullanir

    @classmethod
    def tearDownClass(cls):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(cls.proc.pid), "/T", "/F"], capture_output=True)
        else:
            cls.proc.kill()
            cls.proc.wait(timeout=30)
        shutil.rmtree(cls.udd, ignore_errors=True)

    def run_flow(self, fn):
        with sync_playwright() as pw:
            browser, page, ours = wa_web.attach(pw, self.udd, timeout_ms=30000)
            self.assertFalse(ours, "mevcut web.whatsapp.com sekmesi yeniden kullanilmali")
            return fn(page)

    def export(self, name, out, **kw):
        def go(page):
            staging = tempfile.mkdtemp(prefix="wa_smoke_stage_")
            try:
                status = wa_web.export_chat_cdp(page, name, Args(out=out, **kw), staging)
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    res = wa_web.import_bundles([staging], out, kw.get("date_from"), kw.get("date_to"), kw.get("max_messages"))
                return status, res, page.evaluate("window.typedInComposer")
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        return self.run_flow(go)

    def test_list_and_export_read_only(self):
        out = tempfile.mkdtemp()
        try:
            names = self.run_flow(wa_web.list_chats)
            self.assertEqual(len(names), 36)  # 30 sıralı + 6 uydurma ek sohbet (emoji, çift boşluk, I/i, belirsiz çift, yavaş arama)
            self.assertEqual(names[0], "Sohbet 01")
            status, res, typed = self.export("sohbet 03", out)
            self.assertEqual(status["state"], "done")
            self.assertEqual(res, (1, 0))
            result = status["results"][0]
            self.assertEqual((result["rows"], result["media"], result["missing"]), (40, 16, 0))
            amb = self.export("sohbet 0", out)[0]["results"][0]
            self.assertIn("More than one", amb["error"])
            md_path = os.path.join(out, "Sohbet 03", "Sohbet 03.md")
            with open(md_path, encoding="utf-8") as f:
                md = f.read()
            self.assertIn("Message count: 40", md)
            self.assertIn("## 2026-11-13", md)
            self.assertIn("## 2026-11-14", md)
            self.assertIn("**Naime** 08:00\nMesaj 0", md)
            self.assertIn("![](media/20261113-0830-", md)  # damgasiz foto: tarih gun basligindan, saat alt bilgiden
            media = sorted(os.listdir(os.path.join(out, "Sohbet 03", "media")))
            self.assertEqual(len(media), 16)  # 6 yuklu (i % 7 == 3) + 5 yuklenmemis (i % 7 == 5) + 5 indirme dugmeli (i % 7 == 6)
            sizes = sorted(png_size(os.path.join(out, "Sohbet 03", "media", m)) for m in media)
            # yuklu foto 80px, yuklenmemisler goruntuleyiciden 300px (bulanik onizleme degil)
            self.assertEqual(sizes, [80] * 6 + [120] * 5 + [300] * 5)
            self.assertEqual(typed, 0)  # mesaj kutusuna hic yazilmadi
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def lookup(self, name, **kw):
        """Yalniz bul/ac/topla (import yok): (durum, arama kutusu degeri, mesaj kutusuna yazilan)."""
        def go(page):
            staging = tempfile.mkdtemp(prefix="wa_smoke_stage_")
            try:
                status = wa_web.export_chat_cdp(page, name, Args(out=None, no_media=True, max_messages=3, **kw), staging)
                return (status, page.evaluate("document.getElementById('q').value"),
                        page.evaluate("window.typedInComposer"))
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        return self.run_flow(go)

    def test_titles_with_emoji_spacing_and_turkish_case(self):
        # gercek baslikta emoji <img alt> (textContent'te yok); liste basliginda emoji karakter olarak var
        for query in ["Örnek ÇUKUROVA Nakliyat", "ornek cukurova", "Merkezi Test hibu", "MerkeziTest hibu",  # çift boşluk / boşluksuz
                      "ılık liman", "ILIK LİMAN"]:  # I/ı/i/İ
            with self.subTest(query=query):
                status, box, typed = self.lookup(query)
                self.assertEqual(status["state"], "done", status)
                self.assertNotIn("error", status["results"][0], status)
                self.assertGreaterEqual(status["results"][0]["rows"], 3)  # sohbet acildi ve toplandi (3 mesajla sinirli)
                self.assertEqual((box, typed), ("", 0))  # arama kutusu temizlendi, mesaj kutusu bos

    def test_ambiguous_and_missing_titles_are_content_free(self):
        status, box, _ = self.lookup("deneme grup")
        err = status["results"][0]["error"]
        self.assertIn("More than one", err)
        self.assertIn("2 candidates", err)
        self.assertNotIn("Deneme", err)  # adlar hatada yer almaz, yalniz sayi
        self.assertEqual(box, "")
        status, box, _ = self.lookup("hic yok boyle bir sohbet")
        self.assertIn("No chat with this name", status["results"][0]["error"])
        self.assertEqual(box, "")

    def test_slow_search_results_are_awaited_and_heartbeat_kept(self):
        # sonuclar 2.6 sn gecikir; eski sabit 1.8 sn bekleme burada eski (tam) listeden 'bulunamadi' derdi
        status, box, _ = self.lookup("yavas arama")
        self.assertEqual(status["state"], "done", status)
        self.assertGreaterEqual(status["results"][0]["rows"], 3)
        self.assertEqual(box, "")
        now = int(time.time() * 1000)
        self.assertGreater(status["heartbeat"], status["startedAt"])
        self.assertLess(abs(status["alive"] - status["heartbeat"]), 60000)
        self.assertEqual(status["phase"], "end")
        self.assertEqual([p["final"] for p in status["parts"]], [True])
        self.assertLess(now - status["heartbeat"], 10 * 60 * 1000)
        self.assertGreaterEqual(status["steps"], 1)  # ilerleme sayaclari (yalniz sayilar)

    def test_from_filter_stops_scrolling_and_no_media(self):
        import datetime as dt
        out = tempfile.mkdtemp()
        try:
            status, res, _ = self.export("Sohbet 07", out, date_from=dt.date(2026, 11, 14), no_media=True)
            self.assertEqual(res, (1, 0))
            with open(os.path.join(out, "Sohbet 07", "Sohbet 07.md"), encoding="utf-8") as f:
                md = f.read()
            self.assertNotIn("## 2026-11-13", md)
            self.assertIn("Message count: 20", md)
            self.assertIn("_(media not included)_", md)
            self.assertFalse(os.path.exists(os.path.join(out, "Sohbet 07", "media")))
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_max_messages_stops_early(self):
        out = tempfile.mkdtemp()
        try:
            status, res, _ = self.export("Sohbet 05", out, max_messages=15)
            self.assertEqual(res, (1, 0))
            with open(os.path.join(out, "Sohbet 05", "Sohbet 05.md"), encoding="utf-8") as f:
                md = f.read()
            self.assertIn("Message count: 15", md)
            self.assertIn("Mesaj 39", md)  # en yeni mesajlar tutulur
            self.assertNotIn("Mesaj 24\n", md)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    # ---- issue #20: stop control and checkpoints
    def collect(self, name, **kw):
        """Toplama + ham parcalar (import yok): (durum, {dosya adi: parca})."""
        import json

        def go(page):
            staging = tempfile.mkdtemp(prefix="wa_smoke_stage_")
            try:
                status = wa_web.export_chat_cdp(page, name, Args(**kw), staging)
                parts = {}
                for n in sorted(os.listdir(staging)):
                    with open(os.path.join(staging, n), encoding="utf-8") as f:
                        parts[n] = json.load(f)
                return status, parts, staging
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        return self.run_flow(go)

    def test_stop_button_saves_what_was_collected(self):
        out = tempfile.mkdtemp()
        try:
            # paneldeki "Stop and save" dugmesine ilk kaydirma adimindan sonra basilir (kullanici gibi)
            self.run_flow(lambda page: page.evaluate("""() => { const iv = setInterval(() => {
                const b = document.querySelector('#wa-collect-panel button[data-wa=stop]');
                if (b && window.__waStatus && window.__waStatus.phase === 'collect') { b.click(); clearInterval(iv); }
            }, 10); }"""))
            status, parts, staging = self.collect("Sohbet 09", no_media=True)
            try:
                result = status["results"][0]
                self.assertEqual(status["state"], "done")
                self.assertTrue(status.get("stopped") and result.get("stopped"))
                self.assertTrue(0 < result["rows"] < 40, result)          # 40 mesajin yalniz ilk yuklenenleri
                final = [p for p in parts.values() if p.get("final")]
                self.assertEqual(len(final), 1)
                self.assertTrue(final[0]["stopped"])
                with redirect_stdout(io.StringIO()) as o, redirect_stderr(io.StringIO()):
                    res = wa_web.import_bundles([staging], out)
                self.assertEqual(res, (1, 0))
                self.assertIn("stopped early", o.getvalue())
                self.assertEqual(os.listdir(staging), [])                 # donusturulen paketler silindi
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_checkpoints_make_an_unfinished_collection_importable(self):
        out = tempfile.mkdtemp()
        status, parts, staging = self.collect("Sohbet 11", checkpoint_minutes=0.0001)   # her adimda ara kayit
        try:
            self.assertEqual(status["state"], "done")
            snaps = sorted((n for n, p in parts.items() if p.get("snapshot")), key=lambda n: parts[n]["part"])
            self.assertGreaterEqual(len(snaps), 2, list(parts))
            for n in snaps:   # ara kayit yalniz kendinden once yazilmis medya parcalarina dayanir
                p = parts[n]
                self.assertTrue(all(i < p["part"] and parts_media(parts, i) for i in p["mediaParts"]), p["mediaParts"])
            final = next(n for n, p in parts.items() if p.get("final"))
            os.remove(os.path.join(staging, final))                   # sekme kapandi: son parca hic yazilmadi
            newest = parts[snaps[-1]]
            with redirect_stdout(io.StringIO()) as o, redirect_stderr(io.StringIO()):
                res = wa_web.import_bundles([staging], out)
            self.assertEqual(res, (1, 0))
            self.assertIn(f"newest checkpoint (part {newest['part']}) was used", o.getvalue())
            with open(os.path.join(out, "Sohbet 11", "Sohbet 11.md"), encoding="utf-8") as f:
                md = f.read()
            self.assertIn(f"Message count: {len(newest['rows'])}", md)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(out, ignore_errors=True)


def parts_media(parts, no):
    return any(p["part"] == no and p.get("media") for p in parts.values())


if __name__ == "__main__":
    unittest.main(verbosity=2)
