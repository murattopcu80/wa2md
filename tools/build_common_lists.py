#!/usr/bin/env python3
"""Builds the ordinary-word lists adlar/en-common.txt and adlar/tr-common.txt of the language packs (issue #2).

Standard library only; reproducible from the downloaded source files (nothing is fetched by this script):
    python tools/build_common_lists.py --lexemes-en lex_en.csv --corpus pg_dir --given adlar/en-given.txt \\
        adlar/en-given-more.txt adlar/tr-adlar.txt --out adlar

Everything the lists are built from is CC0, public domain or this repository's own work (MIT):
  * Wikidata Lexemes (CC0 1.0), English lemmas with their lexical category (QUERY_LEXEMES below; CSV columns lem,c).
  * Project Gutenberg e-texts in the public domain (the books in the corpus directory, one file per book; the
    Project Gutenberg licence header and footer of each file are cut off). Only the document frequency of lower-case
    words is used (in how many books a word occurs in lower case), so that character names never count.
  * Hand-reviewed word lists in this file (EXTRA_EN, DROP_EN, FUNCTION_EN, TR_WORDS): the project's own work.

en-common.txt (ordinary words of English). Used by the engine for three things: (1) a capitalized unknown word right
after a given name is a surname unless it is an ordinary word ("Emily Always"), (2) the same for a lone word after a
closing phrase ("Thanks, everyone"), (3) a lower-case given name that is an ordinary word of the pack is the word
("120 miles"), also in a chat where several packs are selected. A word is listed when
    (a) it occurs in lower case in at least DOC_SHARE_MIN (30%) of the corpus books and is an English word: a lower-case
        Wikidata Lexeme lemma, or a regular inflection of one (plural, third person, past, -ing, -ly, comparative), or
        a word of FUNCTION_EN (closed-class words: Wikidata lemmas of those categories are incomplete), or a word of
        FORMS_EN (irregular forms and British spellings, reviewed by hand: every frequent word that is none of the
        above has to be put by hand into FORMS_EN or REJECT_EN, the tool stops otherwise), or
    (b) it is in EXTRA_EN: a word below that frequency (the books are 19th and early 20th century) that is common in
        present-day chat text and equals a given name or a name part (hand-reviewed, see the comments there);
and it is not in DROP_EN (frequent in the books for a reason that makes it a poor "ordinary word" test: archaic
forms, and words that are mainly a name part).

tr-common.txt (ordinary words of Turkish) is small on purpose. Its only job: a given name of ANOTHER selected pack
that is an ordinary Turkish word is a word-name ("Ben", "Kim", "Kira"). It lists the entries of TR_WORDS that are
also entries of the given-name dictionaries named with --given (the tool stops if a TR_WORDS entry is in none of
them). TR_WORDS was compiled by reading through those name dictionaries and keeping the tokens that are everyday
Turkish words (pronouns, question and function words, very common nouns and verb forms); it is the project's own
work, not copied from any word list. Wikidata Lexemes cover Turkish only thinly (a few thousand entries), so they
are not the basis of the Turkish list.
"""
import argparse
import csv
import datetime
import os
import re
import unicodedata

QUERY_LEXEMES = ('SELECT DISTINCT ?lem ?c WHERE { ?l dct:language wd:Q1860; wikibase:lemma ?lem; '
                 'wikibase:lexicalCategory ?c }')
PROPER_NOUN = "Q147276"             # lexical category "proper noun": never an ordinary word
DOC_SHARE_MIN = 0.30                # a word must occur in lower case in at least this share of the corpus books
MIN_LETTERS = 2

# closed-class words (pronouns, determiners, prepositions, conjunctions, auxiliaries, particles, greetings) and
# very common chat words; the Wikidata lemma list is thin for these
FUNCTION_EN = set((
    "i me my mine myself you your yours yourself he him his himself she her hers herself it its itself we us our ours "
    "ourselves they them their theirs themselves who whom whose which what that this these those someone somebody "
    "something anyone anybody anything everyone everybody everything nobody nothing none one ones each every either "
    "neither both all any some many much more most few fewer less least several enough other another such own same "
    "a an the and or but nor so yet for if then than though although because since while whereas unless until till "
    "whether as at by in on of off to up out over under into onto upon from with within without about above across "
    "after against along among around before behind below beneath beside besides between beyond despite during down "
    "except inside near outside past per plus round through throughout toward towards via is am are was were be been "
    "being have has had having do does did done doing will would shall should can could may might must ought not no "
    "yes yeah yep nope ok okay hi hey hello bye goodbye thanks thank please sorry cheers hmm oh ah wow ouch well "
    "here there where when why how now then today tomorrow yesterday tonight always never ever often sometimes "
    "already still just only also too very quite rather really maybe perhaps again once twice not mum mom dad mate "
    "pal bro sis").split())

# hand-reviewed additions to the frequency selection (rule (b)). Method: every token of the name dictionaries
# (en-given.txt, the labels of en-given-more.txt, tr-adlar.txt) that is an English word (a lower-case Lexeme lemma or a
# regular inflection of one) but below the frequency bound was read through (about 640 tokens that are not already in
# en-word-names.txt or sozcuk-adlar.txt). Kept: the words that present-day chat text uses in lower case all the time;
# the books (19th and early 20th century) hardly contain them (french, german, irish, muslim, christmas: typed in lower
# case in chat, capitalized in books). Not kept (borderline, decided by hand): aspen, caprice,
# charisma, fang, gala, gore, hank, lore, mace, mars, mills, serif, ado, ailing (rare in chat); august (a month name,
# the pack's calendar words already cover it); and every token whose lower-case use is mainly a name (john, anna, ...)
EXTRA_EN = set("euros rice increase query ants mini hub pastor staples french german irish muslim christmas".split())

# frequent in the books but not an ordinary word for the engine's tests: archaic forms
DROP_EN = set("thou thee thy thine hath doth art ye shalt wilt dost hast wert o'er ere nay aye".split())

# Words that pass the frequency bound but are neither a lemma nor a regular inflection of one: reviewed by hand (the
# tool stops when a new such word appears that is in neither list). Accepted: irregular verb and noun forms and British
# spellings (a Lexeme lemma list has the base forms only). Rejected: abbreviations, fragments and archaic forms.
FORMS_EN = set((
    "arisen arose ate awoke became befallen began begun beheld bitten blew borne bought bred brought caught children "
    "clung crept daresay dealt demeanour drank dreamt drew dwelt eaten fed feet fled flew flung forgiven forgot "
    "foresaw foreseen foretold fought gave geese got grew hid knelt knew lain learnt led lent lustre met mice misled "
    "overcame overtaken overtook parlour pretence ran rang repaid rode sank sat seen shone shown shrank shrunk slept "
    "slid slung smouldering sprang sprung spun stood strewn strode strove sung swam swore swung threw told took trod "
    "trodden undergone undertaken undertook vigour went wept withdrew withheld women wore workmen wrote wrung").split())
REJECT_EN = set("bade bethought bidden et etc forbade hast smote te un".split())

# Turkish ordinary words that are also tokens of the given-name dictionaries (see the module docstring)
TR_WORDS = set((
    "abi ada adam adi adin al alan alma aman ana anne ara aya ben cam cami dan dede elli genis hadi hakim hayat ilan kal "
    "kara kat kaya kim kira kirk lan mal ona oran sabah sal sari sen sira sol sonu yan").split())
# Second pass: the tokens of the given-name dictionaries that also occur in the Turkish word lists of this repository's own
# rules (wa2md_lang/tr.py, wa2md.py) were read through as well (adi adin alma ilan sira genis sonu hadi cami hakim were added).
# Third pass: the Turkish case, possessive and copula suffixes (da de dan den la le ya ye nin in un ... ) that an apostrophe
# splits off a name ("Mehmet'dan") were checked against the given-name dictionaries; the only collision is 'dan' (added).
# Considered and not kept: bil, eder, han, rey, tan (not everyday words by themselves); baba, bin, ton (not an entry of
# the English given-name dictionaries: English ordinary words or hand-removed labels, so the cross-pack rule never asks).
# 'kirk' and 'kira' are the Turkish 'kırk' (forty) and 'kira' (rent) as the engine folds them (ı -> i).


def fold(w):
    w = unicodedata.normalize("NFD", w.lower())
    return unicodedata.normalize("NFC", "".join(c for c in w if not unicodedata.combining(c)))


def read_words(path):
    with open(path, encoding="utf-8") as f:
        return {fold(w) for ln in f if not ln.startswith("#") for w in ln.replace("\t", " ").split()}


def book_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        t = f.read()
    a = re.search(r"\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*\n", t)
    b = re.search(r"\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", t)
    return t[a.end() if a else 0: b.start() if b else len(t)]


def doc_freq(corpus_dir):
    """word -> number of books in which it occurs in lower case; second value: number of books."""
    df, books = {}, 0
    for fn in sorted(os.listdir(corpus_dir)):
        if not fn.endswith(".txt"):
            continue
        books += 1
        seen = set(re.findall(r"(?<![A-Za-z'’])[a-z]{%d,}(?![A-Za-z'’])" % MIN_LETTERS, book_text(os.path.join(corpus_dir, fn))))
        for w in seen:
            df[w] = df.get(w, 0) + 1
    return df, books


def stems(w):
    """Possible lemmas of a regularly inflected English word."""
    out = {w}
    if w.endswith("ies"):
        out.add(w[:-3] + "y")
    if w.endswith("ves"):
        out.update((w[:-3] + "f", w[:-3] + "fe"))
    if w.endswith("es"):
        out.add(w[:-2])
    if w.endswith("s"):
        out.add(w[:-1])
    if w.endswith("ied"):
        out.add(w[:-3] + "y")
    if w.endswith("ed"):
        out.update((w[:-2], w[:-1]))
        if len(w) > 4 and w[-3] == w[-4]:
            out.add(w[:-3])
    if w.endswith("ing"):
        out.update((w[:-3], w[:-3] + "e"))
        if len(w) > 5 and w[-4] == w[-5]:
            out.add(w[:-4])
    if w.endswith("ly"):
        out.add(w[:-2])
        if w.endswith("ily"):
            out.add(w[:-3] + "y")
    if w.endswith("er") or w.endswith("est"):
        base = w[:-2] if w.endswith("er") else w[:-3]
        out.update((base, base + "e"))
        if base.endswith("i"):
            out.add(base[:-1] + "y")
        if len(base) > 2 and base[-1] == base[-2]:
            out.add(base[:-1])
    return out


def lemma_set(path):
    """Lower-case lemmas (letters only) of the Wikidata Lexemes CSV, proper nouns left out."""
    out = set()
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            lem = r["lem"].strip()
            if r["c"].endswith("/" + PROPER_NOUN) or not lem.islower():
                continue
            k = fold(lem)
            if re.fullmatch(r"[a-z]{%d,}" % MIN_LETTERS, k):
                out.add(k)
    return out


def english(args):
    lemmas = lemma_set(args.lexemes_en)
    df, books = doc_freq(args.corpus)
    need = max(1, -(-int(DOC_SHARE_MIN * 1000) * books // 1000))      # ceil(share * books)
    freq = {w for w, n in df.items() if n >= need}
    sel = {w for w in freq if w in FUNCTION_EN or stems(w) & lemmas}
    unreviewed = sorted(freq - sel - FORMS_EN - REJECT_EN)
    if unreviewed:
        raise SystemExit(f"frequent words that are no lemma or regular inflection, to review by hand (FORMS_EN or REJECT_EN): {unreviewed}")
    sel |= FORMS_EN & freq
    words = sorted((sel | EXTRA_EN | {w for w in FUNCTION_EN if re.fullmatch(r"[a-z]{2,}", w)}) - DROP_EN)
    return words, books, need, len(lemmas)


def turkish(args):
    names = set()
    for fn in args.given:
        names |= read_words(fn)
    missing = sorted(w for w in TR_WORDS if w not in names)
    if missing:
        raise SystemExit(f"TR_WORDS entries that are in no --given dictionary: {missing}")
    return sorted(TR_WORDS)


def write(path, title, lines, words):
    today = datetime.date.today().isoformat()
    head = [f"# {title}"] + [f"# {x}" for x in lines] + [f"# Built: {today} by tools/build_common_lists.py; entries: {len(words)}",
                                                         "# Format: one word per line (lower case, accents folded); matching is case- and "
                                                         "accent-insensitive (wa2md._key)."]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(head) + "\n" + "\n".join(words) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexemes-en", required=True, help="CSV (lem,c) of the Wikidata query QUERY_LEXEMES")
    ap.add_argument("--corpus", required=True, help="directory of Project Gutenberg texts (*.txt)")
    ap.add_argument("--given", nargs="+", required=True, help="given-name dictionaries (for the Turkish list)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--retrieved", default="2026-11-20", help="retrieval date of the downloads")
    ap.add_argument("--ids", default="", help="comma-separated Project Gutenberg ebook numbers of the corpus (for the header)")
    args = ap.parse_args()

    en, books, need, nlem = english(args)
    write(os.path.join(args.out, "en-common.txt"), "Ordinary words of the 'en' language pack", [
        "Source: Wikidata Lexemes (CC0 1.0, https://www.wikidata.org/wiki/Wikidata:Licensing), English lemmas, retrieved "
        + args.retrieved + ", query:", " " + QUERY_LEXEMES,
        f"  combined with the lower-case word counts of {books} public-domain books of Project Gutenberg (https://www.gutenberg.org,",
        "  numbers: " + args.ids + "), and a hand-reviewed list of this repository.",
        "Licence: CC0 1.0 / public domain for the sources; this list is compiled for this repository and distributed under",
        " the repository licence (MIT). No share-alike material is used.",
        f"Method: a word is listed when it occurs in lower case in at least {need} of the {books} books and is a lower-case",
        f" Lexeme lemma ({nlem} lemmas) or a regular inflection of one, or is a closed-class word (FUNCTION_EN) or a hand-reviewed irregular form (FORMS_EN in the tool); plus the",
        " hand-reviewed present-day words of EXTRA_EN; minus the archaic forms of DROP_EN (all in tools/build_common_lists.py).",
        "Use: a capitalized word after a given name is no surname when it is listed here, a lone word after a closing phrase is",
        " no name, and with several packs selected a lower-case given name listed here is the word, not the name."], en)
    tr = turkish(args)
    write(os.path.join(args.out, "tr-common.txt"), "Ordinary words of the 'tr' language pack (those that are also given names elsewhere)", [
        "Source: this repository's own hand-compiled list (TR_WORDS in tools/build_common_lists.py), distributed under the",
        " repository licence (MIT). Not copied from any word list; no share-alike material is used.",
        "Method: the given-name dictionaries (en-given.txt, en-given-more.txt, tr-adlar.txt; CC0, Wikidata) were read through and",
        " the tokens that are everyday Turkish words were kept (pronouns, question and function words, very common nouns and",
        " verb forms); also checked: the tokens that these dictionaries share with the Turkish word lists of this repository's",
        " own rules (wa2md_lang/tr.py). Compiled 2026-11-20. Wikidata Lexemes cover Turkish too thinly to be the basis.",
        "Use: with several packs selected, a given name of another pack that is listed here (and is no given name of the",
        " Turkish pack) is a word-name: masked only with context (Ben, Kim, Kira)."], tr)
    print(f"en-common {len(en)} words ({books} books, doc-freq >= {need}); tr-common {len(tr)} words")


if __name__ == "__main__":
    main()
