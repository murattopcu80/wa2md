"""English language pack: word lists, patterns and output labels for English chats (issue #2).

The engine's rules are the same for every language; this module only supplies English data. Field meanings:
wa2md_lang.LanguagePack. Dictionaries: adlar/en-*.txt (sources and licences in their headers and in docs/data-sources.md).
"""
from wa2md_lang import NEVER, Labels, LanguagePack

_UNITS = r"USD|GBP|EUR|CAD|AUD|KG|LBS?|OZ|TONS?|TONNES?|FT|KM|MI|MILES?|MPH|HRS?|MINS?|PCS"


# words and links after which a national number written without grouping is a phone ("call me on 07700900123")
_PHONE_WORDS = ("call", "phone", "tel", "tel.", "telephone", "mobile", "mob", "mob.", "cell", "ph", "ph.", "whatsapp",
                "text", "ring", "number", "fax", "contact", "reach")
_PHONE_LINKS = (" ", ": ", ":", " - ", ". ", " on ", " at ", " on: ", " me on ", " me at ", " me ", " us on ", " us at ",
                " us ", " is ", " is: ", " no ", " no. ", " no: ", " #", " me back on ")


def _national_phones(b):
    """UK and US/Canada national phone shapes written without a country code (alternatives of the engine's phone
    pattern; the engine adds '+<country> ...' and '00 <country> ...'). Grouped shapes stand alone; ungrouped digit
    strings (and the space-only US shape, which also fits three plain numbers) only right after a phone word.
    Never inside a word, a link or a decimal, never followed by a further digit group or a unit."""
    D, S = b.DG, r"[ \-\u00a0\u2010-\u2015\u2212]"
    area = lambda n: rf"(?:\(0[1-9]{D}{{{n}}}\){S}?|0[1-9]{D}{{{n}}}{S})"     # '0161 ', '(0161) ', '(020)'
    us_area = rf"(?:1[ \-.]?)?\([2-9]{D}{{2}}\){S}?"
    head = r"(?<![\w/=&?#%@.\-$£€])"
    tail = rf"(?!{S}{D}{{2}})(?![ \t]?(?i:{_UNITS})\b)"
    after = b.after(_PHONE_WORDS, _PHONE_LINKS)
    shapes = [
        rf"{area(3)}{D}{{3}}{S}?{D}{{3}}",                    # UK 07700 900123, 07700 900 123, 01632 960123
        rf"{area(3)}{D}{{5}}",                                # UK 01632 96012 (10 digits)
        rf"{area(2)}{D}{{3}}{S}?{D}{{4}}",                    # UK 0161 496 0123, 0800 123 4567, 0161 4960123
        rf"{area(2)}{D}{{6}}",                                # UK 0800 123456 (10 digits)
        rf"{area(1)}{D}{{4}}{S}?{D}{{4}}",                    # UK 020 7946 0123
        rf"07{D}{{9}}",                                       # UK mobile without grouping
        rf"{us_area}[2-9]{D}{{2}}[ \-.]{D}{{4}}",            # US (202) 555-0147, 1 (202) 555 0147
        rf"(?:1-)?[2-9]{D}{{2}}-[2-9]{D}{{2}}-{D}{{4}}",      # US 202-555-0147, 1-202-555-0147
        rf"(?:1\.)?[2-9]{D}{{2}}\.[2-9]{D}{{2}}\.{D}{{4}}",  # US 202.555.0147
        rf"{after}(?:1 )?[2-9]{D}{{2}} [2-9]{D}{{2}}[ \-]{D}{{4}}",   # after a phone word: 202 555 0147
        rf"{after}(?:1?[2-9]{D}{{2}}[2-9]{D}{{6}}|0[1-9]{D}{{8,9}})",  # after a phone word: 2025550147, 01619460123
    ]
    return [rf"{head}(?:{'|'.join(shapes)}){tail}"]


def _mobile_phones(b):
    """No English shape is masked outside an English selection: a UK mobile (07700 900123) also fits digit strings that
    the Turkish pack has always left as text, and the Turkish pack's output must stay byte-identical. A UK mobile in a
    chat that selects only the Turkish pack is a documented miss (docs/language-support.md, known limits)."""
    return []


LABELS = Labels(
    chat="Chat-{n}",
    chat_fallback="chat",
    person_word="Person",
    person_sep=" ",
    unknown_mark="?",
    masks={"phone": "[phone]", "company": "[company]", "path": "[path]", "email": "[email]", "user": "[user]",
           "password": "[password]", "code": "[code]", "iban": "[iban]", "national_id": "[national-id]",
           "plate": "[plate]"},
    media="media-{n}{ext}",
    participants="Participants",
    message_count="Message count",
    date_range="Date range",
    media_omitted="_(media not included)_",
    file_missing="_(file missing: {name})_",
    attachment_not_copied="_(attachment not copied: {name}, {kind})_",
    forwarded="Forwarded message",
    deleted="This message was deleted",
    download_failed="{kind} could not be downloaded: {label}",
    not_exported="[{kind}: not exported]",
    own_name="Me",
    web_kinds={"image": "photo", "gif": "gif", "video": "video", "audio": "audio", "document": "document"},
    kinds={"image": "image", "video": "video", "audio": "audio", "contact": "contact card", "pdf": "PDF",
           "office": "office document", "archive": "archive", "other": "other"},
    manifest_file="attachments.md",
    manifest_head=("# Attachments", "",
                   "Status of every attachment. **Check every copied file by hand**: the content of images, videos and "
                   "audio (faces, screenshots, voices, names inside documents) is not anonymized.", "",
                   "| File | Kind | Status |", "|---|---|---|"),
    status_copied="copied, check by hand",
    status_no_media="not copied (--no-media)",
    status_missing="missing (not in the export)",
    status_not_copied="not copied (may contain personal data; --copy-documents)",
    review_suffix="-suspect-names.txt",
)

_MONTHS = "january february march april may june july august september october november december"
_DAYS = "monday tuesday wednesday thursday friday saturday sunday"

PACK = LanguagePack(
    code="en",
    name="English",
    labels=LABELS,
    stopwords=frozenset((
        "the and you to is it of in that for are with be have this not what can will was at but your just my me we "
        "they do so if or an all get there about would know when how i i'm it's don't im dont thanks please yes "
        "been has had were did does could should them their our us he she his her him who which from up out then "
        "than here now today tomorrow tonight good great sure see let got going want need think").split()),
    detect_chars="",
    fold_i="iI",
    # accented letters fold to the base letter, so "Zoë Müller" and "zoe muller" are the same name
    fold_pairs={"a": "áàâäãåÁÀÂÄÃÅ", "e": "éèêëÉÈÊË", "i": "íìîïÍÌÎÏ", "o": "óòôõøöÓÒÔÕØÖ", "u": "úùûüÚÙÛÜ",
                "n": "ñÑ", "c": "çÇ"},
    # ---- export locale: English phone interface (the Turkish pack carries the same English strings; the export fields
    # of every shipped pack are always active together, see wa2md_lang.merge)
    ampm=r"[AaPp]\.?\s?[Mm]\.?",
    pm=r"p",
    attach_android=r"file attached",
    attach_ios=r"attached",
    omitted=r"omitted",
    strip_name=[r"^WhatsApp Chat with\s+", r"^WhatsApp Chat\s*-\s*"],
    system_patterns=(
        r"^your security code with (?P<s>.+?) changed\b",
        r"^(?P<s>.+?) changed to (?P<same>\+?\d[\d ()\-]{6,}\d)\b",
        r"^(?P<s>.+?) made (?P<o>.+?) an? admin\b",
        r"^(?P<s>.+?) (?:added|removed) (?P<o>.+?)\.?$",
        r"^(?P<s>.+?) (?:created group|created this group|changed the subject|changed the group|changed this group|"
        r"deleted this group|reset this group|joined using|joined from|joined via|left\b|was added|was removed|"
        r"is now an admin|requested to join|changed their phone number|changed the settings|pinned a message|"
        r"started a (?:video |voice )?call|turned (?:on|off))",
    ),
    subject_change=r"created group|changed the subject|changed the group name|changed this group's name",
    system_split=r",\s*and\s+|,\s*|\s+and\s+",
    system_not_person=frozenset({"you", "your"}),
    system_bad=r"[\"“”:/@]|https?|\b(?:messages?|group|this)\b",
    system_notice=r"end-to-end encrypted|disappearing messages|security code|group description|admin approval|"
                  r"only admins|changed (?:the|this) group|group icon",
    group_event=r"\b(?:added|removed|joined|left|created (?:this )?group|changed the subject|changed (?:the|this) "
                r"group|is now an admin|made .+ admin)\b",
    group_only_patterns=(
        r'^(?P<s>.+?) created (?:group [\"“].*[\"”]|this group)\.?$',
        r"^(?P<s>.+?) (?:added|removed) (?P<o>.+?)\.?$",
        r"^(?P<s>.+?) joined (?:using this group's invite link|using an invite link|from the community|via invite link)",
        r"^(?P<s>.+?) changed (?:the subject|this group's icon|the group description|this group's settings|the group name|"
        r"this group's name|the group icon)\b",
        r"^(?P<s>.+?) (?:is now an admin|made .+ an? admin)\b",
        r"^you(?:'re| are) now an admin\b|^you were added\b",
    ),
    group_weak=r"left|joined|was added|was removed",
    event_words=(
        "added", "removed", "changed", "made", "created", "deleted", "reset", "joined", "left", "was ", "is now", "now an",
        "requested", "pinned", "started", "turned", "security", "you were", "encrypted", "disappearing", "description",
        "admin", "icon"),
    self_refs=frozenset({"you"}),
    name_suffix_strip=NEVER,
    web_system_skip=r"end-to-end encrypt",
    web_weekdays=_DAYS.split(),
    web_today=frozenset({"today"}),
    web_yesterday=frozenset({"yesterday"}),
    # ---- English names take no suffix without an apostrophe ("Harriet's" is handled by the generic apostrophe rule)
    name_suffixes=(),
    # ---- trade names: distinctive capitalized words before a strong sector word or a legal form become [company]
    sector_words=("logistics logistic freight haulage hauliers haulier trucking forwarding forwarders movers removals "
                  "courier couriers transport transportation shipping cargo carriers").split(),
    sector_generic=frozenset("transport transportation shipping cargo carriers".split()),
    sector_weak_extra=frozenset(),
    sector_suffixes=("s", "es"),
    web_affixes=frozenset(set("s es er ers ing online net web app api mail portal panel blog shop store admin support "
                              "group co uk us usa".split()) | {""}),
    web_prefixes=frozenset({"www", "m", "mobile", "en", "web", "uk", "us"}),
    web_noncommercial=frozenset({"org", "gov", "edu", "ac", "nhs", "mil", "sch", "police", "mod", "ltd", "plc"}),
    web_tld=r"\.(?:com|net|biz|info|co|io)(?:\.(?:uk|au|nz))?|\.(?:co|org|ltd|plc)\.uk|\.(?:uk|us|ca|au|nz|ie)",
    web_tld_quick=r"\.(?:com|net|biz|info|co|io|uk|us|ca|au|nz|ie)",
    legal_words=("ltd limited inc incorporated llc llp lp plc corp corporation co company gmbh pty "
                 "services solutions group holdings enterprises industries trading partners associates").split(),
    legal_strong="ltd limited inc incorporated llc llp plc corp corporation gmbh pty".split(),
    legal_form="ltd limited inc llc llp plc corp gmbh pty".split(),
    legal_san=(),
    legal_tic=(),
    legal_pair=("limited", "company"),
    legal_glued=r"(?i:pty\.?ltd\.?|l\.l\.c\.?)",
    legal_special=NEVER,
    legal_special_chars="",
    kin="sons son brothers bros daughters and &".split(),
    kin_join=("and", "&"),
    firm_func=(
        "the a an of for to in on at by with from all every any some our your my his her their this that these those "
        "one two three four five six seven eight nine ten hundred thousand first second new old other same own "
        "yesterday today tomorrow also just still only very more most less").split(),
    firm_stop=(
        "cheap fast reliable trusted local national international express premium professional quality budget best "
        "same next day long distance door domestic commercial residential heavy light general special").split(),
    hon_base=(),
    hon_singular=NEVER,
    address_adjectives="dear".split(),
    # ---- names in context
    calendar_words=(_MONTHS + " " + _DAYS + " spring summer autumn winter").split(),
    calendar_names="april may june august summer autumn winter sunday".split(),
    capitalized_words=("english british american scottish welsh irish canadian australian european african asian "
                       "christmas easter halloween thanksgiving god jesus").split(),
    closing_phrases=(r"cheers|thanks|thank you|thx|ta|many thanks|regards|kind regards|best regards|warm regards|best|"
                     r"best wishes|all the best|love|lots of love|sincerely|yours|yours sincerely|take care|"
                     r"catch you later|see you|see ya|speak soon|talk soon|bye"),
    honorific_after=NEVER,
    honorific_org=NEVER,
    honorific_stop=(),
    title_before=frozenset({"mr", "mrs", "ms", "miss", "mx", "dr", "doctor", "prof", "professor", "sir", "dame", "lord",
                            "lady", "madam", "rev", "revd", "reverend", "fr", "sr", "hon", "capt", "captain", "col",
                            "colonel", "sgt", "sergeant", "lt", "lieutenant", "insp", "inspector", "det", "detective",
                            "pc", "constable", "cllr", "councillor", "councilor", "mayor", "senator", "governor",
                            "pastor", "rabbi", "imam", "nurse", "uncle", "aunt", "auntie", "grandma", "grandpa",
                            "nan", "nana", "coach", "officer", "judge"}),
    title_not_name_suffix=NEVER,
    title_stop=("all everyone everybody team there folks guys sir madam customer customers manager director president "
                "colleagues friends members parents sir/madam or and the a an my our your").split(),
    chat_title_stop="our my your the best happy new old big little family team".split(),
    family_words="family fam".split(),
    surname_suffix=r"..(?:son|sen|ton|ford|field|ley|worth|wood|man)$",
    landmark_before=NEVER,
    institution_any=("university college hospital school academy institute museum library station airport stadium "
                     "cathedral church").split(),
    institution_cap=("street st road rd avenue ave lane boulevard blvd drive square park bridge hall centre center "
                     "tower river lake bay hill mount court place way close crescent terrace").split(),
    contact_words=("contact call phone telephone tel mobile mob cell ph whatsapp wa telegram signal attn "
                   "watsapp whatsap wtsp wapp").split(),
    org_unit=r"(?:department|dept|team|office|desk|centre|center|branch|depot|warehouse|division|services?|support|"
             r"sales|accounts|billing)",
    filler_words=("no number num nr for info information details only please call text office fax ext extension "
                  "direct main hours after before mobile cell business hotline name surname first last other "
                  "alternative alt home work landline").split(),
    filler_prefixes="number phone contact whatsapp".split(),
    ordinary_words=("thanks thank cheers regards best wishes hello hi hey okay yeah yep nope sorry please welcome "
                    "congrats congratulations").split(),
    ordinary_suffix=r"(?:ing|ings|ed|ly|ness|ment|ments|tion|tions|able|ible|ful|less|est|ies)$",
    lower_case_context=False,
    contraction_suffixes=frozenset({"t"}),   # don't, can't, won't, ain't, shan't (never a name + suffix)
    # ---- listings and routes
    listing_places=("usa us uk america britain england scotland wales ireland canada australia europe asia africa "
                    "mexico midwest east west north south coast").split(),
    listing_words=(
        "truck trucks trailer flatbed reefer van vans dry box tanker container lorry load loads freight pallet pallets "
        "ton tons tonne tonnes lb lbs kg ft feet mile miles km rate rates price quote urgent available asap pickup "
        "delivery deliver dispatch broker carrier shipper driver drivers").split(),
    place_region_kind="region",
    route_load=(),
    route_from=NEVER,
    route_to=NEVER,
    route_from_keys=(),
    route_to_keys=(),
    # ---- passwords, codes, units
    secret_keywords=["password", "passcode", "passphrase", "token", "login", "api key", "apikey", "api-key", "api_key",
                     "secret", "credentials"],
    secret_keywords_exact=["passwd", "password", "pass", "pwd", "pw", "pin"],
    otp_words=("code", "verification", "verify", "otp"),
    otp_extra=r"[Oo][Tt][Pp]|2[Ff][Aa]",
    otp_short=r"pin|code|otp|verification",
    pin_word="pin",
    otp_units=r"USD|GBP|EUR|CAD|AUD|\$|£|€|KG|LBS?|TONS?|MILES?|KM|FT",
    units=_UNITS,
    secret_stop=("none", "no", "yes", "nothing", "forgot", "forgotten", "changed", "same", "unknown", "tbd", "is",
                 "was", "the", "and", "for", "new", "old", "reset"),
    secret_link=r"is|was|=|for(?:[ \t]+[^\W\d_]+){1,3}[ \t]*:",     # "password for the portal: X"
    code_context=r"whatsapp|(?<!\w)web(?!\w)|link|pair|qr",
    # ---- phones and identifiers (national shapes and national ids for English-speaking countries: next step)
    phone_glued_words="tel ph mob cell phone whatsapp".split(),
    phone_national=_national_phones,
    phone_mobile=_mobile_phones,
    phone_extension=r"[ \t]*,?[ \t]*(?i:ext\.?|extn\.?|extension)[ \t]*:?[ \t]*\d{1,5}(?!\d)|[ \t]?[xX]\d{1,5}(?!\d)",
    iban=r"(?<![\w])(?:GB|IE)\d{2} ?[A-Z]{4}(?: ?\d{4}){3} ?\d{2}(?!\d)",     # UK and Irish IBAN
    national_id=NEVER,
    plate=NEVER,
    dictionary_dir="adlar",
    dictionary_files={"given": ("en-given.txt", "en-given-more.txt"), "surname": "en-surnames.txt", "ambiguous": "en-word-names.txt",
                      "places": "en-places.txt",
                      "common": "en-common.txt"},
)
