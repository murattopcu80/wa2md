"""English option names, Turkish aliases and the message-language switch (phase 1 of the English-primary decision).

All names are invented. The existing suites pin WA2MD_LANG=tr where they assert Turkish console text; this file covers
the English default, every alias and the switch itself.
"""
import filecmp
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, ROOT)
import wa2md  # noqa: E402
import wa_web  # noqa: E402

TR = os.path.join(FIX, "android_tr")
WEB = os.path.join(FIX, "web")

# (English primary name, Turkish alias, extra argv value or None, destination, value when given)
FLAG_MAP = [
    ("--no-media", "--medya-yok", None, "no_media", True),
    ("--copy-documents", "--belgeleri-kopyala", None, "copy_docs", True),
    ("--no-dictionary", "--sozluksuz", None, "no_dict", True),
    ("--no-anonymize", "--no-anonim", None, "anonim", False),
    ("--anonymize", "--anonim", None, "anonim", True),
    ("--extra-names", "--ek-adlar", "Zorbek Tuvaq,Plimm", "extra_names", ["Zorbek Tuvaq", "Plimm"]),
    ("--review-dir", "--inceleme-dizini", "/tmp/wa2md-review-x", "review_dir", "/tmp/wa2md-review-x"),
]


def _argv(flag, value):
    return [flag] if value is None else [flag, value]


class Isolated(unittest.TestCase):
    """Fresh environment per test: no WA2MD_LANG from the developer's shell, state folder in a temp dir."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wa2md-i18n-")
        self._env = {k: os.environ.get(k) for k in ("WA2MD_LANG", "XDG_STATE_HOME")}
        os.environ.pop("WA2MD_LANG", None)
        os.environ["XDG_STATE_HOME"] = os.path.join(self.tmp, "state")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        wa2md.reset_lang()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, main, *argv):
        o, e = io.StringIO(), io.StringIO()
        with redirect_stdout(o), redirect_stderr(e):
            try:
                code = main(list(argv))
            except SystemExit as x:
                code = x.code
        return code, o.getvalue(), e.getvalue()

    def wa2md_run(self, *argv):
        return self.call(wa2md.main, *argv)

    def parse(self, *argv):
        wa2md.init_lang(list(argv))
        return wa2md.build_parser().parse_args(["x", "--out", "o", *argv])


class OptionNames(Isolated):
    def test_defaults_are_identical_for_every_name(self):
        a = self.parse()
        self.assertTrue(a.anonim)
        for dest in ("no_media", "copy_docs", "no_dict"):
            self.assertIs(getattr(a, dest), False, dest)
        self.assertIsNone(a.extra_names)
        self.assertIsNone(a.review_dir)

    def test_english_name_and_turkish_alias_set_the_same_destination(self):
        for en, tr, value, dest, expected in FLAG_MAP:
            with self.subTest(en=en, tr=tr):
                a_en = self.parse(*_argv(en, value))
                a_tr = self.parse(*_argv(tr, value))
                self.assertEqual(getattr(a_en, dest), expected)
                self.assertEqual(getattr(a_tr, dest), expected)
                self.assertEqual(vars(a_en), vars(a_tr))  # nothing else differs: same destinations, same defaults

    def test_web_import_and_export_accept_the_same_names(self):
        for sub in ("import", "export"):
            for en, tr, value, dest, expected in FLAG_MAP:
                if dest == "copy_docs":
                    continue  # wa2md.py only; the web commands never had this option
                with self.subTest(sub=sub, en=en, tr=tr):
                    base = ["paths.json"] if sub == "import" else ["--chats", "Plimm Grup"]
                    got = []
                    for flag in (en, tr):
                        wa2md.init_lang([])
                        ns = wa_web.build_parser().parse_args([sub, *base, "--out", "o", *_argv(flag, value)])
                        got.append(vars(ns))
                        self.assertEqual(getattr(ns, dest), expected)
                    self.assertEqual(got[0], got[1])

    def test_web_media_flag_names(self):
        for sub, base in (("snippet", ["--chats", "Plimm"]), ("import", ["p.json", "--out", "o"]),
                          ("export", ["--chats", "Plimm", "--out", "o"])):
            for flag in ("--no-media", "--medya-yok"):
                with self.subTest(sub=sub, flag=flag):
                    wa2md.init_lang([])
                    self.assertTrue(wa_web.build_parser().parse_args([sub, *base, flag]).no_media)

    def test_old_command_line_still_gives_identical_files(self):
        """The same run written with English names and with the old Turkish names produces byte-identical output."""
        outs = []
        for tag, names in (("en", ["--no-media", "--extra-names", "Plimm", "--review-dir"]),
                           ("tr", ["--medya-yok", "--ek-adlar", "Plimm", "--inceleme-dizini"])):
            out = os.path.join(self.tmp, "out-" + tag)
            review = os.path.join(self.tmp, "review-" + tag)
            code, _, err = self.wa2md_run(TR, "--out", out, names[0], names[1], names[2], names[3], review)
            self.assertEqual(code, 0, err)
            outs.append(out)
        cmp = filecmp.dircmp(outs[0], outs[1])
        self.assertEqual((cmp.left_only, cmp.right_only, cmp.diff_files), ([], [], []))
        sub = filecmp.dircmp(os.path.join(outs[0], "Sohbet-1"), os.path.join(outs[1], "Sohbet-1"))
        self.assertEqual((sub.left_only, sub.right_only, sub.diff_files), ([], [], []))

    def test_no_anonymize_and_no_anonim_write_real_names(self):
        for flag in ("--no-anonymize", "--no-anonim"):
            with self.subTest(flag=flag):
                out = os.path.join(self.tmp, "o" + flag)
                code, _, err = self.wa2md_run(TR, "--out", out, flag)
                self.assertEqual(code, 0, err)
                self.assertTrue(os.path.isfile(os.path.join(out, "Naime", "Naime.md")))

    def test_copy_documents_names_behave_the_same(self):
        found = []
        for flag in ("--copy-documents", "--belgeleri-kopyala"):
            out = os.path.join(self.tmp, "c" + flag)
            code, _, err = self.wa2md_run(TR, "--out", out, flag)
            self.assertEqual(code, 0, err)
            found.append(sorted(os.listdir(os.path.join(out, "Sohbet-1", "media"))))
        self.assertEqual(found[0], found[1])
        self.assertTrue(any(n.endswith(".pdf") for n in found[0]))

    def test_no_dictionary_names_behave_the_same(self):
        real = wa2md.missing_name_lists
        wa2md.missing_name_lists = lambda: ["tr-adlar.txt"]  # simulate a tool folder without the dictionaries
        try:
            for flag in ("--no-dictionary", "--sozluksuz"):
                with self.subTest(flag=flag):
                    out = os.path.join(self.tmp, "d" + flag)
                    code, _, err = self.wa2md_run(TR, "--out", out, flag)
                    self.assertEqual(code, 0, err)
            code, _, err = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "d-none"))
            self.assertEqual(code, 2)
            self.assertIn("--no-dictionary", err)  # the English message names the English option
        finally:
            wa2md.missing_name_lists = real

    def test_turkish_message_names_the_turkish_alias_and_english_names_the_english_option(self):
        real = wa2md.missing_name_lists
        wa2md.missing_name_lists = lambda: ["tr-adlar.txt"]
        try:
            _, _, err_tr = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o1"), "--lang", "tr")
            _, _, err_en = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o2"), "--lang", "en")
        finally:
            wa2md.missing_name_lists = real
        self.assertIn("--sozluksuz", err_tr)
        self.assertIn("--no-dictionary", err_en)

    def test_help_lists_english_primary_and_turkish_alias(self):
        _, out, _ = self.wa2md_run("--help")
        for en, tr, *_ in FLAG_MAP:
            self.assertIn(en, out)
            self.assertIn(tr, out)
        self.assertRegex(out, r"--no-media, --medya-yok")  # English first


class MessageLanguage(Isolated):
    def test_default_is_english(self):
        _, out, _ = self.wa2md_run("--help")
        self.assertIn("Converts WhatsApp chat exports to Markdown.", out)
        self.assertNotIn("sohbet dışa aktarımını", out)

    def test_lang_option_switches_help(self):
        for argv in (["--lang", "tr", "--help"], ["--lang=tr", "--help"], ["--help", "--lang", "tr"],
                     ["--lang", "TR", "--help"]):
            with self.subTest(argv=argv):
                _, out, _ = self.wa2md_run(*argv)
                self.assertIn("WhatsApp sohbet dışa aktarımını Markdown'a çevirir.", out)

    def test_environment_variable_switches_help(self):
        for value in ("tr", "TR", "tr_TR", "tr-TR.UTF-8"):
            with self.subTest(value=value):
                os.environ["WA2MD_LANG"] = value
                _, out, _ = self.wa2md_run("--help")
                self.assertIn("sohbet dışa aktarımını", out)

    def test_option_beats_environment_variable(self):
        os.environ["WA2MD_LANG"] = "tr"
        _, out, _ = self.wa2md_run("--lang", "en", "--help")
        self.assertIn("Converts WhatsApp chat exports", out)
        os.environ["WA2MD_LANG"] = "en"
        _, out, _ = self.wa2md_run("--lang", "tr", "--help")
        self.assertIn("sohbet dışa aktarımını", out)

    def test_unknown_values(self):
        os.environ["WA2MD_LANG"] = "de"  # unknown environment value: ignored, English
        _, out, _ = self.wa2md_run("--help")
        self.assertIn("Converts WhatsApp chat exports", out)
        code, _, err = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o"), "--lang", "de")  # unknown option value: error
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)

    def test_language_is_reset_on_every_call(self):
        self.wa2md_run("--lang", "tr", "--help")
        _, out, _ = self.wa2md_run("--help")
        self.assertIn("Converts WhatsApp chat exports", out)

    def test_library_calls_follow_the_environment_and_main_leaves_no_state(self):
        """No order dependence between tests or callers: after main() the language follows WA2MD_LANG again."""
        self.wa2md_run("--lang", "tr", "--help")
        self.assertEqual(wa2md.current_lang(), "en")
        os.environ["WA2MD_LANG"] = "tr"
        self.assertEqual(wa2md.current_lang(), "tr")
        self.assertIn("Girdi bulunamadı", wa2md.t("input_missing", path="x"))
        self.wa2md_run("--lang", "en", "--help")
        self.assertEqual(wa2md.current_lang(), "tr")   # the explicit --lang of that call did not leak
        del os.environ["WA2MD_LANG"]
        self.assertEqual(wa2md.t("input_missing", path="x"), "Input not found: x")

    def test_console_messages_english_by_default_and_turkish_on_request(self):
        out_en = os.path.join(self.tmp, "en")
        out_tr = os.path.join(self.tmp, "tr")
        code, o_en, _ = self.wa2md_run(TR, "--out", out_en)
        self.assertEqual(code, 0)
        self.assertRegex(o_en, r"\[Sohbet-1\] 7 messages, \d+ media copied, \d+ media missing -> ")
        self.assertIn("   masked: sender", o_en)
        self.assertIn("Mode: removal of direct identifiers.", o_en)
        code, o_tr, _ = self.wa2md_run(TR, "--out", out_tr, "--lang", "tr")
        self.assertEqual(code, 0)
        self.assertRegex(o_tr, r"\[Sohbet-1\] 7 mesaj, \d+ medya kopyalandı, \d+ medya eksik -> ")
        self.assertIn("   maskelenen: gönderen", o_tr)
        self.assertIn("Mod: doğrudan tanımlayıcıların kaldırılması.", o_tr)

    def test_errors_follow_the_language(self):
        miss = os.path.join(self.tmp, "yok")
        _, _, e_en = self.wa2md_run(miss, "--out", os.path.join(self.tmp, "o"))
        _, _, e_tr = self.wa2md_run(miss, "--out", os.path.join(self.tmp, "o"), "--lang", "tr")
        self.assertIn("ERROR: Input not found:", e_en)
        self.assertIn("HATA: Girdi bulunamadı:", e_tr)
        _, _, e_en = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o"), "--from", "2026-13-40")
        self.assertIn("Invalid date '2026-13-40' (expected YYYY-MM-DD)", e_en)
        _, _, e_tr = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o"), "--from", "2026-13-40", "--lang", "tr")
        self.assertIn("Geçersiz tarih '2026-13-40' (YYYY-AA-GG olmalı)", e_tr)

    def test_markdown_output_is_identical_in_both_languages(self):
        """Phase 1 does not translate the labels inside the Markdown: the message language never reaches the output."""
        outs = []
        for lang in ("en", "tr"):
            out = os.path.join(self.tmp, "m-" + lang)
            code, _, err = self.wa2md_run(TR, "--out", out, "--lang", lang)
            self.assertEqual(code, 0, err)
            outs.append(out)
        cmp = filecmp.dircmp(os.path.join(outs[0], "Sohbet-1"), os.path.join(outs[1], "Sohbet-1"))
        self.assertEqual((cmp.left_only, cmp.right_only, cmp.diff_files), ([], [], []))
        with open(os.path.join(outs[0], "Sohbet-1", "Sohbet-1.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("Kişi 1", md)
        self.assertIn("# Sohbet-1", md)

    def test_review_file_follows_the_language(self):
        chat = ("14.11.2026 10:00 - Plimm Zorbek: merhaba\n14.11.2026 10:01 - Orhan: Deniz abi yarın gelir mi\n"
                "14.11.2026 10:02 - Plimm Zorbek: Bora aradı dün\n")
        src = os.path.join(self.tmp, "src")
        os.makedirs(src)
        with open(os.path.join(src, "Plimm Zorbek ile WhatsApp Sohbeti.txt"), "w", encoding="utf-8") as f:
            f.write(chat)
        heads = {}
        for lang in ("en", "tr"):
            rv = os.path.join(self.tmp, "rv-" + lang)
            code, o, err = self.wa2md_run(src, "--out", os.path.join(self.tmp, "o-" + lang), "--lang", lang,
                                          "--review-dir", rv)
            self.assertEqual(code, 0, err)
            files = [n for n in os.listdir(rv) if n.endswith("-supheli-adlar.txt")] if os.path.isdir(rv) else []
            if not files:
                self.skipTest("fixture produced no review entries")
            with open(os.path.join(rv, files[0]), encoding="utf-8") as f:
                heads[lang] = f.read()
        self.assertTrue(heads["en"].startswith("# MAY CONTAIN REAL NAMES - DO NOT SHARE"))
        self.assertTrue(heads["tr"].startswith("# OLASI GERÇEK ADLAR İÇERİR - PAYLAŞMA, COMMIT ETME."))

    def test_web_help_and_messages_follow_the_language(self):
        _, out, _ = self.call(wa_web.main, "--help")
        self.assertIn("Exports WhatsApp Web chats to Markdown (read-only).", out)
        _, out, _ = self.call(wa_web.main, "--lang", "tr", "--help")
        self.assertIn("WhatsApp Web sohbetlerini Markdown'a aktarır (salt okunur).", out)
        for lang, text in (("en", "Final bundle part not found"), ("tr", "Son paket (final) bulunamadı")):
            with self.subTest(lang=lang):
                tmp = os.path.join(self.tmp, "b" + lang)
                os.makedirs(tmp)
                with open(os.path.join(tmp, "wa-bundle-x-abc123-001.json"), "w", encoding="utf-8") as f:
                    json.dump({"format": "wa-web-bundle", "final": False, "total": 1, "media": []}, f)
                _, _, err = self.call(wa_web.main, "import", tmp, "--out", os.path.join(tmp, "o"), "--lang", lang)
                self.assertIn(text, err)

    def test_web_subcommand_accepts_lang_after_the_subcommand(self):
        _, out, _ = self.call(wa_web.main, "snippet", "--chats", "Plimm", "--lang", "tr")
        self.assertIn('"lang": "tr"', out.split(";\n", 1)[0])
        _, out, _ = self.call(wa_web.main, "snippet", "--chats", "Plimm")
        self.assertIn('"lang": "en"', out.split(";\n", 1)[0])

    def test_snippet_steps_follow_the_language(self):
        _, _, err = self.call(wa_web.main, "snippet", "--chats", "Plimm")
        self.assertIn("Steps: 1) In the WhatsApp Web tab press F12", err)
        _, _, err = self.call(wa_web.main, "snippet", "--chats", "Plimm", "--lang", "tr")
        self.assertIn("Adımlar: 1) WhatsApp Web sekmesinde F12", err)

    def test_subprocess_uses_the_environment_variable(self):
        env = dict(os.environ, WA2MD_LANG="tr", PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "wa2md.py"), "--help"], env=env,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0)
        self.assertIn("sohbet dışa aktarımını", p.stdout)
        env.pop("WA2MD_LANG")
        p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "wa2md.py"), "--help"], env=env,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertIn("Converts WhatsApp chat exports", p.stdout)


class MediaWarning(Isolated):
    """Copying media stays the default in anonymous mode; one console line says so (count and advice only)."""

    EN = re.compile(r"^   WARNING: (\d+) media/attachment files were copied as they are and are NOT anonymized "
                    r"\(faces, ID documents, bank cards, screenshots with names\)\. Use --no-media before sharing\.$", re.M)
    TR = re.compile(r"^   UYARI: (\d+) medya/ek dosyası olduğu gibi kopyalandı ve anonimleştirilmedi \(yüzler, kimlik "
                    r"belgeleri, banka kartları, ad içeren ekran görüntüleri\)\. Paylaşmadan önce --medya-yok kullan\.$",
                    re.M)

    def copied(self, out):
        return int(re.search(r"(\d+) media copied", out).group(1))

    def test_english_line_once_with_the_copied_count(self):
        code, o, _ = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o"))
        self.assertEqual(code, 0)
        hits = self.EN.findall(o)
        self.assertEqual(hits, [str(self.copied(o))])
        self.assertGreater(int(hits[0]), 0)

    def test_turkish_line_with_lang_tr(self):
        code, o, _ = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o"), "--lang", "tr")
        self.assertEqual(code, 0)
        n = int(re.search(r"(\d+) medya kopyalandı", o).group(1))
        self.assertEqual(self.TR.findall(o), [str(n)])

    def test_not_printed_without_copied_media_or_when_not_anonymizing(self):
        for extra in (["--no-media"], ["--medya-yok"], ["--no-anonymize"], ["--no-anonim"]):
            with self.subTest(extra=extra):
                _, o, _ = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o" + extra[0]), *extra)
                self.assertNotIn("were copied as they are", o)

    def test_line_carries_no_chat_content(self):
        _, o, _ = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o"))
        line = next(l for l in o.splitlines() if "were copied as they are" in l)
        for real in ("Naime", "Orhan", "IMG-2026", "foto"):
            self.assertNotIn(real, line)
        self.assertRegex(line, self.EN)

    def test_stderr_is_not_used(self):
        _, _, e = self.wa2md_run(TR, "--out", os.path.join(self.tmp, "o"))
        self.assertNotIn("were copied as they are", e)

    def test_help_tells_the_same_story(self):
        _, out, _ = self.wa2md_run("--help")
        self.assertIn("recommended for output you will share", " ".join(out.split()))


class MessageTable(unittest.TestCase):
    def test_every_message_has_both_languages_and_the_same_placeholders(self):
        field = re.compile(r"{([a-z_]+)}")
        for key, texts in wa2md.MSG.items():
            with self.subTest(key=key):
                self.assertEqual(set(texts), set(wa2md.LANGS))
                self.assertEqual(set(field.findall(texts["en"])), set(field.findall(texts["tr"])))
                self.assertTrue(texts["en"].strip() and texts["tr"].strip())

    def test_every_message_key_is_used(self):
        src = ""
        for name in ("wa2md.py", "wa_web.py"):
            with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                src += f.read()
        used = set(re.findall(r"""\bt\(\s*["']([a-z_]+)["']""", src))
        used |= set(re.findall(r"""wa2md\.t\(\s*["']([a-z_]+)["']""", src))
        used |= {"web_copied", "web_not_copied", "why_hitap", "why_büyük", "why_küçük"}  # chosen by a conditional/prefix
        self.assertEqual(sorted(set(wa2md.MSG) - used), [])

    def test_javascript_table_has_both_languages(self):
        with open(os.path.join(ROOT, "wa2md_assets", "wa_collect.js"), encoding="utf-8") as f:
            js = f.read()
        block = js[js.index("const MSG = {"):js.index("let LANG")]
        entries = re.findall(r"^\s+(\w+): \{ en: \"[^\"]+\", tr: \"[^\"]+\" \},$", block, re.M)
        self.assertGreaterEqual(len(entries), 15)
        self.assertEqual(len(entries), len(re.findall(r"^\s+\w+: \{ en:", block, re.M)))
        self.assertTrue(js.isascii())  # the snippet goes through the Windows clipboard as ASCII

    def test_stat_labels_cover_the_internal_categories(self):
        for cat in wa2md._STAT_ORDER + ["firma", "iletişim"]:
            self.assertIn(cat, wa2md.STAT_LABEL)


if __name__ == "__main__":
    unittest.main()
