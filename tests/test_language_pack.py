"""Language-pack interface (issue #2): the pack contract, and label invariance (every pattern that contains an output
label is built from the pack's labels: a different label set gives the same output with only the labels replaced)."""
import dataclasses
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import _pin  # noqa: E402  (Turkish pack set and labels, issue #2)
import wa2md  # noqa: E402
import wa2md_lang  # noqa: E402

SYNTH = {"phone": "<ph>", "company": "<co>", "path": "<pa>", "email": "<em>", "user": "<us>", "password": "<pw>",
         "code": "<cd>", "iban": "<ib>", "national_id": "<id>", "plate": "<pl>"}


def synthetic(pack):
    L = pack.labels
    return dataclasses.replace(pack, labels=dataclasses.replace(
        L, chat="Chat-{n}", person_word="Pers", masks=SYNTH, media="m-{n}{ext}", participants="Parts",
        message_count="Count", date_range="Range", media_omitted="_(omit)_", file_missing="_(miss: {name})_",
        attachment_not_copied="_(skip: {name}, {kind})_"))


def substitute(text, L):
    """Turkish output -> the same output written with the synthetic labels (mechanical)."""
    text = re.sub(re.escape(L.person_word) + r"([ \-])(\d+|\?)", r"Pers\1\2", text)
    for kind, mask in L.masks.items():
        text = text.replace(mask, SYNTH[kind])
    text = re.sub(re.escape(L.chat.format(n="")) + r"(\d+)", r"Chat-\1", text)
    for a, b in ((L.participants, "Parts"), (L.message_count, "Count"), (L.date_range, "Range"),
                 (L.media_omitted, "_(omit)_")):
        text = text.replace(f"- {a}:", f"- {b}:") if a != L.media_omitted else text.replace(a, b)
    return text


def render_chat(people, rows, title="Yük Grubu"):
    text = "".join(f"11/14/26, 9:{i % 60:02d} AM - {people[s]}: {t}\n" for i, (s, t) in enumerate(rows))
    msgs, _ = wa2md.parse(wa2md.decode(text.encode("utf-8")))
    group = wa2md.is_group(msgs, title)
    msgs = wa2md.mark_system_lines(title, msgs, group)
    a = wa2md.Anonymizer(title, msgs, 7, None, group=group)
    out, _, _ = wa2md.render(title, msgs, None, anon=a)
    return out, sorted((r[0], r[1], r[2]) for r in a.review.values()), dict(a.stats)


def setUpModule():
    _pin.pin()


def tearDownModule():
    _pin.unpin()


class PackContract(unittest.TestCase):
    def test_default_pack_passes_the_contract(self):
        p = wa2md_lang.load_pack(wa2md_lang.DEFAULT_PACK)
        self.assertTrue(wa2md_lang.check_pack(p))
        self.assertIs(wa2md.active_pack(), p)

    def test_every_field_is_set(self):
        p = wa2md_lang.load_pack("tr")
        for f in dataclasses.fields(wa2md_lang.LanguagePack):
            self.assertIsNotNone(getattr(p, f.name), f.name)

    def test_unknown_pack_is_rejected(self):
        with self.assertRaises(ValueError):
            wa2md_lang.load_pack("xx")

    def test_broken_pack_is_rejected(self):
        p = wa2md_lang.load_pack("tr")
        with self.assertRaises(Exception):
            wa2md.use_pack(dataclasses.replace(p, system_split="("))
        self.assertIs(wa2md.active_pack(), p)


class LabelInvariance(unittest.TestCase):
    """The first 60 invented interaction-heavy chats of fixtures/etkilesim_main.json, rendered under the Turkish labels and
    under a synthetic label set: identical after replacing the labels; the same review words and counts."""

    def tearDown(self):
        wa2md.use_pack(None)

    def test_synthetic_labels_change_only_the_labels(self):
        with open(os.path.join(HERE, "fixtures", "etkilesim_main.json"), encoding="utf-8") as f:
            chats = json.load(f)["sohbetler"][:60]      # 60 chats: ~10 s (all 300: ~50 s, same result)
        tr = wa2md_lang.load_pack("tr")
        before = [render_chat(c["k"], c["m"]) for c in chats]
        wa2md.use_pack(synthetic(tr))
        after = [render_chat(c["k"], c["m"]) for c in chats]
        masked = 0
        for (md_tr, rev_tr, st_tr), (md_s, rev_s, st_s) in zip(before, after):
            self.assertEqual(substitute(md_tr, tr.labels), md_s)
            self.assertEqual(rev_tr, rev_s)
            self.assertEqual(st_tr, st_s)
            masked += md_s.count("Pers ") + md_s.count("<ph>") + md_s.count("<co>")
        self.assertGreater(masked, 600)


if __name__ == "__main__":
    unittest.main()
