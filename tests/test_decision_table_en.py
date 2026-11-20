"""English decision table (issue #2), built like the Turkish one (test_nakliye_karar_tablosu.py): every row is
(class, participants or None, input messages, expected output lines), run with the English pack and English labels.

All names, companies, numbers and links are invented (phones from fictional/drama ranges). In the expected output
'{P:<name>}' is that participant's label; '{L1}', '{L2}' ... are labels of non-participants (same placeholder, same
label; different placeholders, different labels). A message given as a string is sent by 'Harriet Plimm'; a tuple is
(sender, text); '\\n' inside a message gives several output lines. Rows of class 'M...' run with the Turkish and the
English pack together (a mixed chat), all others with the English pack alone.

Classes: S sender and participants, N dictionary names, T titles before a name, W ordinary words that are also names
(must be preserved), PL places, X prices/dates/times/measures (must be preserved), C contact words and phones, G
signatures, F trade names, L links/e-mails/handles, K passwords/codes/IBAN, Y system lines, M mixed Turkish+English.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import wa2md  # noqa: E402

H, Z = "Harriet Plimm", "Zorbek Tuvaq"
PEOPLE = (H, Z)
TITLE = "Freight Desk"
PHONE = "+44 7700 900123"
ZM = PEOPLE + ("Zoë Müller",)

TR8 = ["merhaba abi nasılsın", "iyiyim sen nasılsın", "akşam gelir misin", "tamam geliyorum", "yarın saat kaçta",
       "bilmiyorum daha sonra yazarım", "evet olur", "sağol abi"]
EN8 = ["good morning, how are you", "I am fine, thanks", "can you come tonight", "yes I will be there",
       "what time is it now", "I don't know, I will text you", "that is good", "thanks for that"]

ROWS = [
    # ---- S: participants (sender names and their parts, any case)
    ("S", None, ["Hi Zorbek, it's Harriet"], ["Hi {P:Zorbek Tuvaq}, it's {P:Harriet Plimm}"]),
    ("S", None, ["tell plimm and tuvaq to wait"], ["tell {P:Harriet Plimm} and {P:Zorbek Tuvaq} to wait"]),
    ("S", None, ["Harriet's van is outside"], ["{P:Harriet Plimm}'s van is outside"]),
    ("S", ZM, ["zoe muller wrote back"], ["{P:Zoë Müller} wrote back"]),
    ("S", ZM, ["ZOE MULLER signed"], ["{P:Zoë Müller} signed"]),
    # ---- N: dictionary names (given names unambiguous in every case; given + surname as one person)
    ("N", None, ["yesterday John called"], ["yesterday {L1} called"]),
    ("N", None, ["John Smith and Mary Johnson met"], ["{L1} and {L2} met"]),
    ("N", None, ["I talked to sarah about it"], ["I talked to {L1} about it"]),
    ("N", None, ["Ask Emily and Oliver"], ["Ask {L1} and {L2}"]),
    ("N", None, ["Did you see Margaret today?"], ["Did you see {L1} today?"]),
    ("N", None, ["Thomas's car is outside"], ["{L1}'s car is outside"]),
    ("N", None, ["Jennifer will bring the keys"], ["{L1} will bring the keys"]),
    ("N", None, ["Daniel"], ["{L1}"]),
    ("N", None, ["John called", ("Zorbek Tuvaq", "did John leave?")], ["{L1} called", "did {L1} leave?"]),
    ("N", None, ["I met Zorvan Quell yesterday"], ["I met Zorvan Quell yesterday"]),   # documented limit: unknown name
    # an unknown capitalized surname after an unambiguous given name; the verb after a given name stays
    ("N", None, ["Bethany Crowle sent it"], ["{L1} sent it"]),
    ("N", None, ["I asked Bethany Crowle about the van"], ["I asked {L1} about the van"]),
    ("N", None, ["yesterday Grace said hi, then Mark called"], ["yesterday {L1} said hi, then {L2} called"]),
    ("N", None, ["Emily Always calls late"], ["{L1} Always calls late"]),          # a common word is no surname
    ("N", None, ["Bethany Called Me About The Truck Today"], ["{L1} Called Me About The Truck Today"]),   # title case
    # the first word and day names do not make a short line title case
    ("N", None, ["The new driver, Bethany Crowle, starts Monday"], ["The new driver, {L1}, starts Monday"]),
    # given names of several origins (en-given-more.txt) and a spelling that was only a surname
    ("N", None, ["Ask Lisa or Mohammed"], ["Ask {L1} or {L2}"]),
    # a lower-case given name that is a common English word is the word; a word-name opening the sentence before a
    # given name is a verb
    ("N", None, ["it's about 120 miles, then Miles called"], ["it's about 120 miles, then {L1} called"]),
    ("N", None, ["Tell Harvey his tyres are ready"], ["Tell {L1} his tyres are ready"]),
    # B2: several full names in one line; names do not make a line title case (a real heading still does)
    ("N", None, ["Michael Thornbury and Laura Vexley came"], ["{L1} and {L2} came"]),
    ("N", None, ["Chidi Okonkwo and Siobhan Murphy agreed"], ["{L1} and {L2} agreed"]),
    ("N", None, ["Sarah Vexley and Tom Okonkwo and Wei Zhang arrived"], ["{L1} and {L2} and {L3} arrived"]),
    ("N", None, ["Emily Rockets Past Target Again"], ["{L1} Rockets Past Target Again"]),
    ("N", None, ["Local Haulier Wins Regional Award For Safety"], ["Local Haulier Wins Regional Award For Safety"]),
    # S6: possessive after a full name, hyphenated and apostrophe surnames, an initial before a listed surname,
    # 'Limited' alone as a legal form, a signature on two lines
    ("N", None, ["Tom Okonkwo's truck is here"], ["{L1}'s truck is here"]),
    ("N", None, ["Mary Smith-Jones will call you"], ["{L1} will call you"]),
    ("N", None, ["Liam O'Brien is the driver"], ["{L1} is the driver"]),
    ("N", None, ["Wei Zhang and Mohammed Al-Rashid arrive at 5"], ["{L1} and {L2} arrive at 5"]),
    ("N", None, ["Mary well-known driver"], ["{L1} well-known driver"]),       # lower-case parts: no surname
    ("N", None, ["J. Smith signed the form"], ["{L1} signed the form"]),
    ("G", None, ["Cheers,\nGav"], ["Cheers,", "{L1}"]),
    ("G", None, ["Best,\nok"], ["Best,", "ok"]),
    ("F", None, ["Quillon Transport Limited sent the POD"], ["[company] Transport Limited sent the POD"]),
    ("F", None, ["The offer is Limited to ten pallets"], ["The offer is Limited to ten pallets"]),
    ("N", None, ["Rahul, Chinedu and Krzysztof are driving; Ximena and Wei too"],
     ["{L1}, {L2} and {L3} are driving; {L4} and {L5} too"]),
    ("N", None, ["the fan is broken, it was a long day, put it in the bin"],
     ["the fan is broken, it was a long day, put it in the bin"]),
    # ---- T: titles before a name (title kept, name masked even when it is in no dictionary)
    ("T", None, ["Please ask Mr. Quilby"], ["Please ask Mr. {L1}"]),
    ("T", None, ["Mrs Brandt and Dr. Okafor are out"], ["Mrs {L1} and Dr. {L2} are out"]),
    ("T", None, ["Prof Ashdown sent the notes"], ["Prof {L1} sent the notes"]),
    ("T", None, ["Ms. Jones will call"], ["Ms. {L1} will call"]),
    ("T", None, ["Uncle Bob is here"], ["Uncle {L1} is here"]),
    ("T", None, ["Hello everyone, Dr. Okafor here"], ["Hello everyone, Dr. {L1} here"]),
    ("T", None, ["Mx Arlow joined us"], ["Mx {L1} joined us"]),
    ("T", None, ["Councillor Abernathy will attend"], ["Councillor {L1} will attend"]),
    ("T", None, ["Cllr. Abernathy and Rev Pickett came, Fr. Donnelly too"], ["Cllr. {L1} and Rev {L2} came, Fr. {L3} too"]),
    ("T", None, ["Nurse Ratchet and Officer Dibble are on shift"], ["Nurse {L1} and Officer {L2} are on shift"]),
    ("T", None, ["the nurse and the officer are on shift"], ["the nurse and the officer are on shift"]),
    ("T", None, ["Dear Sir or Madam, hello"], ["Dear Sir or Madam, hello"]),
    ("T", None, ["Dear all, the meeting moved"], ["Dear all, the meeting moved"]),
    ("T", None, ["Dear customers, we are closed"], ["Dear customers, we are closed"]),
    # ---- W: names that are also ordinary words: lower case and sentence start stay, context masks
    ("W", None, ["please mark it"], ["please mark it"]),
    ("W", None, ["Mark the date on the calendar"], ["Mark the date on the calendar"]),
    ("W", None, ["yesterday Mark called me"], ["yesterday {L1} called me"]),
    ("W", None, ["Rose's phone is dead; the rose bushes are fine"], ["{L1}'s phone is dead; the rose bushes are fine"]),
    ("W", None, ["I will pay the bill tomorrow"], ["I will pay the bill tomorrow"]),
    ("W", None, ["we hope it works"], ["we hope it works"]),
    ("W", None, ["you may go now"], ["you may go now"]),
    ("W", None, ["say grace before dinner"], ["say grace before dinner"]),
    ("W", None, ["the will was read"], ["the will was read"]),
    ("W", None, ["Will you come?"], ["Will you come?"]),
    ("W", None, ["I asked Will about it"], ["I asked {L1} about it"]),
    ("W", None, ["We met Grace at noon"], ["We met {L1} at noon"]),
    ("W", None, ["a hare ran past the violet flowers and the lee side of the ship, jack of all trades"],
     ["a hare ran past the violet flowers and the lee side of the ship, jack of all trades"]),
    ("W", None, ["a frank discussion about the price"], ["a frank discussion about the price"]),
    ("W", None, ["then Frank called"], ["then {L1} called"]),
    ("W", None, ["We sat by the river with Robin"], ["We sat by the river with {L1}"]),
    ("W", None, ["I have faith in you"], ["I have faith in you"]),
    ("W", None, ["the rich get richer"], ["the rich get richer"]),
    ("W", None, ["she has a heart of gold"], ["she has a heart of gold"]),
    ("W", None, ["happy new year to the whole team"], ["happy new year to the whole team"]),
    ("W", None, ["the dawn shift starts early"], ["the dawn shift starts early"]),
    ("W", None, ["the guy at the gate"], ["the guy at the gate"]),
    ("W", None, ["max 20 pallets"], ["max 20 pallets"]),
    ("W", None, ["Mark Smith signed"], ["{L1} signed"]),                          # word-name + surname: masked
    ("W", None, ["Mr. Mark arrived"], ["Mr. {L1} arrived"]),
    # ---- W (calendar): month and day names are never names
    ("W", None, ["the meeting is in May"], ["the meeting is in May"]),
    ("W", None, ["March 3rd works, see you in August"], ["March 3rd works, see you in August"]),
    ("W", None, ["see you on Monday or Friday"], ["see you on Monday or Friday"]),
    # season, month and day words that are given names: names only before a listed surname or after a title
    ("W", None, ["the Autumn rates are higher"], ["the Autumn rates are higher"]),
    ("W", None, ["the Summer schedule starts in June, back in April"], ["the Summer schedule starts in June, back in April"]),
    ("W", None, ["May I ask? On Sunday we rest"], ["May I ask? On Sunday we rest"]),
    ("W", None, ["June Carter called and Summer Holloway sent the file"], ["{L1} called and {L2} sent the file"]),
    ("W", None, ["I spoke to Mrs May about it"], ["I spoke to Mrs {L1} about it"]),
    ("W", None, ["we met April Johnson at the depot in August"], ["we met {L1} at the depot in August"]),
    # contractions: "don't" is not Don + suffix, "ain't" / "shan't" not Ain / Shan (pack field contraction_suffixes)
    ("W", None, ["I don't know, we can't wait"], ["I don't know, we can't wait"]),
    ("W", None, ["Don't forget the pallets"], ["Don't forget the pallets"]),
    ("W", None, ["ain't that right, we shan't wait"], ["ain't that right, we shan't wait"]),
    ("N", None, ["I asked Don, Mark'll be late"], ["I asked {L1}, {L2}'ll be late"]),
    # ---- PL: places (cities as places, countries, states)
    ("PL", None, ["The truck left Chicago for Dallas"], ["The truck left Chicago for Dallas"]),
    ("PL", None, ["Load available Chicago → Dallas, 40ft flatbed"], ["Load available Chicago → Dallas, 40ft flatbed"]),
    ("PL", None, ["We moved to London last year"], ["We moved to London last year"]),
    ("PL", None, ["flying to Boston on Monday"], ["flying to Boston on Monday"]),
    ("PL", None, ["Manchester is rainy"], ["Manchester is rainy"]),
    ("PL", None, ["shipping from Texas to Ohio"], ["shipping from Texas to Ohio"]),
    # ---- X: prices, dates, times, measures, references (must be preserved)
    ("X", None, ["$1,250.50 for 25 tons"], ["$1,250.50 for 25 tons"]),
    ("X", None, ["2026-11-14 at 08:30 PM"], ["2026-11-14 at 08:30 PM"]),
    ("X", None, ["2.5 km away, 60 mph"], ["2.5 km away, 60 mph"]),
    ("X", None, ["ref 1234567890"], ["ref 1234567890"]),
    ("X", None, ["flight BA 2490 lands at 9:41"], ["flight BA 2490 lands at 9:41"]),
    ("X", None, ["£300 per pallet, 12 pallets"], ["£300 per pallet, 12 pallets"]),
    ("X", None, ["order #20261114 shipped"], ["order #20261114 shipped"]),
    ("X", None, ["Meet at 5pm on 12/11/2026"], ["Meet at 5pm on 12/11/2026"]),
    ("X", None, ["It costs 40 USD"], ["It costs 40 USD"]),
    ("X", None, ["Room 214, floor 3"], ["Room 214, floor 3"]),
    # not phones: order/tracking/reference numbers, card- and ID-like numbers, versions, coordinates, plain numbers
    ("X", None, ["ref 0123456789 for the pallet"], ["ref 0123456789 for the pallet"]),
    ("X", None, ["tracking 1Z999AA10123456784"], ["tracking 1Z999AA10123456784"]),
    ("X", None, ["card 4111 1111 1111 1111 expired"], ["card 4111 1111 1111 1111 expired"]),
    ("X", None, ["SSN format 123-45-6789"], ["SSN format 123-45-6789"]),
    ("X", None, ["version 10.4.1234 is out, build 2.14.1033"], ["version 10.4.1234 is out, build 2.14.1033"]),
    ("X", None, ["coordinates 51.5074, -0.1278"], ["coordinates 51.5074, -0.1278"]),
    ("X", None, ["loads 250 300 1500 kg today, 200 300 4000 boxes"], ["loads 250 300 1500 kg today, 200 300 4000 boxes"]),
    ("X", None, ["at 202 555 0147 kg"], ["at 202 555 0147 kg"]),
    ("X", None, ["price £1,250 or 1 250 000"], ["price £1,250 or 1 250 000"]),
    ("X", None, ["the 2026-11-14 date, 14:30 on 12/11/2026, 12.11.2026"], ["the 2026-11-14 date, 14:30 on 12/11/2026, 12.11.2026"]),
    ("X", None, ["https://example.com/u/07700900123 and example.com/202-555-0147"],
     ["https://example.com/u/07700900123 and example.com/202-555-0147"]),
    ("X", None, ["0800 123 4567 1234 is the account"], ["0800 123 4567 1234 is the account"]),
    # ---- C: contact words and phones (international and national shapes)
    ("C", None, [f"Contact: Wendell Quilby {PHONE}"], ["Contact: {L1} [phone]"]),
    ("C", None, [f"Tel: Odalys Fenwick {PHONE}"], ["Tel: {L1} [phone]"]),
    ("C", None, [f"Odalys Fenwick {PHONE}"], ["{L1} [phone]"]),
    ("C", None, [f"{PHONE} Oliver"], ["[phone] {L1}"]),
    ("C", None, [f"WhatsApp {PHONE}"], ["WhatsApp [phone]"]),
    ("C", None, ["Contact us on +1 415 555 0132"], ["Contact us on [phone]"]),
    ("C", None, ["phone number +49 151 2345 6789"], ["phone number [phone]"]),
    ("C", None, ["Mobile: +61 4 1234 5678"], ["Mobile: [phone]"]),
    ("C", None, ["call me at 0049 151 2345 6789"], ["call me at [phone]"]),
    ("C", None, [f"Contact: Wendell Quilby {PHONE}", "Wendell Quilby is late"], ["Contact: {L1} [phone]", "{L1} is late"]),
    # national shapes (UK and US/Canada; reserved example ranges), contact words, extensions
    ("C", None, ["07700 900456 is my new number"], ["[phone] is my new number"]),
    ("C", None, ["my mobile is 07700-900-321"], ["my mobile is [phone]"]),
    ("C", None, ["call 07700900123 tonight"], ["call [phone] tonight"]),
    ("C", None, ["London office 020 7946 0123, freephone 0800 123 4567"], ["London office [phone], freephone [phone]"]),
    ("C", None, ["Leeds (0113) 496 0123 or 0113 496 0124"], ["Leeds [phone] or [phone]"]),
    ("C", None, ["ring (202) 555-0147 or 202-555-0147"], ["ring [phone] or [phone]"]),
    ("C", None, ["202.555.0147 is the desk, 1-202-555-0148 after 5pm"], ["[phone] is the desk, [phone] after 5pm"]),
    ("C", None, ["call me on 2025550147"], ["call me on [phone]"]),
    ("C", None, ["my number is 202 555 0147"], ["my number is [phone]"]),
    ("C", None, ["Tel: (202)555-0149 x204"], ["Tel: [phone]"]),
    ("C", None, ["tel +1-202-555-0143 ext. 204"], ["tel [phone]"]),
    ("C", None, ["+44 (0)7700 900123 or +44 20 7946 0123"], ["[phone] or [phone]"]),
    ("C", None, ["+33 6 12 34 56 78"], ["[phone]"]),
    # a phone in a line with "code": the digit groups belong to the phone, not to a one-time code
    ("C", None, ["+44 7700 900789 for the gate code"], ["[phone] for the gate code"]),
    ("C", None, ["the code is 4821, call 07700 900123"], ["the code is [code], call [phone]"]),
    # ---- G: signatures
    ("G", None, [f"Best regards,\nOliver Brandt\n{PHONE}"], ["Best regards,", "{L1}", "[phone]"]),
    # documented limit (the Turkish rules behave the same): a name in no dictionary alone on the line above a phone
    ("G", None, [f"Best regards,\nOdalys Fenwick\n{PHONE}"], ["Best regards,", "Odalys Fenwick", "[phone]"]),
    ("G", None, ["Thanks\nHarriet"], ["Thanks", "{P:Harriet Plimm}"]),
    ("G", None, ["Cheers,\nJohn Smith"], ["Cheers,", "{L1}"]),
    # a lone capitalized word after a closing phrase is a (nick)name; ordinary closings stay
    ("G", None, ["Cheers, Gav"], ["Cheers, {L1}"]),
    ("G", None, ["Kind regards, Dunstan"], ["Kind regards, {L1}"]),
    ("G", None, ["Catch you later, Fitz"], ["Catch you later, {L1}"]),
    ("G", None, ["Thanks, everyone", "Thanks, Everyone", "Cheers, Mate", "Love, Mum"],
     ["Thanks, everyone", "Thanks, Everyone", "Cheers, Mate", "Love, Mum"]),
    # ---- F: trade names with legal forms and sector words
    ("F", None, ["Acme Logistics Ltd. will ship 25 tons"], ["[company] Logistics Ltd. will ship 25 tons"]),
    ("F", None, ["Quilby Haulage LLC"], ["[company] Haulage LLC"]),
    ("F", None, ["Mercury Transport Inc. is cheap"], ["[company] Transport Inc. is cheap"]),
    ("F", None, ["Fenwick Removals Ltd"], ["[company] Removals Ltd"]),
    ("F", None, ["Ordway Freight called"], ["[company] Freight called"]),
    ("F", None, ["HTTP Transport settings"], ["HTTP Transport settings"]),
    ("F", None, ["The Electric Company called"], ["The Electric Company called"]),
    ("F", None, ["fast delivery please"], ["fast delivery please"]),
    # ordinary lower-case words before a legal form stay
    ("F", None, ["we got the contract with Redwood Holdings Inc."], ["we got the contract with [company] Holdings Inc."]),
    ("F", None, ["the deal with Redwood Holdings Inc. and Blue Fern Trading Ltd is done"],
     ["the deal with [company] Holdings Inc. and [company] Trading Ltd is done"]),
    # ---- L: links, e-mails, handles
    ("L", None, ["www.fenwicklogistics.com/rates"], ["www.[company].com/[path]"]),
    ("L", None, ["https://github.com/example/project"], ["https://github.com/example/project"]),
    ("L", None, ["mail me at odalys.fenwick@example.com"], ["mail me at [email]"]),
    ("L", None, ["@harriet.plimm texted me"], ["[user] texted me"]),
    # ---- K: passwords, one-time codes, IBAN
    ("K", None, ["password: Hunter2Plimm!"], ["password: [password]"]),
    ("K", None, ["my PIN is 4321"], ["my PIN is [password]"]),
    ("K", None, ["your verification code is 482913"], ["your verification code is [code]"]),
    ("K", None, ["OTP 112233"], ["OTP [code]"]),
    ("K", None, ["pwd: s3cr3t!x"], ["pwd: [password]"]),
    ("K", None, ["the password is the same"], ["the password is the same"]),
    ("K", None, ["password for the portal: Wren!2026"], ["password for the portal: [password]"]),
    ("K", None, ["code red, everyone out"], ["code red, everyone out"]),
    ("K", None, ["IBAN GB82 WEST 1234 5698 7654 32"], ["IBAN [iban]"]),
    # ---- Y: system lines (sender-less lines of a group export)
    ("Y", None, [(None, "Harriet Plimm added Odalys Fenwick"), "Odalys Fenwick says hi"],
     ["09:02 – {P:Harriet Plimm} added {P:Odalys Fenwick}", "{P:Odalys Fenwick} says hi"]),
    ("Y", None, [(None, "Zorbek Tuvaq left")], ["09:02 – {P:Zorbek Tuvaq} left"]),
    # ---- M: mixed chat, Turkish and English packs together
    ("M", None, ["Merhaba Deniz abi, Mr. Quilby aradı"], ["Merhaba {L1} abi, Mr. {L2} aradı"]),
    ("M", None, ["Ayşe called yesterday, tamam mı?"], ["{L1} called yesterday, tamam mı?"]),
    ("M", None, ["the lee side of the ship"], ["the lee side of the ship"]),
    ("M", None, ["can you call Mehmet"], ["can you call {L1}"]),
    # both packs: an English given name that is an ordinary Turkish word is a word-name (and the reverse)
    ("M", None, ["ben geldim", "kim aradı", "kira ne kadar", "ara beni", "sal gitsin"],
     ["ben geldim", "kim aradı", "kira ne kadar", "ara beni", "sal gitsin"]),
    ("M", None, ["ben Mehmet'i aradım, Mehmet kim dedi"], ["ben {L1}'i aradım, {L1} kim dedi"]),
    ("M", None, ["yesterday Ben called, then Kim said hi"], ["yesterday {L1} called, then {L2} said hi"]),
    ("M", (H, "Kim Arslan"), [("Kim Arslan", "selam"), "Kim burada mı?"], ["selam", "{P:Kim Arslan} burada mı?"]),
    # both packs: a lower-case English given name that is an ordinary English word stays the word, as with 'en' alone
    ("M", None, ["it is 300 miles away", "we sell rice and euros, prices increase"],
     ["it is 300 miles away", "we sell rice and euros, prices increase"]),
    ("M", None, ["Miles called yesterday", "it is 300 miles away"], ["{L1} called yesterday", "it is 300 miles away"]),
    # S5: the national phone shapes of every shipped pack, whatever the selection; S9: an IBAN of any country
    # (mod-97 check) before the phone rule; a wrong check sum stays text (its phone-shaped part is still a phone)
    ("C", None, ["call 0532 111 22 33"], ["call [phone]"]),
    ("K", None, ["IBAN DE89 3704 0044 0532 0130 00"], ["IBAN [iban]"]),
    ("K", None, ["iban TR33 0006 1005 1978 6457 8413 26 thanks"], ["iban [iban] thanks"]),
    ("K", None, ["NL91ABNA0417164300 and FR14 2004 1010 0505 0001 3M02 606"], ["[iban] and [iban]"]),
    ("K", None, ["ref DE89 3704 0044 0532 0130 01"], ["ref DE89 3704 [phone]"]),
    # B1 (review of a65d79e): no language signal selects both packs; a capitalized first word, a given name of the
    # English pack and an unlisted surname ending the line or the sentence: the whole name
    ("M", None, ["Call Emily Zabrowski"], ["Call {L1}"]),
    ("M", None, ["Ask Emily Zabrowski"], ["Ask {L1}"]),
    ("M", None, ["Tel Emily Zabrowski"], ["Tel {L1}"]),
    ("M", None, ["WhatsApp Emily Zabrowski"], ["WhatsApp {L1}"]),
    ("M", None, ["Contact Emily Zabrowski"], ["Contact {L1}"]),
    ("M", None, ["Call Emily Zabrowski, thanks"], ["Call {L1}, thanks"]),
    ("M", None, ["Call Emily Tomorrow"], ["Call {L1} Tomorrow"]),         # a common word is no surname
    # B4: Turkish clearly dominates (>= 3/4 of the voting messages): an English given name that is an ordinary Turkish
    # word needs strong evidence (honorific, suffix, surname, contact, participant); a capital alone is not enough
    ("M", None, TR8 + ["tamam, Kim gelecek bilmiyorum", "dün Ben söyledim", "yarın Ara bakalım", "bu ay Kira gecikti",
                       "sonra Ana kapıdan gir"],
     TR8 + ["tamam, Kim gelecek bilmiyorum", "dün Ben söyledim", "yarın Ara bakalım", "bu ay Kira gecikti",
            "sonra Ana kapıdan gir"]),
    ("M", None, TR8 + ["Kim Hanım geldi", "dün Ben'e söyledim"], TR8 + ["{L1} Hanım geldi", "dün {L2}'e söyledim"]),
    ("M", PEOPLE + ("Kim Doran",), TR8 + ["tamam, Kim gelecek bilmiyorum"],
     TR8 + ["tamam, {P:Kim Doran} gelecek bilmiyorum"]),
    # ... English dominates: 'Ben' is the English name there (its ordinary sense is Turkish)
    ("M", None, EN8 + ["yesterday Ben called"], EN8 + ["yesterday {L1} called"]),
    # ... balanced mixed chat: the rule before stays (a capital in mid-sentence is context)
    ("M", None, ["good morning, see you there", "ok thanks, I will be there", "tamam, Kim gelecek bilmiyorum",
                 "evet geliyorum"],
     ["good morning, see you there", "ok thanks, I will be there", "tamam, {L1} gelecek bilmiyorum", "evet geliyorum"]),
]


def run(rows, people=PEOPLE, packs=("en",)):
    """rows: [(sender or None, text)] -> (message text lines, Anonymizer)."""
    wa2md.use_pack(wa2md.wa2md_lang.merge(packs, labels="en"))
    try:
        rows = [(p, "hello there") for p in people] + list(rows)
        text = "".join(f"11/14/26, 9:{i:02d} AM - " + (f"{s}: {t}" if s else t) + "\n" for i, (s, t) in enumerate(rows))
        msgs, _ = wa2md.parse(wa2md.decode(text.encode("utf-8")))
        group = wa2md.is_group(msgs, TITLE)
        msgs = wa2md.mark_system_lines(TITLE, msgs, group)
        a = wa2md.Anonymizer(TITLE, msgs, 1, None, group=group)
        out, _, _ = wa2md.render(TITLE, msgs, None, anon=a)
    finally:
        wa2md.use_pack(None)
    lines = [ln.strip().strip("_").strip() for ln in out.split("\n")
             if ln.strip() and not ln.startswith(("#", "- ", "**"))]
    return lines[len(people):], a


def _template_rx(exp, a):
    out, seen = [], []
    for part in re.split(r"(\{P:[^}]+\}|\{L\d+\})", "\n".join(exp)):
        if part.startswith("{P:"):
            out.append(re.escape(a.labels[part[3:-1]]))
        elif re.fullmatch(r"\{L\d+\}", part):
            if part in seen:
                out.append(f"(?P={part[1:-1]})")
            else:
                seen.append(part)
                out.append(rf"(?P<{part[1:-1]}>Person \d+)")
        else:
            out.append(re.escape(part))
    return "".join(out), seen


def check(case, row):
    cls, people, msgs, exp = row
    rows = [m if isinstance(m, tuple) else (H, m) for m in msgs]
    out, a = run(rows, people or PEOPLE, ("tr", "en") if cls.startswith("M") else ("en",))
    got = "\n".join(out)
    rx, ls = _template_rx(exp, a)
    m = re.fullmatch(rx, got)
    case.assertTrue(m, f"[{cls}] {msgs!r}\n  expected: {exp!r}\n  got:      {out!r}")
    labs = [m.group(x[1:-1]) for x in ls]
    case.assertEqual(len(set(labs)), len(labs), f"[{cls}] different people got one label: {out!r}")
    for x in labs:
        case.assertNotIn(x, a._people, f"[{cls}] participant label not expected: {out!r}")


class DecisionTableEnglish(unittest.TestCase):
    def test_rows(self):
        for row in ROWS:
            with self.subTest(cls=row[0], msgs=row[2]):
                check(self, row)

    def test_table_size_and_classes(self):
        self.assertGreaterEqual(len(ROWS), 80)
        self.assertEqual({r[0] for r in ROWS}, {"S", "N", "T", "W", "PL", "X", "C", "G", "F", "L", "K", "Y", "M"})


if __name__ == "__main__":
    unittest.main()
