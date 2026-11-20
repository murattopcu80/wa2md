"""Pack selection and output labels (issue #2): --packs / WA2MD_PACKS, the automatic rule, merged pack sets, labels
that follow --lang / WA2MD_LANG. All chats and names are invented."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import wa2md  # noqa: E402
import wa2md_lang  # noqa: E402

TR_TEXT = ["merhaba abi yarın gelir misin", "tamam ben de geliyorum, çok iyi olur", "evet bu akşam konuşuruz"]
EN_TEXT = ["hi there, are you coming tomorrow", "yes I will be there with the van", "thanks, see you at the depot"]
# chats in languages without a pack (review of a65d79e, B3): no pack may win on shared short words or accented letters
THIRD = {
    "es": ["Hola, mañana voy con Emily a la oficina de Madrid", "Vale, dile a Jessica que llame"],
    "fr": ["Bonjour, je vais avec Emily à la gare de Lyon demain", "Oui, dis à Jessica de venir"],
    "nl": ["Hoi, ik ga morgen met Emily naar de winkel", "Ja, zeg tegen Jessica dat ze komt"],
    "pt": ["Olá, amanhã vou com a Emily ao escritório de Lisboa", "Diz à Jessica que ligue"],
    "de": ["Guten Morgen, der Lastwagen kommt morgen früh", "Alles klar, ich rufe Emily an, danke schön",
           "Bis morgen dann, tschüss"],
}


def msgs(texts, sender="Harriet Plimm"):
    return [{"sender": sender, "lines": [t]} for t in texts]


class Env(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("WA2MD_LANG", "WA2MD_PACKS", "XDG_STATE_HOME")}
        self.tmp = tempfile.mkdtemp()
        os.environ.pop("WA2MD_LANG", None)
        os.environ.pop("WA2MD_PACKS", None)
        os.environ["XDG_STATE_HOME"] = os.path.join(self.tmp, "state")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        wa2md.use_pack(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = wa2md.main(list(argv))
        return code, out.getvalue(), err.getvalue()


class Detection(Env):
    def test_turkish_chat_selects_turkish_only(self):
        self.assertEqual(wa2md.detect_packs(msgs(TR_TEXT)), ("tr",))

    def test_english_chat_selects_english_only(self):
        self.assertEqual(wa2md.detect_packs(msgs(EN_TEXT)), ("en",))

    def test_mixed_chat_selects_both(self):
        self.assertEqual(wa2md.detect_packs(msgs(TR_TEXT + EN_TEXT)), ("tr", "en"))

    def test_a_few_english_words_in_a_turkish_chat_do_not_add_english(self):
        self.assertEqual(wa2md.detect_packs(msgs(TR_TEXT * 3 + ["ok thanks"])), ("tr",))

    def test_system_lines_do_not_vote(self):
        """A Turkish chat exported from an English-language phone: English system lines, Turkish messages."""
        sys_lines = [{"sender": None, "lines": ["Harriet Plimm added Zorbek Tuvaq"]} for _ in range(20)]
        self.assertEqual(wa2md.detect_packs(sys_lines + msgs(TR_TEXT)), ("tr",))

    def test_web_path_messages_vote_with_their_text_parts(self):
        web = [{"sender": "Harriet Plimm", "parts": [("text", t), ("note", "Forwarded message")]} for t in EN_TEXT]
        self.assertEqual(wa2md.detect_packs(web), ("en",))

    def test_third_language_chats_select_every_pack(self):
        for lang, texts in THIRD.items():
            with self.subTest(lang=lang):
                scores, _ = wa2md.pack_scores(msgs(texts))
                self.assertLess(max(scores), wa2md._SEL_FLOOR, scores)     # es fr nl pt: 0.0 0.0; de: 0.0 0.053
                self.assertEqual(wa2md.detect_packs(msgs(texts)), wa2md_lang.PACKS)

    def test_turkish_without_turkish_letters_selects_turkish(self):
        self.assertEqual(wa2md.detect_packs(msgs(["slm", "naber", "iyiyim sen", "aksam cikalim mi"])), ("tr",))
        self.assertEqual(wa2md.detect_packs(msgs(["aksam gelirmisin", "olur saat 8de", "Mehmet de gelsin"])), ("tr",))

    def test_shared_short_words_and_letters_are_no_turkish_evidence(self):
        scores, _ = wa2md.pack_scores(msgs(["de da ne mi su ki her", "ö ü ç Müller Göteborg Français"]))
        self.assertEqual(scores[0], 0.0)

    def test_media_only_chat_selects_every_pack(self):
        self.assertEqual(wa2md.detect_packs(msgs(["<Media omitted>", "<Media omitted>"])), wa2md_lang.PACKS)

    def test_dominant_language_by_message_votes(self):
        tr8 = ["merhaba abi nasılsın", "iyiyim sen nasılsın", "akşam gelir misin", "tamam geliyorum",
               "yarın saat kaçta", "bilmiyorum daha sonra yazarım", "evet olur", "sağol abi"]
        _, votes = wa2md.pack_scores(msgs(tr8 + EN_TEXT[:2]))
        self.assertEqual(votes, [8, 2])
        self.assertEqual(wa2md._dominant(("tr", "en"), votes), "tr")            # 8 of 10 >= 3/4
        self.assertIsNone(wa2md._dominant(("tr", "en"), wa2md.pack_scores(msgs(TR_TEXT + EN_TEXT))[1]))  # balanced
        self.assertIsNone(wa2md._dominant(("tr", "en"), [5, 0]))                 # fewer than 6 voting messages
        self.assertIsNone(wa2md._dominant(("tr",), [9, 0]))                      # one pack: nothing to weigh

    def test_third_language_chat_masks_the_names_of_every_pack(self):
        d = os.path.join(self.tmp, "es")
        os.makedirs(d)
        with open(os.path.join(d, "WhatsApp Chat with Zorbek Tuvaq.txt"), "w", encoding="utf-8") as f:
            f.write("11/14/26, 10:00 AM - Zorbek Tuvaq: " + THIRD["es"][0] + "\n11/14/26, 10:01 AM - Harriet Plimm: "
                    + THIRD["es"][1] + "\n")
        out = os.path.join(self.tmp, "out")
        code, o, err = self.run_cli(d, "--out", out, "--review-dir", os.path.join(self.tmp, "rv"))
        self.assertEqual(code, 0, err)
        self.assertIn("tr, en - 2 of 2", o)
        with open(os.path.join(out, "Chat-1", "Chat-1.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertNotIn("Emily", md)
        self.assertNotIn("Jessica", md)

    def test_no_signal_selects_every_pack(self):
        self.assertEqual(wa2md.detect_packs(msgs(["👍", "12:30", "ok"])), wa2md_lang.PACKS)
        self.assertEqual(wa2md.detect_packs([]), wa2md_lang.PACKS)


class Options(Env):
    def test_normalisation(self):
        self.assertEqual(wa2md._norm_packs("auto"), "auto")
        self.assertEqual(wa2md._norm_packs("EN,tr"), ("tr", "en"))
        self.assertEqual(wa2md._norm_packs("en tr"), ("tr", "en"))
        self.assertIsNone(wa2md._norm_packs("de"))
        self.assertIsNone(wa2md._norm_packs(""))

    def test_option_beats_environment_beats_auto(self):
        self.assertEqual(wa2md.current_packs(), "auto")
        os.environ["WA2MD_PACKS"] = "en"
        self.assertEqual(wa2md.current_packs(), ("en",))
        wa2md.init_lang(["--packs", "tr"])
        try:
            self.assertEqual(wa2md.current_packs(), ("tr",))
        finally:
            wa2md.reset_lang()
        self.assertEqual(wa2md.current_packs(), ("en",))

    def test_unknown_value_is_an_error(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_cli(os.path.join(HERE, "fixtures", "android_en"), "--out", self.tmp, "--packs", "de")
        self.assertEqual(cm.exception.code, 2)

    def test_unknown_environment_value_is_an_error_too(self):
        os.environ["WA2MD_PACKS"] = "de"
        err = io.StringIO()
        with self.assertRaises(SystemExit) as cm, redirect_stdout(io.StringIO()), redirect_stderr(err):
            wa2md.main([os.path.join(HERE, "fixtures", "android_en"), "--out", self.tmp])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("WA2MD_PACKS", err.getvalue())
        import wa_web
        with self.assertRaises(SystemExit) as cm, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            wa_web.main(["list"])
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(self.run_cli(os.path.join(HERE, "fixtures", "android_en"), "--out", self.tmp, "--packs",
                                      "en")[0], 0)                       # --packs beats the bad environment value


class MergedSets(unittest.TestCase):
    def tearDown(self):
        wa2md.use_pack(None)

    def test_turkish_alone_is_the_turkish_pack(self):
        self.assertIs(wa2md_lang.merge(("tr",), labels="tr"), wa2md_lang.load_pack("tr"))

    def test_export_words_are_the_same_in_every_selection(self):
        sets = [wa2md_lang.merge(c, labels="en") for c in (("tr",), ("en",), ("tr", "en"))]
        for f in wa2md_lang.EXPORT_FIELDS:
            values = {repr(getattr(p, f)) for p in sets}
            self.assertEqual(len(values), 1, f)

    def test_union_of_words_and_files(self):
        both = wa2md_lang.merge(("en", "tr"), labels="en")
        self.assertEqual(both.code, "tr+en")
        self.assertIn("ltd", both.legal_form)
        self.assertIn("inc", both.legal_form)
        self.assertIn("mr", both.title_before)
        self.assertIn("sayin", both.title_before)
        self.assertEqual(both.dictionary_files["given"], ("tr-adlar.txt", "en-given.txt", "en-given-more.txt"))
        self.assertEqual(both.labels.chat, "Chat-{n}")

    def test_alternatives_split_at_top_level_only(self):
        self.assertEqual(wa2md_lang.split_alternatives(r"a|(b|c)|[|]|\|"), ["a", "(b|c)", "[|]", r"\|"])

    def test_pin_and_unpin(self):
        tr = wa2md_lang.load_pack("tr")
        wa2md.use_pack("en")
        wa2md.Anonymizer("x", msgs(TR_TEXT))         # pinned: the chat's own text does not reselect
        self.assertEqual(wa2md.active_pack().code, "en")
        self.assertIs(wa2md.use_pack(None), tr)


class Labels(Env):
    def run_fixture(self, *extra):
        out = os.path.join(self.tmp, "out")
        code, o, err = self.run_cli(os.path.join(HERE, "fixtures", "android_tr"), "--out", out, "--review-dir",
                                    os.path.join(self.tmp, "rv"), *extra)
        self.assertEqual(code, 0, err)
        return out, o

    def test_english_labels_by_default(self):
        out, o = self.run_fixture()
        self.assertTrue(os.path.isfile(os.path.join(out, "Chat-1", "Chat-1.md")))
        with open(os.path.join(out, "Chat-1", "Chat-1.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("- Participants: Person 1", md)

    def test_turkish_labels_with_lang_tr_or_environment(self):
        out, _ = self.run_fixture("--lang", "tr")
        self.assertTrue(os.path.isfile(os.path.join(out, "Sohbet-1", "Sohbet-1.md")))
        shutil.rmtree(out)
        os.environ["WA2MD_LANG"] = "tr"
        out, _ = self.run_fixture()
        self.assertTrue(os.path.isfile(os.path.join(out, "Sohbet-1", "Sohbet-1.md")))

    def test_labels_do_not_depend_on_the_packs(self):
        out, _ = self.run_fixture("--packs", "tr")
        self.assertTrue(os.path.isfile(os.path.join(out, "Chat-1", "Chat-1.md")))


class ConsoleLine(Env):
    """One console line per chat states the automatically selected packs (codes and counts only)."""
    def run_fixture(self, name, *extra):
        out = os.path.join(self.tmp, "out-" + "-".join((name,) + extra))
        code, o, err = self.run_cli(os.path.join(HERE, "fixtures", name), "--out", out, "--review-dir",
                                    os.path.join(self.tmp, "rv"), *extra)
        self.assertEqual(code, 0, err)
        return [ln.strip() for ln in o.splitlines() if ln.strip().startswith(("Language packs", "Dil paketleri"))]

    def test_auto_selection_is_reported_in_both_languages(self):
        self.assertEqual(self.run_fixture("en_android_uk24"), ["Language packs (auto, from the chat text): en - 1 of 2"])
        self.assertEqual(self.run_fixture("android_tr", "--lang", "tr"),
                         ["Dil paketleri (otomatik, sohbet metninden): tr - 2 paketten 1"])

    def test_explicit_selection_prints_nothing(self):
        self.assertEqual(self.run_fixture("en_android_uk24", "--packs", "en,tr"), [])
        os.environ["WA2MD_PACKS"] = "tr"
        self.assertEqual(self.run_fixture("android_tr"), [])


if __name__ == "__main__":
    unittest.main()
