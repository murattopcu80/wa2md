"""ikinci bagimsiz inceleme (B1, S1-S7, N1-N4) ve onceki bulgularin regresyonu.
Tum adlar, numaralar, sohbetler ve dosya adlari uydurmadir."""
import io
import json
import os
import shutil
import stat
import sys
import tempfile
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


# --- uc disa aktarim bicimi: (gonderen, metin) ya da (None, sistem satiri) -> sohbet metni
def android_tr(rows, day=14):
    return "".join(f"{day:02d}.11.2026 09:{i:02d} - " + (f"{s}: {t}" if s else t) + "\n" for i, (s, t) in enumerate(rows))


def android_en(rows, day=14):
    return "".join(f"11/{day}/26, 9:{i:02d} AM - " + (f"{s}: {t}" if s else t) + "\n" for i, (s, t) in enumerate(rows))


def ios(rows, title, day=14):
    """iOS: sistem satirlari gonderen yerinde sohbet adiyla gelir (onlerinde gorunmez LRM isareti)."""
    return "".join(f"[{day:02d}.11.2026 09:{i:02d}:00] " + (f"{s}: {t}" if s else f"{title}: ‎{t}") + "\n"
                   for i, (s, t) in enumerate(rows))


FORMATS = {"android_tr": lambda rows, title: android_tr(rows), "android_en": lambda rows, title: android_en(rows),
           "ios": ios}
GROUP = [("Kenan Ergin", "selam"), ("Melis Tarnu", "selam"), ("Jorvik Plimm", "selam")]   # 3 gonderen: grup


def md(text, title="Örnek Satranç Kulübü", group=None, **kw):
    """Uretimdeki yol: tum dosya uzerinden grup karari, sistem satirlari, tek Anonymizer, tek render."""
    msgs, _ = wa2md.parse(wa2md.decode(text.encode("utf-8")))
    if group is None:
        group = wa2md.is_group(msgs, title)
    msgs = wa2md.mark_system_lines(title, msgs, group)
    a = wa2md.Anonymizer(title, msgs, 1, None, group=group)
    out, _, _ = wa2md.render(title, msgs, None, anon=a, **kw)
    return out, a


def body(out):
    return "\n".join(l for l in out.split("\n") if l.strip() and not l.startswith(("#", "- ")))


def run(*argv):
    o, e = io.StringIO(), io.StringIO()
    with redirect_stdout(o), redirect_stderr(e):
        code = wa2md.main(list(argv))
    return code, o.getvalue(), e.getvalue()


def make_dir(root, title, text, files=None, ios_layout=False):
    d = os.path.join(root, f"WhatsApp Chat - {title}" if ios_layout else f"WhatsApp Chat with {title}")
    os.makedirs(d)
    name = "_chat.txt" if ios_layout else f"WhatsApp Chat with {title}.txt"
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        f.write(text)
    for n, data in (files or {}).items():
        with open(os.path.join(d, n), "wb") as f:
            f.write(data)
    return d


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def read(self, *p):
        with open(os.path.join(*p), encoding="utf-8") as f:
            return f.read()

    def chat_md(self, out):
        d = [x for x in os.listdir(out) if x.startswith("Sohbet-")][0]
        return self.read(out, d, d + ".md")


# ------------------------------------------------------------------ B1
class B1Landmark(unittest.TestCase):
    LEAK = ["Kenan Ankara Hastanesinde yatıyor", "Kenan müzesinde", "Kenan istasyonu bekliyor",
            "Zeynep Gazi Üniversitesi'ni kazandı", "Hz. Kenan geldi", "Selin Kadıköy Lisesinde okuyor",
            "dün Sinan üniversitesi dedi", "Zeynep Ankara Caddesi'nde oturuyor"]
    KEEP = ["Mimar Sinan Üniversitesi", "Fatih Sultan Mehmet Köprüsü", "Atatürk Caddesi", "Hz. Muhammed"]

    def test_participant_and_loose_forms_masked_in_all_formats(self):
        for fmt, mk in FORMATS.items():
            with self.subTest(fmt=fmt):
                out, a = md(mk(GROUP + [("Melis Tarnu", t) for t in self.LEAK], "Örnek Satranç Kulübü"))
                for bad in ("Kenan", "Zeynep", "Selin", "Sinan"):
                    self.assertNotIn(bad, body(out))
                self.assertIn("Ankara Hastanesinde yatıyor", out)       # kurum adinin kendisi kalir
                self.assertGreater(a.stats.get("yer/kurum belirsiz", 0), 0)

    def test_narrow_proper_noun_phrase_untouched(self):
        for fmt, mk in FORMATS.items():
            with self.subTest(fmt=fmt):
                out, _ = md(mk(GROUP + [("Melis Tarnu", ", ".join(self.KEEP))], "Örnek Satranç Kulübü"))
                self.assertIn(", ".join(self.KEEP), out)

    def test_participant_name_part_never_exempt(self):
        rows = [("Sinan Ergin", "selam"), ("Melis Tarnu", "selam"), ("Jorvik Plimm", "selam"),
                ("Melis Tarnu", "Mimar Sinan Üniversitesi ve Hz. Sinan")]
        out, _ = md(android_tr(rows))
        self.assertNotIn("Sinan", body(out))
        self.assertIn("Mimar Kişi 1 Üniversitesi", out)


# ------------------------------------------------------------------ S1, S5, S6, N3: bire bir / grup karari
class S1IosOneToOneEventLikeLines(unittest.TestCase):
    TITLE = "Xandor Dree"

    def rows(self):
        return [("Xandor Dree", "Messages and calls are end-to-end encrypted."), ("Xandor Dree", "Kardeşim de katıldı."),
                ("Xandor Dree", "Ali ayrıldı, Veli left"), ("Zarvo Kentel", "Xandor Dree bey ne zaman gelir? Xandor çok iyi")]

    def test_contact_lines_stay_messages_and_name_masked(self):
        for fmt, mk in FORMATS.items():
            with self.subTest(fmt=fmt):
                text = mk(self.rows(), self.TITLE)
                msgs, _ = wa2md.parse(wa2md.decode(text.encode()))
                self.assertFalse(wa2md.is_group(msgs, self.TITLE))
                out, a = md(text, self.TITLE)
                self.assertFalse(a.group)
                for bad in ("Xandor", "Dree"):
                    self.assertNotIn(bad, body(out))
                self.assertRegex(out, r"\*\*Kişi \d+\*\* 09:01\nKardeşim de katıldı\.")

    def test_real_group_event_lines_still_converted(self):
        rows = [(None, 'Zarvo Kentel created group "Örnek Satranç Kulübü"'), (None, "Zarvo Kentel added Melis Tarnu"),
                (None, "Jorvik Plimm joined using this group's invite link"), (None, "Qelvin Yorst left"),
                ("Zarvo Kentel", "Jorvik, Qelvin nerede?")]
        tr = [(None, 'Zarvo Kentel "Örnek Satranç Kulübü" grubunu oluşturdu'), (None, "Zarvo Kentel, Melis Tarnu'yu ekledi"),
              (None, "Jorvik Plimm, bu grubun davet bağlantısıyla katıldı"), (None, "Qelvin Yorst ayrıldı"),
              ("Zarvo Kentel", "Jorvik, Qelvin nerede?")]
        for fmt, text in (("android_en", android_en(rows)), ("android_tr", android_tr(tr)),
                          ("ios_en", ios(rows, "Örnek Satranç Kulübü")), ("ios_tr", ios(tr, "Örnek Satranç Kulübü"))):
            with self.subTest(fmt=fmt):
                out, a = md(text)
                self.assertTrue(a.group)
                for bad in ("Jorvik", "Plimm", "Qelvin", "Yorst", "Melis"):
                    self.assertNotIn(bad, body(out))
                self.assertIn("- Katılımcılar: Kişi 1\n", out)


class S5OneToOneDecidedFromWholeExport(Tmp):
    def text(self, fmt, title):
        d14 = [(title, "merhaba")]
        d15 = [("Zarvo Kentel", f"{title} yarın gelir, xandor plimm de")]
        if fmt == "ios":
            return ios(d14, title, 14) + ios(d15, title, 15)
        f = android_tr if fmt == "android_tr" else android_en
        return f(d14, 14) + f(d15, 15)

    def test_title_with_group_word_or_four_words_masked(self):
        for title in ("Xandor Plimm Apartman", "Jorvik Van Der Plimm", "Plimm Ekibi Xandor"):
            for fmt in FORMATS:
                with self.subTest(title=title, fmt=fmt):
                    root = os.path.join(self.tmp, f"{fmt}-{len(title)}")
                    src = make_dir(root, title, self.text(fmt, title), ios_layout=fmt == "ios")
                    out = os.path.join(root, "o")
                    code, o, e = run(src, "--out", out, "--from", "2026-11-15")
                    self.assertEqual(code, 0, e)
                    res = self.chat_md(out)
                    for tok in title.split():
                        self.assertNotIn(tok, body(res))
                        self.assertNotIn(tok.lower(), body(res))

    def test_real_group_keeps_title_words(self):
        rows = GROUP + [("Kenan Ergin", "Satranç Kulübü toplantısı, kulübü arayın")]
        src = make_dir(self.tmp, "Satranç Kulübü", android_tr(rows[:3], 14) + android_tr(rows[3:], 15))
        out = os.path.join(self.tmp, "o")
        code, o, e = run(src, "--out", out, "--from", "2026-11-15")
        self.assertEqual(code, 0, e)
        self.assertIn("Satranç Kulübü toplantısı, kulübü arayın", self.chat_md(out))


class S6IosMemberNamedLikeGroup(unittest.TestCase):
    def test_event_lines_converted_member_messages_kept(self):
        for lang, ev in (("tr", ['Zarvo Kentel "Annem" grubunu oluşturdu', "Zarvo Kentel, Jorvik Plimm adlı kişiyi ekledi"]),
                         ("en", ['Zarvo Kentel created group "Annem"', "Zarvo Kentel added Jorvik Plimm"])):
            with self.subTest(lang=lang):
                rows = [("Annem", "Mesajlar ve aramalar uçtan uca şifrelidir.")] + [("Annem", e) for e in ev] + [
                    ("Annem", "Yarın yemeğe gelin"), ("Annem", "Kardeşim de katıldı."),
                    ("Zarvo Kentel", "tamam, Jorvik de gelir")]
                out, a = md(ios(rows, "Annem"), "Annem")
                self.assertTrue(a.group)
                for bad in ("Jorvik", "Plimm", "Zarvo", "Annem"):
                    self.assertNotIn(bad, body(out))
                self.assertRegex(out, r"\*\*Kişi \d+\*\* 09:03\nYarın yemeğe gelin\n")
                self.assertRegex(out, r"\*\*Kişi \d+\*\* 09:04\nKardeşim de katıldı\.")
                self.assertRegex(out, r"_09:02 – Kişi \d+,? (?:added )?Kişi \d+")


class N3TwoSendersWithoutTitleIsGroup(unittest.TestCase):
    def test_two_senders_none_is_title_is_group(self):
        for fmt, mk in FORMATS.items():
            with self.subTest(fmt=fmt):
                rows = [("Zarvo Kentel", "Kuzey Yıldızı Çalışma yarın. kuzey yıldızı parlak"), ("Melis Tarnu", "tamam")]
                out, a = md(mk(rows, "Kuzey Yıldızı"), "Kuzey Yıldızı")
                self.assertTrue(a.group)
                self.assertIn("kuzey yıldızı parlak", out)

    def test_one_to_one_with_contact_as_sender_masks_title(self):
        for fmt, mk in FORMATS.items():
            with self.subTest(fmt=fmt):
                rows = [("Zarvo Kentel", "yarın xandor plimm gelir"), ("Xandor Plimm", "tamam")]
                out, a = md(mk(rows, "Xandor Plimm"), "Xandor Plimm")
                self.assertFalse(a.group)
                self.assertNotIn("xandor", body(out).lower())


# ------------------------------------------------------------------ S2
class S2PersonNamedGroupTitle(unittest.TestCase):
    def rows(self, title, text):
        return [(None, f'Zarvo Kentel created group "{title}"'), (None, "Zarvo Kentel added Melis Tarnu")] + GROUP + [
            ("Zarvo Kentel", text)]

    def test_only_name_like_title_tokens_masked(self):
        cases = [("Selin Doğum Günü", "doğum günü pastası alalım, günü belli mi? Doğum günü kutlu olsun",
                  "Selin gelir mi? Selin Doğum Günü listesi", ["Selin"]),
                 ("Okul Velileri Kenan", "Okul velileri toplantısı, okul açık", "Kenan'a sor", ["Kenan"]),
                 ("Plimm Ailesi", "aile toplantısı yarın", "Plimm'ler gelir, Plimm Ailesi toplanıyor", ["Plimm"])]
        for title, keep, leak, bad in cases:
            for fmt, mk in FORMATS.items():
                with self.subTest(title=title, fmt=fmt):
                    out, a = md(mk(self.rows(title, keep), title), title)
                    self.assertTrue(a.group)
                    self.assertIn(keep, out)                       # siradan sozcukler (Doğum, Günü, Okul) kalir
                    out, a = md(mk(self.rows(title, leak), title), title)
                    for b in bad:
                        self.assertNotIn(b, body(out))


# ------------------------------------------------------------------ S3, N1, N2: inceleme klasoru, on denetim, web yolu
TEXT = android_tr(GROUP + [("Kenan Ergin", "Bahar geldi, Umut abi'ye söyle"), ("Melis Tarnu", "Poyraz esiyor")])


class S3ReviewDirSymlinkIntoRepo(Tmp):
    def test_symlink_into_git_tree_refused(self):
        src = make_dir(self.tmp, "Satranç Kulübü", TEXT)
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        os.makedirs(os.path.join(repo, "alt"))
        os.symlink(os.path.join(repo, "alt"), os.path.join(self.tmp, "bag"))     # depo icindeki bir klasore bag
        for rv in (os.path.join(self.tmp, "bag"), os.path.join(self.tmp, "bag", "yeni", "alt")):
            with self.subTest(rv=rv):
                out = os.path.join(self.tmp, "o")
                code, o, e = run(src, "--out", out, "--inceleme-dizini", rv)
                self.assertEqual(code, 2)
                self.assertIn("git çalışma ağacının", e)
                self.assertFalse(os.path.exists(out))
                self.assertEqual(sorted(os.listdir(repo)), [".git", "alt"])
                self.assertEqual(os.listdir(os.path.join(repo, "alt")), [])
        self.assertIsNotNone(wa2md.git_work_tree(os.path.join(self.tmp, "bag", "yok", "daha")))

    def test_symlink_outside_git_accepted(self):
        src = make_dir(self.tmp, "Satranç Kulübü", TEXT)
        os.makedirs(os.path.join(self.tmp, "disarisi"))
        os.symlink(os.path.join(self.tmp, "disarisi"), os.path.join(self.tmp, "bag2"))
        code, o, e = run(src, "--out", os.path.join(self.tmp, "o"), "--inceleme-dizini", os.path.join(self.tmp, "bag2"))
        self.assertEqual(code, 0, e)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "disarisi", "Sohbet-1-supheli-adlar.txt")))


@unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root her yere yazar")
class N1ReviewDirCheckedFirst(Tmp):
    def test_read_only_or_uncreatable_review_dir_exit_2_before_output(self):
        src = make_dir(self.tmp, "Satranç Kulübü", TEXT)
        ro = os.path.join(self.tmp, "salt-okunur")
        os.makedirs(ro)
        os.chmod(ro, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, ro, stat.S_IRWXU)
        with open(os.path.join(self.tmp, "dosya"), "w") as f:
            f.write("x")
        for rv in (ro, os.path.join(ro, "alt"), os.path.join(self.tmp, "dosya", "alt")):
            with self.subTest(rv=rv):
                out = os.path.join(self.tmp, "o")
                code, o, e = run(src, "--out", out, "--inceleme-dizini", rv)
                self.assertEqual(code, 2)
                self.assertIn("inceleme klasörü oluşturulamıyor ya da yazılamıyor", e)
                self.assertNotIn("beklenmeyen hata", e)
                self.assertFalse(os.path.exists(out))
        env = os.environ["XDG_STATE_HOME"]
        os.environ["XDG_STATE_HOME"] = ro                       # varsayilan konum yazilamiyor
        self.addCleanup(os.environ.__setitem__, "XDG_STATE_HOME", env)
        code, o, e = run(src, "--out", os.path.join(self.tmp, "o"))
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "o")))

    def test_writable_dir_check_leaves_no_empty_folders(self):
        rv = os.path.join(self.tmp, "a", "b", "c")
        self.assertIsNone(wa2md.writable_dir(rv))
        self.assertEqual(os.listdir(self.tmp), [])
        src = make_dir(self.tmp, "Satranç Kulübü", android_tr(GROUP))
        code, o, e = run(src, "--out", os.path.join(self.tmp, "o"), "--inceleme-dizini", rv)
        self.assertEqual(code, 0, e)


class N2WebRouteSamePath(Tmp):
    def bundle(self):
        rows = [{"id": "AC%030d" % i, "system": None, "out": False, "stamp": f"[14:0{i}, 14.11.2026] {s}: ", "meta": None,
                 "author": None, "text": t, "quote": None, "deleted": False, "forwarded": False, "media": [],
                 "divider": None} for i, (s, t) in enumerate([("Kenan Ergin", "selam"), ("Melis Tarnu", "Umut abi geldi"),
                                                             ("Jorvik Plimm", "tamam")])]
        p = {"format": "wa-web-bundle", "version": 1, "session": "s1", "part": 1, "chat": "Satranç Kulübü", "final": True,
             "media": [], "total": 1, "rows": rows, "today": "2026-11-16", "opts": {}}
        path = os.path.join(self.tmp, "wa-bundle-x-s1-001.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f)
        return path

    def web(self, *argv):
        import wa_web
        o, e = io.StringIO(), io.StringIO()
        with redirect_stdout(o), redirect_stderr(e):
            code = wa_web.main(list(argv))
        return code, o.getvalue(), e.getvalue()

    def test_missing_dictionary_exit_2_and_flag(self):
        path = self.bundle()
        old = wa2md._HERE
        wa2md._HERE = os.path.join(self.tmp, "yok")
        wa2md._LISTS.clear()

        def restore():
            wa2md._HERE = old
            wa2md._LISTS.clear()
        self.addCleanup(restore)
        out = os.path.join(self.tmp, "o")
        code, o, e = self.web("import", path, "--out", out)
        self.assertEqual(code, 2)
        self.assertIn("ad sözlüğü eksik", e)
        self.assertNotIn("beklenmeyen hata", e)
        self.assertFalse(os.path.exists(out))
        code, o, e = self.web("import", path, "--out", out, "--sozluksuz", "--inceleme-dizini", os.path.join(self.tmp, "rv"))
        self.assertEqual(code, 0, e)
        self.assertIn("ad sözlüğü YOK", o)

    def test_review_dir_extra_names_and_git_guard(self):
        path = self.bundle()
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        code, o, e = self.web("import", path, "--out", os.path.join(self.tmp, "o1"), "--inceleme-dizini", repo)
        self.assertEqual(code, 2)
        self.assertIn("git çalışma ağacının", e)
        out = os.path.join(self.tmp, "o2")
        code, o, e = self.web("import", path, "--out", out, "--inceleme-dizini", os.path.join(self.tmp, "rv"),
                              "--ek-adlar", "Poyraz")
        self.assertEqual(code, 0, e)
        res = self.chat_md(out)
        self.assertNotIn("Umut", res)
        self.assertNotIn("Kenan", res)


# ------------------------------------------------------------------ S4, S7
class S4CaptionThatIsAFileName(unittest.TestCase):
    def texts(self, caption):
        return {"android_tr": android_tr(GROUP) + f"14.11.2026 10:00 - Zarvo Kentel: sifre.pdf (dosya ekli)\n{caption}\n",
                "android_en": android_en(GROUP) + f"11/14/26, 10:00 AM - Zarvo Kentel: sifre.pdf (file attached)\n{caption}\n",
                "ios": ios(GROUP, "Örnek Satranç Kulübü") + f"[14.11.2026 10:00:00] Zarvo Kentel: <attached: 00000012-sifre.pdf>\n"
                                                          f"{caption}\n"}

    def test_file_name_caption_untouched(self):
        for cap in ("şifre listesi.pdf", "parola kurtarma formu.docx", "pin kodları.xlsx"):
            for fmt, text in self.texts(cap).items():
                with self.subTest(cap=cap, fmt=fmt):
                    out, _ = md(text)
                    self.assertIn(cap, out)
                    self.assertNotIn("[parola]", out)

    def test_file_name_message_without_attachment_untouched(self):
        for fmt, mk in FORMATS.items():
            with self.subTest(fmt=fmt):
                rows = GROUP + [("Melis Tarnu", "rapor.pdf (dosya ekli)"), ("Melis Tarnu", "şifre listesi.pdf"),
                                ("Melis Tarnu", "PDF şifresi: Kartal.2024"), ("Melis Tarnu", "Ostra.2024")]
                out, _ = md(mk(rows, "Örnek Satranç Kulübü"))
                self.assertIn("\nşifre listesi.pdf\n", out)
                for secret in ("Kartal.2024", "Ostra.2024"):
                    self.assertNotIn(secret, out)

    def test_password_caption_still_masked(self):
        for cap, secret in (("PDF şifresi: Kartal.2024", "Kartal.2024"), ("zip parolası Deneme!77x", "Deneme!77x"),
                            ("pin=4821.pdf", "4821")):
            for fmt, text in self.texts(cap).items():
                with self.subTest(cap=cap, fmt=fmt):
                    out, _ = md(text)
                    self.assertNotIn(secret, out)
                    self.assertIn("[parola]", out)


class S7BareSocialHandle(unittest.TestCase):
    def test_handles_masked_other_at_rules_kept(self):
        for fmt, mk in FORMATS.items():
            with self.subTest(fmt=fmt):
                line = "@xandor.plimm ve @xandor_plimm takip, @905321112233 ara, @Qelvin bak, mail ali@ornek.com, @ahmet."
                out, _ = md(mk(GROUP + [("Melis Tarnu", line)], "Örnek Satranç Kulübü"))
                for bad in ("xandor", "plimm", "905321112233", "Qelvin", "ali@", "ahmet"):
                    self.assertNotIn(bad, body(out).lower() if bad.islower() else body(out))
                self.assertIn("[kullanıcı] ve [kullanıcı] takip, @[telefon] ara, Kişi", out)
                self.assertIn("mail [e-posta]", out)


# ------------------------------------------------------------------ regresyon: onceki turlarin bulgulari geri gelmesin
class RegressionEarlierFindings(Tmp):
    """Onceki iki turun (onceki uc surum) duzelttigi durumlar uctan uca (CLI) yeniden oynatilir."""
    ANDROID = android_tr(GROUP + [
        (None, "Kenan Ergin, Qelvin Yorst ve Ostra Vell adlı kişileri ekledi"),
        (None, "Pamir Druv, bu grubun davet bağlantısıyla katıldı"),
        ("Kenan Ergin", "rapor.pdf (dosya ekli)"), ("Kenan Ergin", "PDF şifresi: Kartal.2024"),
        ("Melis Tarnu", "Teklif_2024.pdf (dosya ekli)"), ("Melis Tarnu", "IMG-20261114-WA0001.jpg (dosya ekli)"),
        ("Melis Tarnu", "VID-20261114-WA0002.mp4 (dosya ekli)"), ("Melis Tarnu", "Jorvik Plimm.vcf (dosya ekli)"),
        ("Melis Tarnu", "Kenan_Celik_CV.pdf (dosya ekli)"),
        ("Jorvik Plimm", "Qelvin, Ostra, Pamir hepiniz gelin; Druv'a söyle"),
        ("Jorvik Plimm", "Kenan Karakoç da gelecek, Karakoç Hoca derse girdi, Şimşek abi aradı"),
        ("Jorvik Plimm", "@Nuvel bakar mısın? @Melis sen de"),
        ("Jorvik Plimm", "bora gibi esti, ramazan ayı geldi, umut ediyorum, deniz kenarı"),
        ("Jorvik Plimm", "Ahmet geldi. Ahmet Yıldırım aradı. Kenan Ergin aynı kişi değil"),
        ("Jorvik Plimm", "Sayın Xandor Plimmer, Sayın Yetkili, Sayın Üyelerimiz"),
    ])
    IOS = ios([(None, 'Kenan Ergin created group "Örnek Satranç Kulübü"'), (None, "Kenan Ergin added Xandor Dree"),
               (None, "Quorvel Tisk joined using this group's invite link"),
               ("Kenan Ergin", "Xandor nerede? Quorvel geldi mi?"), ("Melis Tarnu", "tamam"), ("Jorvik Plimm", "ok")],
              "Örnek Satranç Kulübü")

    def run_chat(self, title, text, files=(), extra=(), ios_layout=False):
        root = tempfile.mkdtemp(dir=self.tmp)
        src = make_dir(root, title, text, {f: b"x" * 10 for f in files}, ios_layout=ios_layout)
        out, rv = os.path.join(root, "o"), os.path.join(root, "rv")
        code, o, e = run(src, "--out", out, "--inceleme-dizini", rv, *extra)
        self.assertEqual(code, 0, e)
        return out, rv, self.chat_md(out), o

    def test_android_group_end_to_end(self):
        files = ["rapor.pdf", "Teklif_2024.pdf", "IMG-20261114-WA0001.jpg", "VID-20261114-WA0002.mp4", "Jorvik Plimm.vcf"]
        out, rv, res, o = self.run_chat("Örnek Satranç Kulübü", self.ANDROID, files)
        b = body(res)
        # parola ekten sonra maskelenir; gercek ek basliklari dokunulmaz
        self.assertNotIn("Kartal.2024", res)
        self.assertIn("PDF şifresi: [parola]", res)
        self.assertIn("Teklif_2024.pdf", res)
        # sistem satiri kisileri (Android)
        for bad in ("Kenan", "Melis", "Jorvik", "Qelvin", "Yorst", "Ostra", "Vell", "Pamir", "Druv"):
            self.assertNotIn(bad, b)
        # bilinen ad + baska soyad = baska kisi; soyad + hitap; @Ad; Sayın Ad
        self.assertNotIn("Karakoç", b)
        self.assertNotIn("Şimşek", b)
        self.assertNotIn("Nuvel", b)
        self.assertNotIn("Plimmer", b)
        self.assertIn("Sayın Yetkili, Sayın Üyelerimiz", res)
        # kucuk harfli siradan sozcukler
        self.assertIn("bora gibi esti, ramazan ayı geldi, umut ediyorum, deniz kenarı", res)
        # bir kisi bir etiket, iki kisi iki etiket
        import re
        line = [l for l in res.split("\n") if l.endswith("aynı kişi değil")][0]
        labs = re.findall(r"Kişi \d+", line)
        self.assertEqual(len(labs), 3)
        self.assertEqual(labs[0], labs[1])                 # Ahmet == Ahmet Yıldırım (sozlukle bulunan tek ad + soyad)
        self.assertEqual(labs[2], "Kişi 1")                # Kenan Ergin: gonderen etiketi
        line = [l for l in res.split("\n") if "da gelecek" in l][0]
        self.assertNotRegex(line, r"^Kişi 1 da gelecek")   # Kenan Karakoç: katilimci adi + baska soyad = baska kisi
        self.assertRegex(line, r"^Kişi \d+ da gelecek")
        # izin listesi: yalniz goruntu/video kopyalanir; eksik ek notr ad alir
        media = sorted(os.listdir(os.path.join(out, "Sohbet-1", "media")))
        self.assertEqual(media, ["IMG-20261114-WA0001.jpg", "VID-20261114-WA0002.mp4"])
        ekler = self.read(out, "Sohbet-1", "ekler.md")
        self.assertIn("kopyalanmadı", ekler)
        self.assertNotIn("Plimm", ekler)
        self.assertNotIn("Celik", ekler + res)
        self.assertRegex(ekler, r"medya-\d+\.pdf \| PDF \| eksik")
        # inceleme dosyasi --out disinda ve icerigi ciktida aynen duruyor
        self.assertEqual(os.listdir(out), ["Sohbet-1"])
        rev = self.read(rv, "Sohbet-1-supheli-adlar.txt")
        for r in (x.split("\t") for x in rev.split("\n") if x and not x.startswith("#")):
            self.assertIn(r[0], res)
            for ex in r[3].split(" | "):
                self.assertIn(ex, res)

    def test_ios_system_line_people(self):
        out, rv, res, o = self.run_chat("Örnek Satranç Kulübü", self.IOS, ios_layout=True)
        for bad in ("Xandor", "Dree", "Quorvel", "Tisk", "Kenan", "Satranç"):
            self.assertNotIn(bad, body(res))

    def test_titles(self):
        one = android_tr([("Xandor Plimm", "merhaba")], 14) + android_tr(
            [("Zarvo Kentel", "Xandor Plimm'e ilet, Xandor'a da söyle")], 15)
        out, rv, res, o = self.run_chat("Xandor Plimm", one, extra=("--from", "2026-11-15"))
        self.assertNotIn("Xandor", body(res))
        self.assertNotIn("Plimm", body(res))
        fam = android_tr(GROUP + [("Kenan Ergin", "Plimm Ailesi toplantısı, Plimm'ler gelir")])
        out, rv, res, o = self.run_chat("Plimm Ailesi", fam)
        self.assertIn("Sohbet-1 toplantısı", res)
        self.assertNotIn("Plimm", body(res).replace("Kişi", ""))
        org = android_tr(GROUP + [("Kenan Ergin", "Satranç Kulübü toplantısı cumartesi, kulübü arayın")])
        out, rv, res, o = self.run_chat("Satranç Kulübü", org)
        self.assertIn("Satranç Kulübü toplantısı cumartesi, kulübü arayın", res)

    def test_allow_list_copy_flag(self):
        files = ["rapor.pdf", "IMG-20261114-WA0001.jpg"]
        text = android_tr(GROUP + [("Kenan Ergin", f"{f} (dosya ekli)") for f in files])
        out, rv, res, o = self.run_chat("Örnek Satranç Kulübü", text, files, extra=("--belgeleri-kopyala",))
        self.assertEqual(sorted(os.listdir(os.path.join(out, "Sohbet-1", "media"))), sorted(files))

    def test_missing_name_lists_exit_2(self):
        old = wa2md._HERE
        wa2md._HERE = os.path.join(self.tmp, "yok")
        wa2md._LISTS.clear()

        def restore():
            wa2md._HERE = old
            wa2md._LISTS.clear()
        self.addCleanup(restore)
        src = make_dir(self.tmp, "Örnek Satranç Kulübü", android_tr(GROUP))
        out = os.path.join(self.tmp, "o")
        code, o, e = run(src, "--out", out)
        self.assertEqual(code, 2)
        self.assertIn("ad sözlüğü eksik", e)
        self.assertFalse(os.path.exists(out))


class IosEventPeopleWithoutConversion(unittest.TestCase):
    def test_anonymizer_collects_people_from_unconverted_title_lines(self):
        """Cagiran mark_system_lines'i atlasa da (dogrudan Anonymizer) grup adiyla gelen olay satirlarinin kisileri
        maskelenir; bire bir sohbette karsi tarafin olay gibi mesaji kisi toplamaz."""
        text = ios([(None, 'Kenan Ergin created group "Test Grubu"'), (None, "Kenan Ergin added Xandor Plimm"),
                    (None, "Quorvel Tisk joined using this group's invite link"),
                    ("Kenan Ergin", "Xandor nerede? Quorvel geldi mi?")], "Test Grubu")
        msgs, _ = wa2md.parse(wa2md.decode(text.encode()))
        a = wa2md.Anonymizer("Test Grubu", msgs, 1, None)
        out, _, _ = wa2md.render("Test Grubu", msgs, None, anon=a)
        for bad in ("Xandor", "Plimm", "Quorvel", "Tisk", "Kenan"):
            self.assertNotIn(bad, out)
        one = ios([("Xandor Dree", "Kardeşim de katıldı."), ("Zarvo Kentel", "tamam")], "Xandor Dree")
        msgs, _ = wa2md.parse(wa2md.decode(one.encode()))
        a = wa2md.Anonymizer("Xandor Dree", msgs, 1, None)
        self.assertNotIn("Kardeşim de", a.labels)


class LongLineFromTitleSender(unittest.TestCase):
    def test_long_message_from_sender_named_like_chat_is_linear(self):
        import time
        long = ("Naime Ankara " * 4000).strip()
        for group in (False, True):
            with self.subTest(group=group):
                rows = ([("Zarvo Kentel", "selam")] + ([("Melis Tarnu", "selam")] if group else [])
                        + [("Zarvo Kentel", long), (None, "Zarvo Kentel added Jorvik Plimm")])
                t = time.time()
                out, a = md(android_en(rows), "Zarvo Kentel")
                self.assertLess(time.time() - t, 10)
                self.assertNotIn("Naime", out)


class ProbeCasesThirdReview(unittest.TestCase):
    """Ucuncu tur inceleme betiklerindeki (t9, t13) ve birim testte henuz olmayan durumlar."""

    def test_turkish_number_change_and_comma_left_people_masked(self):
        rows = [(None, "Zarvo Kentel, Melis Tarnu ve Jorvik Plimm adlı kişileri ekledi"),
                (None, "Qelvin Yorst, +90 532 111 22 33 numarasına geçti"), (None, "Ostra Vell, left"),
                ("Zarvo Kentel", "Qelvin, Ostra gelin. Yorst ve Vell de"), ("Melis Tarnu", "Ostra'ya söyle")]
        out, a = md(android_tr(rows))
        for bad in ("Qelvin", "Yorst", "Ostra", "Vell", "532"):
            self.assertNotIn(bad, body(out))

    def test_non_participant_dictionary_name_in_group_title_lower_case(self):
        title = "Okul Velileri Kenan"
        rows = [(None, f'Zarvo Kentel created group "{title}"'), (None, "Zarvo Kentel added Melis Tarnu"),
                ("Zarvo Kentel", "Okul velileri toplantısı, kenan da gelsin")]
        out, a = md(android_en(rows), title)
        self.assertIn("Okul velileri toplantısı, ", out)
        self.assertNotIn("kenan", body(out).lower())
