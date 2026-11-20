"""Language packs for wa2md: everything the engine needs that depends on a language.

A pack is one module in this package (``wa2md_lang/<code>.py``) that exposes ``PACK = LanguagePack(...)``. The engine
(``wa2md.py``) never holds a word list, a language-specific pattern or an output label itself: it reads them from the
active pack (``wa2md.use_pack``) and compiles its patterns from them, once per pack. See ``docs/language-packs.md``.

Conventions used by the field comments below:
  * "words": a sequence of plain words as written (any case); the engine folds them with the pack's ``fold_*`` rules.
  * "key form": already folded (lower case, Turkish letters mapped as ``fold_i``/``fold_pairs`` do) - matched against
    folded words, so a regex in key form never needs upper-case or accented alternatives.
  * "regex": Python ``re`` source text (no flags inside unless stated); the engine adds anchors and flags.
Standard library only.
"""
import dataclasses
import importlib
import re
from typing import Callable, Mapping, Sequence

DEFAULT_PACK = "tr"      # the pack wa2md.py loads at import, before any selection (tests compare against it)
PACKS = ("tr", "en")     # packs shipped in this package; merge order of a pack set (Turkish first: byte identity)
NEVER = r"(?!)"          # regex that never matches: a pack with nothing to say for a regex field


@dataclasses.dataclass(frozen=True)
class Labels:
    """Every string the engine writes into the Markdown output, the attachment list and the review file."""
    chat: str                       # chat / folder / file label, "{n}" = position in the run ("Sohbet-{n}")
    chat_fallback: str              # folder name when a chat name sanitizes to nothing
    person_word: str                # person label = person_word + person_sep + number ("Kişi 3")
    person_sep: str
    unknown_mark: str               # neutral label = person_word + person_sep + unknown_mark ("Kişi ?")
    masks: Mapping[str, str]        # kind -> mask text; kinds: phone company path email user password code iban
    #                                 national_id plate
    media: str                      # renamed media file, "{n}" and "{ext}" ("medya-{n}{ext}")
    participants: str               # header lines of a chat file
    message_count: str
    date_range: str
    media_omitted: str              # note lines (Markdown, already with emphasis marks)
    file_missing: str               # "{name}"
    attachment_not_copied: str      # "{name}", "{kind}"
    forwarded: str                  # WhatsApp Web path: note text of a forwarded message
    deleted: str                    # WhatsApp Web path: note text of a deleted message
    download_failed: str            # WhatsApp Web path: "{kind}", "{label}"
    own_name: str                   # WhatsApp Web path: sender name of outgoing messages
    web_kinds: Mapping[str, str]    # WhatsApp Web media kind id -> display (image gif video audio document)
    kinds: Mapping[str, str]        # attachment kind id -> display (image video audio contact pdf office archive other)
    manifest_file: str              # attachment list file name and content
    manifest_head: Sequence[str]
    status_copied: str
    status_no_media: str
    status_missing: str
    status_not_copied: str
    review_suffix: str              # review file name = <chat label> + review_suffix

    def person(self, n):
        return f"{self.person_word}{self.person_sep}{n}"

    @property
    def person_unknown(self):
        return f"{self.person_word}{self.person_sep}{self.unknown_mark}"


@dataclasses.dataclass(frozen=True)
class LanguagePack:
    code: str
    name: str
    labels: Labels

    # ---- automatic selection (wa2md.detect_packs): which chats this pack is for
    stopwords: frozenset            # lower-case frequent function words of the language
    detect_chars: str               # letters that only this language uses (a word with one counts as a hit)

    # ---- letters: folding (case- and accent-insensitive keys) and the per-letter classes of name patterns
    fold_i: str                     # letters that all fold to "i" (Turkish i/I/ı/İ); upper-case ones start a capital
    fold_pairs: Mapping[str, str]   # base letter -> accented variants that fold to it ({"c": "çÇ", ...})

    # ---- export locale (the phone export's own words)
    ampm: str                       # regex: AM/PM markers after the time
    pm: str                         # regex matched at the start of the lower-cased marker: afternoon
    attach_android: str             # regex: "(file attached)" words
    attach_ios: str                 # regex: "<attached: ...>" word
    omitted: str                    # regex: "<Media omitted>" words
    strip_name: Sequence[str]       # regexes removed from an export file name to get the chat name
    system_patterns: Sequence[str]  # regexes (re.I) of system lines; groups s (subject), o (objects), same (number)
    subject_change: str             # regex (re.I): the line changes the group subject (quoted text = chat name)
    system_split: str               # regex: separator between several people of one system line
    system_not_person: frozenset    # lower-case words that are not people in a system line (you, siz...)
    system_bad: str                 # regex (re.I): a system-line "person" containing this is not a person
    system_notice: str              # regex (re.I): person-less notices (encryption, security code...)
    group_event: str                # regex (re.I): a sender-less line with this proves a group chat
    group_only_patterns: Sequence[str]  # regexes (re.I) of whole lines that only occur in groups
    group_weak: str                 # regex (re.I): the verbs of "X left / X joined" (name-shaped X) in a known group
    event_words: Sequence[str]      # lower-case substrings; a line without any of them is no event (pre-filter)
    self_refs: frozenset            # key form: "you" words that stand in the person slot of an event line
    name_suffix_strip: str          # regex: apostrophe suffix removed from a system-line person ("Ali'yi")
    web_system_skip: str            # regex (re.I): WhatsApp Web system rows that are dropped
    web_weekdays: Sequence[str]     # folded weekday names, Monday first (repeat per language: index % 7)
    web_today: frozenset
    web_yesterday: frozenset

    # ---- inflection: closed suffix list that may follow a name without an apostrophe (empty = none)
    name_suffixes: Sequence[Sequence[str]]   # ordered optional groups (diminutive, plural, possessive, case)

    # ---- trade names and business domains
    sector_words: Sequence[str]     # words of the sector (strong unless listed below)
    sector_generic: frozenset       # short/general sector words: not searched in domains
    sector_weak_extra: frozenset    # further weak words (weak = need a listing marker)
    sector_suffixes: Sequence[str]  # suffixes a sector word may take ("Nakliyattan")
    web_affixes: frozenset          # key form: what may remain of a domain label after removing sector words
    web_prefixes: frozenset         # host prefixes that are not the distinctive label (www, m, ...)
    web_noncommercial: frozenset    # second-level labels under a country TLD that are not commercial
    web_tld: str                    # regex: commercial TLDs of the business-domain rule
    web_tld_quick: str              # regex: pre-filter of the same TLDs
    legal_words: Sequence[str]      # legal-form and company-service words of a trade-name chain
    legal_strong: Sequence[str]     # chain words that are a trade-name marker on their own
    legal_form: Sequence[str]       # legal forms (no second marker needed)
    legal_san: Sequence[str]        # two word groups that together form a legal form ("San." + "Tic.")
    legal_tic: Sequence[str]
    legal_pair: Sequence[str]       # words that together form a legal form ("Limited" + "Şirketi")
    legal_glued: str                # regex: legal form written as one token ("Ltd.Şti.")
    legal_special: str              # regex: abbreviated legal form with letters outside \w boundaries ("A.Ş.")
    legal_special_chars: str        # characters of legal_special used as a quick pre-filter
    kin: Sequence[str]              # kinship words / conjunctions inside a trade name ("ve", "&", "Kardeşler")
    kin_join: Sequence[str]         # the conjunctions among kin (not a family word)
    firm_func: Sequence[str]        # function words: never the distinctive part of a trade name
    firm_stop: Sequence[str]        # generic qualifiers: not distinctive (with firm_func)
    hon_base: Sequence[str]         # bare honorifics that may be a trade name ("ABLA NAKLİYAT")
    hon_singular: str               # regex, key form: honorific + singular possessive ("Dayım")
    address_adjectives: Sequence[str]   # address adjectives ("Sayın", "Değerli")

    # ---- names: honorifics, titles, contact context, ordinary words
    calendar_words: Sequence[str]   # month, weekday and season names (never names on their own)
    calendar_names: Sequence[str]   # calendar words that are also given names: a name before a listed surname or
    #                                 after a title ('June Carter', 'Mrs May'), never alone ('in May', 'Autumn rates')
    capitalized_words: Sequence[str]    # words always written capitalized that are no names
    closing_phrases: str            # regex (any case): closing phrases; a lone capitalized word after one on its own line
    #                                 is a signature name ('Cheers, Gav'; NEVER: no such rule)
    honorific_after: str            # regex, key form: honorific after a name, with its suffixes ("bey", "abi")
    honorific_org: str              # regex, key form: honorific whose preceding word is an institution
    honorific_stop: Sequence[str]   # words before an honorific that are no names
    title_before: frozenset         # key form: titles before a name ("sayin", "sn")
    title_not_name_suffix: str      # regex, key form: plural/possessive ending after a title: not a name
    title_stop: Sequence[str]       # words after a title that are no names
    chat_title_stop: Sequence[str]  # words of a group chat title that are no names (possessives, adjectives)
    family_words: Sequence[str]     # family words ("Ailesi"): the capitalized word before is a surname
    surname_suffix: str             # regex, key form: typical surname endings
    landmark_before: str            # regex: a name after this is part of a landmark ("Hz.")
    institution_any: Sequence[str]  # institution words, prefix match, any case ("Üniversitesi")
    institution_cap: Sequence[str]  # institution words, whole word, capitalized chain only ("Caddesi")
    contact_words: Sequence[str]    # contact-channel words ("Tel", "İrtibat", "WhatsApp")
    org_unit: str                   # regex, key form: unit word as last word: not a person ("Birimi")
    filler_words: Sequence[str]     # field-label / filler words of a contact context
    filler_prefixes: Sequence[str]  # words whose inflected forms are fillers too
    ordinary_words: Sequence[str]   # further ordinary words (never names)
    ordinary_suffix: str            # regex, key form: inflection ending of an ordinary word (stem >= 2 letters)
    lower_case_context: bool        # lower case can be a name: a lower-case name that is also an ordinary word is masked
    #                                 next to a known name, and lower-case words join a capitalized trade name before
    #                                 its legal form (off: lower case is the ordinary word)
    contraction_suffixes: frozenset  # endings after an apostrophe that make the word a contraction, not a name with
    #                                 a suffix ('t: "don't", "ain't"; empty for Turkish)
    #                                 (Turkish chats often write names in lower case; in English lower case is the word)

    # ---- listings and routes
    listing_places: Sequence[str]   # informal place names, countries, regions of listings
    listing_words: Sequence[str]    # listing vocabulary (vehicles, units, listing words)
    place_region_kind: str          # kind(s) of the place list that are regions ("|"-separated; join the listing words)
    route_load: Sequence[str]       # words after a place that make it a loading point ("yüklemeli")
    route_from: str                 # regex: ablative suffix after an apostrophe ("'dan")
    route_to: str                   # regex: dative suffix after an apostrophe ("'a")
    route_from_keys: Sequence[str]  # the same suffixes in key form
    route_to_keys: Sequence[str]

    # ---- passwords, codes, units
    secret_keywords: Sequence[str]  # keywords before a password (inflected forms too)
    secret_keywords_exact: Sequence[str]    # keywords before a password (exact, optional plural "s")
    otp_words: Sequence[str]        # one-time-code words (prefix, any inflection)
    otp_extra: str                  # regex: further one-time-code words
    otp_short: str                  # regex, key form: words that allow 4-digit codes nearby
    pin_word: str                   # key form: keyword whose value may be 4 digits
    otp_units: str                  # regex: units after a number that is no code
    units: str                      # regex (case-insensitive): units after a number that is no secret
    secret_stop: Sequence[str]      # words after a keyword that are no password
    secret_link: str                # regex: link word between a keyword and its value ("is": "my PIN is 4321")
    code_context: str               # regex, key form: context of a pairing code (WhatsApp Web, QR)

    # ---- phones and identifiers
    phone_glued_words: Sequence[str]    # contact words a bare mobile number may be glued to ("Tel0500...")
    phone_national: Callable        # f(b) -> list of regex alternatives; b: engine building blocks (see wa2md)
    phone_mobile: Callable          # f(b) -> regex alternatives of the national MOBILE shapes; active with every pack
    #                                 selection (a Turkish mobile in an English chat), so each carries its own guards
    phone_extension: str            # regex: extension suffix that belongs to a phone (" ext. 204"; NEVER: none)
    iban: str                       # regex: IBAN of the country
    national_id: str                # regex: national identity number
    plate: str                      # regex: vehicle plate

    # ---- name dictionaries (files in dictionary_dir next to wa2md.py; '#' lines are comments)
    dictionary_dir: str
    dictionary_files: Mapping[str, object]  # given, surname, ambiguous, common (ordinary words of the language):
    #                                         words; places: "<kind>\t<name>" lines
    #                                         (a file name, or a tuple of names in a merged pack set)


# Fields that describe the phone export itself (its interface language, not the chat's language). A chat exported
# from an English-language phone can be written in Turkish and the reverse, so these always come from EVERY shipped
# pack, whatever pack set is selected for the chat's text (see merge()).
EXPORT_FIELDS = frozenset({
    "ampm", "pm", "attach_android", "attach_ios", "omitted", "strip_name", "system_patterns", "subject_change",
    "system_split", "system_not_person", "system_bad", "system_notice", "group_event", "group_only_patterns",
    "group_weak", "event_words", "self_refs", "name_suffix_strip", "web_system_skip", "web_weekdays", "web_today",
    "web_yesterday"})
_PLAIN = frozenset({"pin_word", "dictionary_dir"})      # plain strings: equal in every pack of a set


def split_alternatives(rx):
    """Top-level alternatives of a regex ('a|(b|c)|[|]' -> ['a', '(b|c)', '[|]'])."""
    out, depth, cls, esc, start = [], 0, -1, False, 0       # cls: index of the open '[' (-1: not in a class)
    for i, ch in enumerate(rx):
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif cls >= 0:
            if ch == "]" and i > cls + 1 and not (i == cls + 2 and rx[cls + 1] == "^"):
                cls = -1
        elif ch == "[":
            cls = i
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "|" and depth == 0:
            out.append(rx[start:i])
            start = i + 1
    out.append(rx[start:])
    return out


def _merge_value(name, values):
    first = values[0]
    if name in ("phone_national", "phone_mobile"):
        fns = list(dict.fromkeys(values))
        return first if len(fns) == 1 else (lambda b: [x for f in fns for x in f(b)])
    if name in _PLAIN:
        if any(v != first for v in values):
            raise ValueError(f"packs disagree on {name}")
        return first
    if name == "legal_special_chars":
        return "".join(dict.fromkeys("".join(values)))
    if isinstance(first, bool):                 # a rule switch: on when any pack of the set needs it
        return any(values)
    if name in ("fold_i", "detect_chars"):
        return "".join(dict.fromkeys("".join(values)))
    if name == "place_region_kind":
        return "|".join(dict.fromkeys(k for v in values for k in v.split("|")))
    if name == "dictionary_files":
        kinds = dict.fromkeys(k for v in values for k in v)
        merged = {}
        for k in kinds:
            files = tuple(dict.fromkeys(f for v in values if k in v for f in ((v[k],) if isinstance(v[k], str) else v[k])))
            merged[k] = files[0] if len(files) == 1 else files
        return merged
    if name == "fold_pairs":
        merged = {}
        for v in values:
            for base, variants in v.items():
                merged[base] = "".join(dict.fromkeys(merged.get(base, "") + variants))
        return merged
    if name == "web_weekdays":                  # whole weeks (index % 7 is the weekday)
        weeks = []
        for v in values:
            for i in range(0, len(v), 7):
                if list(v[i:i + 7]) not in weeks:
                    weeks.append(list(v[i:i + 7]))
        merged = [d for w in weeks for d in w]
        return first if merged == list(first) else merged
    if name == "name_suffixes":                 # ordered optional groups: union group by group
        n = max(len(v) for v in values)
        return tuple(list(dict.fromkeys(x for v in values if i < len(v) for x in v[i])) for i in range(n))
    if isinstance(first, frozenset):
        merged = frozenset().union(*values)
        return first if merged == first else merged
    if isinstance(first, str):                  # regex: union of the top-level alternatives, first pack's text first
        alts = list(dict.fromkeys(a for v in values for a in split_alternatives(v) if a != NEVER))
        if alts == split_alternatives(first):
            return first
        return NEVER if not alts else alts[0] if len(alts) == 1 else "(?:" + "|".join(alts) + ")"
    if isinstance(first, (list, tuple)):
        merged = list(dict.fromkeys(x for v in values for x in v))
        return first if merged == list(first) else type(first)(merged)
    raise TypeError(f"cannot merge field {name}")


def merge(codes, labels=None):
    """The pack set for the chat text packs ``codes`` (shipped order, deduplicated): word lists, sets and patterns are
    united (the first pack's text first), the export fields always over every shipped pack, ``labels`` from the pack
    with that code (default: the first one). A single pack whose export fields already cover the others' and whose
    labels are its own is returned unchanged (same object)."""
    codes = tuple(c for c in PACKS if c in set(codes))
    if not codes:
        raise ValueError("empty pack selection")
    packs = [load_pack(c) for c in codes]
    every = [load_pack(c) for c in PACKS]
    lab = load_pack(labels).labels if labels else packs[0].labels
    changes = {}
    for f in dataclasses.fields(LanguagePack):
        if f.name in ("code", "name", "labels"):
            continue
        src = every if f.name in EXPORT_FIELDS else packs
        value, own = _merge_value(f.name, [getattr(p, f.name) for p in src]), getattr(packs[0], f.name)
        if value is not own and value != own:
            changes[f.name] = value
    if len(packs) > 1:
        changes.update(code="+".join(codes), name=" + ".join(p.name for p in packs))
    if lab is not packs[0].labels:
        changes["labels"] = lab
    if not changes:
        return packs[0]
    merged = dataclasses.replace(packs[0], **changes)
    check_pack(merged)
    return merged


def load_pack(code=DEFAULT_PACK):
    """The pack with this code (``wa2md_lang/<code>.py``); its contract is checked once."""
    if code not in PACKS:
        raise ValueError(f"unknown language pack: {code!r} (available: {', '.join(PACKS)})")
    pack = importlib.import_module(f"{__name__}.{code}").PACK
    check_pack(pack)
    return pack


def check_pack(p):
    """Pack contract: every field present and of the expected shape, every regex compiles, labels well-formed."""
    for f in dataclasses.fields(LanguagePack):
        if getattr(p, f.name, None) is None:
            raise ValueError(f"pack {p.code}: field {f.name} missing")
    rx = [p.ampm, p.pm, p.attach_android, p.attach_ios, p.omitted, *p.strip_name, *p.system_patterns,
          p.subject_change, p.system_split, p.system_bad, p.system_notice, p.group_event, *p.group_only_patterns,
          p.group_weak, p.name_suffix_strip, p.web_system_skip, p.web_tld, p.web_tld_quick, p.legal_glued,
          p.legal_special, p.hon_singular, p.honorific_after, p.honorific_org, p.title_not_name_suffix,
          p.surname_suffix, p.landmark_before, p.org_unit, p.ordinary_suffix, p.route_from, p.route_to, p.otp_extra,
          p.otp_short, p.otp_units, p.units, p.code_context, p.iban, p.national_id, p.plate, p.secret_link, p.phone_extension, p.closing_phrases]
    rx.append(r"^(?P<s>.+?),? (?:" + p.group_weak + r")\.?$")
    for r in rx:
        re.compile(r)
    L = p.labels
    need = {"phone", "company", "path", "email", "user", "password", "code", "iban", "national_id", "plate"}
    if set(L.masks) != need:
        raise ValueError(f"pack {p.code}: label masks must be exactly {sorted(need)}")
    if set(L.kinds) != {"image", "video", "audio", "contact", "pdf", "office", "archive", "other"}:
        raise ValueError(f"pack {p.code}: attachment kinds incomplete")
    if "{n}" not in L.chat or "{n}" not in L.media or "{ext}" not in L.media or not L.person_word:
        raise ValueError(f"pack {p.code}: label templates need {{n}} / {{ext}}")
    if len(p.web_weekdays) % 7:
        raise ValueError(f"pack {p.code}: web_weekdays must be whole weeks")
    return True
