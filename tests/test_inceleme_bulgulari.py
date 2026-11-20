"""bagimsiz inceleme bulgulari 1-16. Tum adlar, numaralar, sohbetler ve dosya adlari uydurmadir."""
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import wa2md  # noqa: E402

_ENV = {}


def setUpModule():
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


H = "14.11.2026 09:%02d - %s: %s"
GROUP_HEAD = ["Can Er", "Ali Veli", "Berk Ak"]     # 3 gonderen: grup


def chat(lines, senders=None):
    """lines: [(gonderen, metin)] ya da [metin] (Can Er yazar); basa 3 gonderenli selam eklenir (grup)."""
    rows = [(s, "selam") for s in (senders if senders is not None else GROUP_HEAD)]
    rows += [x if isinstance(x, tuple) else ("Can Er", x) for x in lines]
    return "\n".join(H % (i, s, t) for i, (s, t) in enumerate(rows)) + "\n"


def md(text, title="Satranç Kulübü", group=None, export=None, **kw):
    msgs, _ = wa2md.parse(wa2md.decode(text.encode("utf-8")))
    msgs = wa2md.mark_system_lines(title, msgs)
    a = wa2md.Anonymizer(title, msgs, 1, None, group=group)
    out, used, miss = wa2md.render(title, msgs, export, anon=a, **kw)
    return out, a


def make_dir(root, title, text, files=None):
    d = os.path.join(root, f"WhatsApp Chat with {title}")
    os.makedirs(d)
    with open(os.path.join(d, "_chat.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    for n, data in (files or {}).items():
        with open(os.path.join(d, n), "wb") as f:
            f.write(data)
    return d


def run(*argv):
    o, e = io.StringIO(), io.StringIO()
    with redirect_stdout(o), redirect_stderr(e):
        code = wa2md.main(list(argv))
    return code, o.getvalue(), e.getvalue()


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def read(self, *p):
        with open(os.path.join(*p), encoding="utf-8") as f:
            return f.read()


class F01CaptionPassword(unittest.TestCase):
    def test_password_line_after_attachment_is_masked(self):
        for att in ("rapor.pdf (dosya ekli)", "<ek: rapor.pdf>"):
            with self.subTest(att=att):
                out, _ = md(chat([att + "\nPDF şifresi: Kartal.2024"]))
                self.assertIn("PDF şifresi: [parola]", out)
                self.assertNotIn("Kartal.2024", out)

    def test_title_lines_are_not_passwords(self):
        out, _ = md(chat(["DOC-20261114-WA0003.pdf (dosya ekli)\nToplanti_Notlari_v2.pdf\nKartal.80.jpg"]))
        self.assertIn("Toplanti_Notlari_v2.pdf", out)
        self.assertIn("Kartal.80.jpg", out)
        self.assertNotIn("[parola]", out)
        self.assertTrue(wa2md.is_title_line("rapor.pdf", {"rapor.pdf"}))
        self.assertFalse(wa2md.is_title_line("şifre Kartal.2024", set()))
        self.assertFalse(wa2md.is_title_line("Kartal.2024", set()))      # bilinen dosya uzantisi degil


class F02ChatTitle(Tmp):
    def test_one_to_one_title_masked_even_if_contact_silent_in_window(self):
        text = ("13.11.2026 09:00 - Xandor Plimm: selam\n"
                "14.11.2026 09:00 - Can Er: Xandor Plimm'e ilet, Xandor Plimm yarın gelir, Xandor'a da söyle\n")
        src = make_dir(self.tmp, "Xandor Plimm", text)
        out = os.path.join(self.tmp, "o")
        code, o, e = run(src, "--out", out, "--from", "2026-11-14")
        self.assertEqual(code, 0, e)
        res = self.read(out, "Sohbet-1", "Sohbet-1.md")
        for bad in ("Xandor", "Plimm"):
            self.assertNotIn(bad, res)
        self.assertRegex(res, r"Kişi \d+'e ilet, Kişi \d+ yarın gelir")

    def test_group_named_after_person_masked_in_text(self):
        out, _ = md(chat(["Plimm Ailesi toplantısı yarın, Plimm'ler gelir"]), title="Plimm Ailesi")
        self.assertNotIn("Plimm", out)
        self.assertIn("Sohbet-1 toplantısı yarın", out)

    def test_organisation_title_words_left_in_group_text(self):
        out, a = md(chat(["Satranç Kulübü toplantısı cumartesi, kulübü arayın"]), title="Satranç Kulübü")
        self.assertTrue(a.group)
        self.assertIn("Satranç Kulübü toplantısı cumartesi, kulübü arayın", out)
        self.assertEqual(a.text("Satranç Kulübü", title=True), "Sohbet-1")   # sistem satiri / dosya adi: maskelenir

    def test_group_detection(self):
        # karar disa aktarimdan: sohbet adi olmayan 2 gonderen -> grup; baslik sozcukleri karar vermez
        msgs, _ = wa2md.parse(chat([], senders=["Can Er", "Ali Veli"]))
        self.assertTrue(wa2md.is_group(msgs, "Mavi Ekip"))
        self.assertTrue(wa2md.is_group(msgs, "Dört Sözcüklü Uzun Başlık"))
        msgs, _ = wa2md.parse(chat([], senders=["Can Er", "Xandor Plimm"]))
        self.assertFalse(wa2md.is_group(msgs, "Xandor Plimm"))
        msgs, _ = wa2md.parse("14.11.2026 09:00 - Can Er: a\n14.11.2026 09:01 - Can Er added Ece Su\n")
        self.assertTrue(wa2md.is_group(msgs, "Xandor Plimm"))


class F03ReviewFile(Tmp):
    TEXT = chat(["Bahar geldi, Umut abi'ye söyle", "Poyraz esiyor"])

    def test_samples_taken_after_masking_and_file_outside_out(self):
        src = make_dir(self.tmp, "Satranç Kulübü", self.TEXT)
        out = os.path.join(self.tmp, "o")
        code, o, e = run(src, "--out", out)
        self.assertEqual(code, 0, e)
        self.assertEqual(os.listdir(out), ["Sohbet-1"])
        res = self.read(out, "Sohbet-1", "Sohbet-1.md")
        rev = self.read(wa2md.default_review_dir(out), "Sohbet-1-supheli-adlar.txt")
        self.assertNotIn("Umut", res)
        self.assertNotIn("Umut", rev)                                   # maskelenmis ad inceleme dosyasinda yok
        rows = [r.split("\t") for r in rev.split("\n") if r and not r.startswith("#")]
        self.assertEqual(sorted(r[0] for r in rows), ["Bahar", "Poyraz"])
        for r in rows:
            for ex in r[3].split(" | "):
                self.assertIn(ex, res)                                  # her ornek ciktida aynen duruyor

    def test_review_dir_flag_and_git_tree_refused(self):
        src = make_dir(self.tmp, "Satranç Kulübü", self.TEXT)
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        code, o, e = run(src, "--out", os.path.join(self.tmp, "o1"), "--inceleme-dizini", os.path.join(repo, "inc"))
        self.assertEqual(code, 2)
        self.assertIn("git çalışma ağacının", e)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "o1")))    # hicbir cikti yazilmadi
        code, o, e = run(src, "--out", os.path.join(repo, "o2"))          # varsayilan inceleme yeri git disinda
        self.assertEqual(code, 0, e)
        self.assertNotIn("_inceleme", os.listdir(os.path.join(repo, "o2")))
        code, o, e = run(src, "--out", os.path.join(self.tmp, "o3"), "--inceleme-dizini", os.path.join(self.tmp, "inc"))
        self.assertEqual(code, 0, e)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "inc", "Sohbet-1-supheli-adlar.txt")))

    def test_gitignore_guard(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
        p = os.path.join(root, ".gitignore")
        if not os.path.isfile(p):
            self.skipTest("repo kokunde degil")
        with open(p, encoding="utf-8") as f:
            self.assertIn("_inceleme/", f.read().split())


class F04IosSystemLines(Tmp):
    IOS = ('[14.11.2026 09:00:00] Test Grubu: Ahmet Kaya created group "Test Grubu"\n'
           "[14.11.2026 09:01:00] Test Grubu: Ahmet Kaya added Xandor Plimm\n"
           "[14.11.2026 09:02:00] Test Grubu: Quorvel Tisk joined using this group's invite link\n"
           "[14.11.2026 09:03:00] Test Grubu: Messages and calls are end-to-end encrypted.\n"
           "[14.11.2026 09:04:00] Ahmet Kaya: Xandor nerede? Quorvel geldi mi?\n")

    def test_group_name_in_sender_position(self):
        src = make_dir(self.tmp, "Test Grubu", self.IOS)
        out = os.path.join(self.tmp, "o")
        code, o, e = run(src, "--out", out)
        self.assertEqual(code, 0, e)
        res = self.read(out, "Sohbet-1", "Sohbet-1.md")
        for bad in ("Xandor", "Plimm", "Quorvel", "Tisk", "Test Grubu", "Ahmet"):
            self.assertNotIn(bad, res)
        self.assertIn("- Katılımcılar: Kişi 1\n", res)                  # grup adi katilimci sayilmaz
        self.assertIn("- Mesaj sayısı: 1\n", res)

    def test_one_to_one_contact_messages_untouched(self):
        msgs, _ = wa2md.parse("[14.11.2026 09:00:00] Xandor Plimm: Ali geldi ve ayrıldı\n"
                              "[14.11.2026 09:01:00] Xandor Plimm: tamam\n")
        self.assertEqual(wa2md.mark_system_lines("Xandor Plimm", msgs)[0]["sender"], "Xandor Plimm")


class F05AttachmentAllowList(Tmp):
    NAMES = ["a.docm", "b.xlsm", "c.eml", "d.ics", "e.html", "f.json", "g.md", "h.gpx", "i.tif", "uzantisiz", "j.pdf",
             "k.vcf"]
    COPIED = ["IMG-1.jpg", "VID-1.mp4", "PTT-1.opus"]

    def test_only_media_copied_by_default(self):
        files = {n: b"x" for n in self.NAMES + self.COPIED}
        text = "".join(H % (i, "Can Er", f"{n} (dosya ekli)") + "\n" for i, n in enumerate(files))
        src = make_dir(self.tmp, "Satranç Kulübü", text, files)
        out = os.path.join(self.tmp, "o")
        code, o, e = run(src, "--out", out)
        self.assertEqual(code, 0, e)
        self.assertEqual(sorted(os.listdir(os.path.join(out, "Sohbet-1", "media"))), sorted(self.COPIED))
        man = self.read(out, "Sohbet-1", "ekler.md")
        for n in self.NAMES:
            self.assertRegex(man, rf"\| {n} \| [^|]+ \| kopyalanmadı")
        out2 = os.path.join(self.tmp, "o2")
        code, o, e = run(src, "--out", out2, "--belgeleri-kopyala")
        self.assertEqual(sorted(os.listdir(os.path.join(out2, "Sohbet-1", "media"))), sorted(files))


class F06Surnames(unittest.TestCase):
    def test_known_first_name_with_other_surname_is_other_person(self):
        out, a = md(chat([("Kenan Er", "selam"), "Kenan Karakoç da gelecek, Kenan Er de"]))
        self.assertNotIn("Karakoç", out)
        her = a.labels["Kenan Er"]
        self.assertIn(f"{her} de", out)
        self.assertNotIn(f"{her} da gelecek", out)                      # farkli kisi, farkli etiket
        self.assertRegex(out, r"Kişi \d+ da gelecek")

    def test_surname_with_honorific_at_line_start(self):
        out, _ = md(chat(["Karakoç Hoca yarın gelecek", "Şimşek abi aradı"]))
        self.assertNotIn("Karakoç", out)
        self.assertNotIn("Şimşek", out)
        self.assertRegex(out, r"Kişi \d+ Hoca yarın gelecek")

    def test_surname_by_morphology_and_third_part(self):
        out, _ = md(chat(["Orhan Öztürkoğlu aradı", "Mehmet Ali Xandor geldi"]))
        for bad in ("Öztürkoğlu", "Xandor", "Mehmet"):
            self.assertNotIn(bad, out)


class F07Mentions(unittest.TestCase):
    def test_mentions_of_non_participants(self):
        out, _ = md(chat(["@Mehmet toplantı kaçta?", "@Xandor bak, Xandor geldi", "@905000001122 ara", "ali@ornek.test"]))
        for bad in ("Mehmet", "Xandor", "5000001122", "ali@"):
            self.assertNotIn(bad, out)
        self.assertIn("[telefon] ara", out)
        self.assertIn("[e-posta]", out)
        self.assertRegex(out, r"\nKişi \d+ toplantı kaçta\?")


class F08AmbiguousWords(unittest.TestCase):
    LOWER = ["yarın bora bekleniyor", "sonunda nail olduk", "halim selim biridir", "seher vakti kalktık",
             "ramazan ayında", "hilal göründü", "erdem sahibi", "kamil bir insan", "poyraz esti", "fırat kenarında",
             "ceyhan nehri", "dicle kıyısı", "mert duruş", "ozan türkü söyledi", "ece kraliçe demek", "cihan harbi",
             "yavuz bir hareket", "şahin uçtu", "ceylan koştu", "yasemin kokusu"]
    FIXED = ["Hz. Muhammed", "Mimar Sinan Üniversitesi", "Fatih Sultan Mehmet Köprüsü", "Atatürk Caddesi"]

    def test_lowercase_ambiguous_words_untouched_and_counted(self):
        out, a = md(chat(self.LOWER))
        for s in self.LOWER:
            self.assertIn(s, out)
        self.assertGreaterEqual(len(a.review), len(self.LOWER) - 1)     # 'halim selim': iki sozcuk

    def test_fixed_expressions_untouched(self):
        out, a = md(chat([f"dün {s} tarafına gittik" for s in self.FIXED]))
        for s in self.FIXED:
            self.assertIn(f"dün {s} tarafına", out)

    def test_clues_still_mask(self):
        out, _ = md(chat(["bora'ya söyle", "bora abi geldi", "toplantıda Bora konuştu"]))
        self.assertNotIn("bora", out.lower().replace("sohbet", ""))

    def test_list_header_records_sources(self):
        with open(os.path.join(os.path.dirname(HERE), "adlar", "sozcuk-adlar.txt"), encoding="utf-8") as f:
            head = f.read()
        for s in ("Wikidata", "CC0", "2026-11-15", "elle derlendi", "Sorgu"):
            self.assertIn(s, head)


class F09MissingDictionary(Tmp):
    def setUp(self):
        super().setUp()
        self.old = wa2md._HERE
        wa2md._HERE = self.tmp                 # adlar/ yok
        wa2md._LISTS.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        wa2md._HERE = self.old
        wa2md._LISTS.clear()

    def test_refuses_without_flag(self):
        src = make_dir(self.tmp, "Satranç Kulübü", chat(["Ahmet geldi"]))
        out = os.path.join(self.tmp, "o")
        code, o, e = run(src, "--out", out)
        self.assertEqual(code, 2)
        self.assertIn("ad sözlüğü eksik", e)
        self.assertFalse(os.path.exists(out))
        code, o, e = run(src, "--out", out, "--sozluksuz")
        self.assertEqual(code, 0, e)
        self.assertIn("ad sözlüğü YOK", o)
        code, o, e = run(src, "--out", os.path.join(self.tmp, "o2"), "--no-anonim")   # anonimsiz: sozluk gerekmez
        self.assertEqual(code, 0, e)


class F10MissingAttachmentNames(Tmp):
    def test_missing_files_get_neutral_names(self):
        src = make_dir(self.tmp, "Satranç Kulübü", chat(["Kenan_Celik_CV.pdf (dosya ekli)", "<ek: Naime_Kaya.jpg>"]))
        out = os.path.join(self.tmp, "o")
        code, o, e = run(src, "--out", out)
        self.assertEqual(code, 0, e)
        res = self.read(out, "Sohbet-1", "Sohbet-1.md") + self.read(out, "Sohbet-1", "ekler.md")
        for bad in ("Kenan", "Celik", "Naime", "Kaya"):
            self.assertNotIn(bad, res)
        self.assertIn("(dosya eksik: medya-1.pdf)", res)
        self.assertIn("eksik (dışa aktarımda yok)", res)


class F11OneLabelPerPerson(unittest.TestCase):
    def test_first_name_then_full_name(self):
        out, _ = md(chat(["Ahmet geldi", "Ahmet Yıldırım aradı"]))
        self.assertRegex(out, r"(Kişi \d+) geldi\n\n\*\*Kişi 1\*\* 09:04\n\1 aradı")
        out, _ = md(chat(["Ahmet Yıldırım aradı", "Ahmet geldi"]))
        self.assertRegex(out, r"(Kişi \d+) aradı\n\n\*\*Kişi 1\*\* 09:04\n\1 geldi")


class F12SystemLineComma(unittest.TestCase):
    def test_comma_kept(self):
        out, _ = md(chat(["x"]) + "14.11.2026 10:00 - Vlemo Drax, bu grubun davet bağlantısıyla katıldı\n")
        self.assertRegex(out, r"Kişi \d+, bu grubun davet")
        self.assertNotIn("Vlemo", out)


class F13SocialHandles(unittest.TestCase):
    def test_handles_and_wa_me(self):
        out, _ = md(chat(["instagram.com/handle_one ve https://www.linkedin.com/in/handle-two bak",
                          "x.com/handle_three/status/1 ve wa.me/905000001122 ve tiktok.com/@handle_four",
                          "instagram.com/p/Cx12 gönderi"]))
        for bad in ("handle_one", "handle-two", "handle_three", "905000001122", "handle_four"):
            self.assertNotIn(bad, out)
        self.assertIn("instagram.com/[kullanıcı] ve https://www.linkedin.com/in/[kullanıcı]", out)
        self.assertIn("wa.me/[telefon]", out)
        self.assertIn("instagram.com/p/Cx12", out)                    # gonderi yolu kisisel degil


class F14Sayin(unittest.TestCase):
    def test_prefix_honorific_unknown_name(self):
        out, _ = md(chat(["Sayın Xandor Plimm, rapor ekte", "Sn. Quorvel Tisk aradı"]))
        for bad in ("Xandor", "Plimm", "Quorvel", "Tisk"):
            self.assertNotIn(bad, out)
        self.assertRegex(out, r"Sayın Kişi \d+, rapor ekte")

    def test_titles_after_sayin_untouched(self):
        for s in ("Sayın Başkan geldi", "Sayın Yetkili", "Sayın Üyelerimiz", "Sayın Velimiz"):
            out, _ = md(chat([s]))
            self.assertIn(s, out)


class F15FixtureTitles(unittest.TestCase):
    def test_fixtures_use_unrelated_organisation_names(self):
        for fn in os.listdir(HERE):
            if fn.endswith(".py") and fn != os.path.basename(__file__):
                with open(os.path.join(HERE, fn), encoding="utf-8") as f:
                    self.assertNotIn("Arama Kurtarma", f.read(), fn)


class F16Performance(unittest.TestCase):
    def test_long_unbroken_token_is_linear(self):
        out, a = md(chat(["selam"]))
        t = time.time()
        a.text("Ab1." * 50000)                 # 200k karakter; onceki surumde 20k karakter ~27 s
        self.assertLess(time.time() - t, 10)


if __name__ == "__main__":
    unittest.main()
