#!/usr/bin/env python3
"""Builds the English dictionaries adlar/en-given.txt, en-surnames.txt, en-word-names.txt and en-places.txt.

Standard library only; reproducible from the downloaded source files (nothing is fetched by this script):
    python tools/build_en_lists.py --wikidata-uk given_uk.csv --wikidata-us given_us.csv \\
        --census Names_2010Census.csv --lexemes lexemes.csv --out adlar
    python tools/build_en_lists.py --more q_Q79.csv q_Q851.csv ... --out adlar     (only adlar/en-given-more.txt)

Sources (all redistributable under the repository's MIT terms):
  * given names: Wikidata (CC0 1.0). Two CSV downloads from the Wikidata Query Service (columns gLabel,c), one per
    citizenship (UK wd:Q145, US wd:Q30); the query is QUERY_GIVEN below.
  * surnames: US Census Bureau, "Frequently Occurring Surnames from the 2010 Census" (public domain, a work of the
    US federal government), file Names_2010Census.csv from
    https://www2.census.gov/topics/genealogy/2010surnames/names.zip (columns name,rank,count,...).
  * word-names: candidates = given names (English and Turkish dictionaries) that are also lower-case English lemmas
    in Wikidata Lexemes (CC0 1.0; QUERY_LEXEMES below, column lem); the candidates are reviewed by hand: only names
    whose ordinary-word use is common are kept (WORD_NAMES below), the rest stay unambiguous names.
  * more given names (en-given-more.txt): the same Wikidata query (CC0 1.0) for citizens of countries whose names
    are common among English speakers but rare in the UK/US query (MORE_COUNTRIES below), one CSV per country; minus
    the names already in en-given.txt, the ordinary English words of adlar/en-common.txt (built from Wikidata Lexemes
    and public-domain books, see tools/build_common_lists.py) and the hand-reviewed English words in NOT_NAMES_MORE.
  * places: this repository's own hand-compiled list of English-speaking countries' regions and large cities
    (PLACES below), distributed under the repository licence.
"""
import argparse
import csv
import datetime
import os
import re
import unicodedata

QUERY_GIVEN = ('SELECT ?gLabel (COUNT(?p) AS ?c) WHERE { ?p wdt:P27 wd:<COUNTRY>; wdt:P735 ?g. '
               '?g rdfs:label ?gLabel. FILTER(LANG(?gLabel)="en") } GROUP BY ?gLabel HAVING (COUNT(?p) >= 5)')
QUERY_LEXEMES = ('SELECT DISTINCT ?lem WHERE { ?l dct:language wd:Q1860; wikibase:lemma ?lem; '
                 'wikibase:lexicalCategory ?c. VALUES ?c { wd:Q1084 wd:Q24905 wd:Q34698 wd:Q380057 } }')
CENSUS_MIN = 5000        # surnames held by at least this many people in the 2010 Census

# never names, although some appear as given-name labels: titles, function words, calendar words (the pack's
# calendar_words already protects month and day names)
NOT_NAMES = set((
    "mr mrs ms miss sir dame lord lady madam dr doctor prof the and you to is it of in that for are with be have this "
    "not what can do so if or an all get there about would know when how am as at by he she we us me my no yes "
    "january february march april may june july august september october november december "
    "monday tuesday wednesday thursday friday saturday sunday "
    # function words (prepositions, conjunctions, pronouns...; Wikidata lexemes above cover only content words)
    "about above across after against along among another any around before behind below beside besides between "
    "beyond both but could did does down during each either enough every few from had has her here hers him his "
    "inside into its just less like many might more most much must near neither nobody none nor nothing now off on "
    "once one only onto other our out outside over own past per plus round several shall should since some such "
    "than then these they those though through till too toward towards under unless until upon very via was were "
    "whatever where whether which while who whom whose why within without yet your ok okay hi hey hello bye thanks "
    "please sorry").split())
# places (PLACES below) that are also given names are dropped from the given names, except these, which are common
# given names too (they stay in en-given.txt and are therefore ambiguous places: masked like names)
PLACE_NAMES_KEPT = {"austin", "charlotte", "georgia", "sydney", "victoria", "virginia"}

# hand-reviewed: given names whose ordinary English use is common (masked only with context, like sozcuk-adlar.txt)
WORD_NAMES = (
    "abbey ace ad almond alpha amber angel ant arch archer art ash aura aurora autumn babe bacon baker barb barber "
    "bard baron basil bass beach bear beau bell belle berry bill bird birdie bishop black bland blossom blue bob "
    "bond booth branch brandy brick brook brown buck bud buddy bunny burr buster butler buzz cam camp candy cannon "
    "canyon carol carpenter case cash cat chamberlain champion chance charity chase cherry chic chick chip chubby "
    "chuck clay cliff colt comfort con constant cook cookie cooper coral cord cotton coy crane creed crystal curly "
    "daisy dale dash dawn day deacon dean delight destiny diamond dick doc dodge dolly don dove drake duke dusty "
    "earl early earnest ebony echo eddy elder else eve even faith fawn fern field finch fish fisher flint flip flora "
    "ford forest fortune fox frank friend fuller gabby gale gamble garland gay gene genesis gentry gill ginger glen "
    "gold grace grant gray green grey griffin grove guy hale hall ham happy hardy harmony hart haven hay hazard "
    "hazel heath heather herb hill holly homer honey honor hope hunt hunter iris ivory ivy jack jade jasmine jay "
    "jazz jean jewel job joy junior justice king kit kitty knight lake lance lane laurel law lee lemon liberty lily "
    "lot lotus love loyal lucky major mark marsh mason mat max mead melody mercy merry miller miner minor misty "
    "monk moody moon moss nana newt nick noble north nova ocean odd olive opal orange pace page park pat patience "
    "patty pearl peer peg penny pepper pip pleasant pope porter potter power powers precious price prince prosper "
    "queen rain rainy ram ransom raven ray read red reed rich rip river rob robin rocky rod roe roger rose rosemary "
    "rowan royal ruby rue rush rust rusty sage sailor saint salmon sandy savage scarlet sharp shepherd sherry skip "
    "sky slim sly smith snow sparks spider spike squire stark sterling stone storm stormy story strong sue sugar "
    "summer sunny sunshine swan tad tanner tawny teal tell temple tiger tiny tone toy trace tray treat trinity true "
    "turner unique urban usher valentine van vane victory viola violet wade walker ward ware warren welcome west "
    "western whit will willing willow win winter wise wolf wood woods woody worth wren young").split()
# Turkish given names (adlar/tr-adlar.txt) that are common English words: ambiguous when the English pack is active
WORD_NAMES_TR = ("bilge can deli elfin hare mete mine nadir nail nil okay oral said server sine tamer tan tuba "
                 "tuna").split()

# countries of the en-given-more.txt query (Wikidata ids): Arabic, South Asian, Spanish, Chinese, Nigerian, Polish names
MORE_COUNTRIES = {
    "Q79": "Egypt", "Q851": "Saudi Arabia", "Q1028": "Morocco", "Q796": "Iraq", "Q810": "Jordan", "Q668": "India",
    "Q843": "Pakistan", "Q902": "Bangladesh", "Q29": "Spain", "Q96": "Mexico", "Q739": "Colombia", "Q414": "Argentina",
    "Q148": "People's Republic of China", "Q865": "Taiwan", "Q1033": "Nigeria", "Q36": "Poland"}
# hand-reviewed: name labels of those countries that are English words, abbreviations, brands, places or parts of a
# place name (they would be masked as names in ordinary English text)
NOT_NAMES_MORE = set((
    "abba ado africa ailing albino amador argentina azul baba bao bello bimbo bin bose camino castor chi cristo danish dev dong fang gala gui "
    "hind hong iban islam mar min mini nike nil pep pero peru ping pol prem primo ramadan roc rut salud sultan tao ting ton "
    "tong ventura yin").split())

# hand-reviewed: frequent spellings that no Wikidata label of the query carries (the name items use other spellings)
GIVEN_MORE_HAND = "Mohammed Muhammed Mohamad Mohamud Mohammod".split()

PLACES = {      # comma-separated names
    "region": (
        "Alabama, Alaska, Arizona, Arkansas, California, Colorado, Connecticut, Delaware, Florida, Georgia, Hawaii, "
        "Idaho, Illinois, Indiana, Iowa, Kansas, Kentucky, Louisiana, Maine, Maryland, Massachusetts, Michigan, "
        "Minnesota, Mississippi, Missouri, Montana, Nebraska, Nevada, New Hampshire, New Jersey, New Mexico, New York, "
        "North Carolina, North Dakota, Ohio, Oklahoma, Oregon, Pennsylvania, Rhode Island, South Carolina, "
        "South Dakota, Tennessee, Texas, Utah, Vermont, Virginia, Washington, West Virginia, Wisconsin, Wyoming, "
        "England, Scotland, Wales, Northern Ireland, Ireland, Alberta, British Columbia, Manitoba, New Brunswick, "
        "Newfoundland, Nova Scotia, Ontario, Prince Edward Island, Quebec, Saskatchewan, New South Wales, Queensland, "
        "South Australia, Tasmania, Victoria, Western Australia, United States, United Kingdom, Canada, Australia, "
        "New Zealand, America, Britain, Mexico, India, Pakistan, Nigeria, South Africa, Germany, France, Spain, Italy, "
        "Poland, Netherlands, Belgium, Portugal, Greece, Turkey, China, Japan, Brazil, Kenya, Ghana, Jamaica, "
        "Philippines"),
    "locality": (
        "London, Birmingham, Manchester, Liverpool, Leeds, Sheffield, Bristol, Newcastle, Nottingham, Leicester, "
        "Coventry, Bradford, Glasgow, Edinburgh, Aberdeen, Dundee, Cardiff, Swansea, Belfast, Dublin, Cork, Galway, "
        "Oxford, Cambridge, Brighton, Southampton, Portsmouth, Plymouth, Reading, Norwich, Milton Keynes, Bournemouth, "
        "Hull, Derby, Wolverhampton, Sunderland, Exeter, York, Bath, Chicago, Houston, Phoenix, Philadelphia, "
        "San Antonio, San Diego, Dallas, San Jose, Jacksonville, Columbus, Indianapolis, San Francisco, Seattle, "
        "Denver, Nashville, Boston, El Paso, Detroit, Memphis, Portland, Las Vegas, Louisville, Baltimore, Milwaukee, "
        "Albuquerque, Tucson, Fresno, Sacramento, Atlanta, Miami, Omaha, Raleigh, Minneapolis, Tulsa, Cleveland, "
        "Oakland, Tampa, New Orleans, Pittsburgh, Cincinnati, St. Louis, Kansas City, Toronto, Montreal, Vancouver, "
        "Calgary, Edmonton, Ottawa, Winnipeg, Halifax, Sydney, Melbourne, Brisbane, Perth, Adelaide, Canberra, Hobart, "
        "Auckland, Wellington, Christchurch, Los Angeles, Salt Lake City, Fort Worth, Charlotte, Austin"),
}


def header(title, lines, n):
    today = datetime.date.today().isoformat()
    out = [f"# {title}"] + [f"# {x}" for x in lines] + [f"# Built: {today} by tools/build_en_lists.py; entries: {n}",
                                                         "# Format: one entry per line (NFC); matching is case- and "
                                                         "accent-insensitive (wa2md._key)."]
    return "\n".join(out) + "\n"


def write(path, head, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(head)
        f.write("\n".join(rows) + "\n")


def main():
    ap = argparse.ArgumentParser()
    for a in ("wikidata-uk", "wikidata-us", "census", "lexemes"):
        ap.add_argument("--" + a)
    ap.add_argument("--out", required=True)
    ap.add_argument("--more", nargs="+", help="per-country CSVs q_<Wikidata id>.csv: build only en-given-more.txt")
    ap.add_argument("--retrieved", default="2026-11-20", help="retrieval date of the downloads")
    args = ap.parse_args()
    if args.more:
        return build_more(args)
    if not all((args.wikidata_uk, args.wikidata_us, args.census, args.lexemes)):
        ap.error("--wikidata-uk, --wikidata-us, --census and --lexemes are required (or --more)")

    given = {}
    for fn in (args.wikidata_uk, args.wikidata_us):
        with open(fn, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                g = r["gLabel"].strip()
                if re.fullmatch(r"[A-Z][a-z]+(?:['’-][A-Z]?[a-z]+)?", g) and g.lower() not in NOT_NAMES:
                    given[g] = given.get(g, 0) + int(r["c"])
    place_words = {n.strip().lower() for text in PLACES.values() for n in text.split(",")}
    dropped = sorted(g for g in given if g.lower() in place_words and g.lower() not in PLACE_NAMES_KEPT)
    for g in dropped:
        del given[g]
    given_rows = sorted(given, key=str.lower)

    surnames = []
    with open(args.census, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["count"].isdigit() and int(r["count"]) >= CENSUS_MIN and r["name"].isalpha():
                s = r["name"].capitalize()
                if s.lower() not in NOT_NAMES:
                    surnames.append(s)
    surname_rows = sorted(set(surnames), key=str.lower)

    with open(args.lexemes, encoding="utf-8") as f:
        lemmas = {r["lem"].strip() for r in csv.DictReader(f)}
    lower = {w for w in lemmas if w.islower()}
    keys = {g.lower() for g in given}
    missing = [w for w in WORD_NAMES if w not in keys or w not in lower]
    if missing:
        raise SystemExit(f"word-names not in the given names or not lower-case lemmas: {missing}")
    word_rows = sorted(set(WORD_NAMES)) + ["# Turkish given names that are common English words"] + sorted(WORD_NAMES_TR)

    src_wd = ["Source: Wikidata (https://www.wikidata.org), Wikidata Query Service (https://query.wikidata.org/sparql)",
              "Licence: CC0 1.0 (https://www.wikidata.org/wiki/Wikidata:Licensing)", f"Retrieved: {args.retrieved}"]
    write(os.path.join(args.out, "en-given.txt"), header("English given names", src_wd + [
        "Query (once per citizenship: UK wd:Q145, US wd:Q30; union of the labels):", " " + QUERY_GIVEN,
        "Kept: single words (optionally one hyphen or apostrophe part), capitalized; removed: titles, function words,",
        " month and day names (list NOT_NAMES in tools/build_en_lists.py) and names of places in en-places.txt",
        " except " + ", ".join(sorted(x.capitalize() for x in PLACE_NAMES_KEPT)) + f" ({len(dropped)} removed:",
        " " + ", ".join(dropped) + ").",
        "Names that are also common English words are listed again in en-word-names.txt (masked only with context).",
        "Coverage is biased toward names of people with a Wikidata entry in the UK and the US."], len(given_rows)),
        given_rows)
    write(os.path.join(args.out, "en-surnames.txt"), header("English surnames (US)", [
        "Source: US Census Bureau, Frequently Occurring Surnames from the 2010 Census,",
        " https://www2.census.gov/topics/genealogy/2010surnames/names.zip (file Names_2010Census.csv)",
        "Licence: public domain (work of the US federal government, 17 U.S.C. 105)", f"Retrieved: {args.retrieved}",
        f"Kept: surnames with at least {CENSUS_MIN} bearers (count column), letters only, capitalized; minus NOT_NAMES.",
        "A surname alone is weak evidence: the engine masks it next to a given name, a phone or a contact word."],
        len(surname_rows)), surname_rows)
    write(os.path.join(args.out, "en-word-names.txt"), header("English names that are also ordinary words", [
        "Lower case or at the start of a sentence these words are NOT masked (counted as suspect remaining and written",
        " to the review file); with context they are: a capital in mid-sentence, a title (Mr. Mark), an apostrophe",
        " suffix (Rose's), a capitalized surname after it (Mark Smith) or a known name next to it.",
        "Candidates: given names (en-given.txt, tr-adlar.txt) that are lower-case lemmas of English nouns, verbs,",
        " adjectives or adverbs in Wikidata Lexemes (CC0 1.0), query:", " " + QUERY_LEXEMES,
        f" retrieved {args.retrieved}; then reviewed by hand (kept: common ordinary use). Compiled for this repository,",
        " distributed under the repository licence."], len(word_rows) - 1), word_rows)
    place_rows = sorted({f"{k}\t{n.strip()}" for k, text in PLACES.items() for n in text.split(",")},
                        key=lambda r: (r.split("\t")[0], r.lower()))
    write(os.path.join(args.out, "en-places.txt"), header("Places: regions and large cities of English-speaking "
                                                          "countries (and countries)", [
        "Source: this repository's own hand-compiled list (public geographic names), distributed under the repository",
        " licence. Kinds: region (countries, states, provinces: listing vocabulary) | locality (large cities).",
        "A place that is also in a name dictionary (Victoria, Charlotte, Austin, Georgia) stays ambiguous: it does not",
        " enter the place rules."], len(place_rows)), place_rows)
    print(f"given {len(given_rows)}, surnames {len(surname_rows)}, word-names {len(word_rows) - 1}, "
          f"places {len(place_rows)}")


def _fold(w):
    w = unicodedata.normalize("NFD", w.lower())
    return "".join(c for c in w if not unicodedata.combining(c))


def _list_words(path):
    with open(path, encoding="utf-8") as f:
        return {_fold(w) for ln in f if not ln.startswith("#") for w in ln.split()}


def build_more(args):
    """adlar/en-given-more.txt from the per-country CSVs (see the module docstring)."""
    known = _list_words(os.path.join(args.out, "en-given.txt"))
    common = _list_words(os.path.join(args.out, "en-common.txt"))
    place_words = {_fold(n.strip()) for text in PLACES.values() for n in text.split(",")}
    names, used = {}, []
    for fn in args.more:
        cid = re.search(r"(Q\d+)", os.path.basename(fn)).group(1)
        used.append(f"{MORE_COUNTRIES[cid]} wd:{cid}")
        with open(fn, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                g = unicodedata.normalize("NFC", r["gLabel"].strip())
                k = _fold(g)
                if (len(g) < 3 or not g[:1].isupper() or not re.fullmatch(r"[^\W\d_]+(?:['’-][^\W\d_]+)?", g)
                        or k in known or k in common or k in NOT_NAMES or k in NOT_NAMES_MORE or k in place_words):
                    continue
                names.setdefault(k, g)
    for g in GIVEN_MORE_HAND:
        if _fold(g) not in known:
            names.setdefault(_fold(g), g)
    rows = sorted(names.values(), key=_fold)
    write(os.path.join(args.out, "en-given-more.txt"), header("More given names (common among English speakers)", [
        "Source: Wikidata (https://www.wikidata.org), QLever Wikidata endpoint (https://qlever.dev/api/wikidata)",
        "Licence: CC0 1.0 (https://www.wikidata.org/wiki/Wikidata:Licensing)", f"Retrieved: {args.retrieved}",
        "Query (once per citizenship; union of the labels):", " " + QUERY_GIVEN,
        "Citizenships: " + ", ".join(used) + ".",
        "Removed: names already in en-given.txt, ordinary English words (en-common.txt, NOT_NAMES, NOT_NAMES_MORE in",
        " tools/build_en_lists.py), place names of en-places.txt; kept: single words (one hyphen or apostrophe part),",
        " capitalized, at least 3 letters. Added by hand (spellings no label carries): " + ", ".join(GIVEN_MORE_HAND) + "."],
        len(rows)), rows)
    print(f"more given names {len(rows)}")


if __name__ == "__main__":
    main()
