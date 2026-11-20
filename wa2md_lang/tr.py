"""Turkish language pack: the word lists, patterns and output labels of wa2md's Turkish behaviour.

Moved verbatim from wa2md.py / wa_web.py (issue #2): the lists keep the English words they already contained, so
the output under this pack is byte-identical to the engine before the move. Field meanings: wa2md_lang.LanguagePack.
"""
from wa2md_lang import Labels, LanguagePack


def _national_phones(b):
    """Turkish national phone shapes (alternatives of the engine's phone pattern, in this order). b: building blocks
    of the engine (dl, DG, DG0, GS, GS0, GS_T, SEP, DATE_AHEAD, GLUED)."""
    _dl, _DG, _DG0, _GS, _GS0, _GS_T, _SEP = b.dl, b.DG, b.DG0, b.GS, b.GS0, b.GS_T, b.SEP
    _DATE_AHEAD, _GLUED = b.DATE_AHEAD, b.GLUED
    _TRUNK = rf"\(?(?:(?:(?:\+|{_dl(0)}{{2}}){_GS_T}?)?{_dl(9)}{_dl(0)}{_GS_T}?(?:{_dl(0)}{_GS_T}?)?|(?:{_dl(0)}{_GS_T}?){{1,2}})"
    # Telefon: (1) onekli (0/90/+90) TR numarasi, gruplama ve ayractan bagimsiz, BUTUN rakam dizisi: cep 9-10 ulusal hane
    # (4-2-4 gibi bir hanesi eksik yazim dahil), sabit hat 10; dizi orada biter (ardinda ayrac + rakam yok). (2) sabit
    # kaliplar (dizi bitmese de: '0500 000 00 00 2 araç'). (4) sozcuge yapisik oneksiz cep (yalniz iletisim sozcugunden
    # sonra), (5) parantezli alan kodu. The engine adds the universal '00 <country>' and '+<8-15 digits>' alternatives
    # and the common bounds; the first characters of those never overlap these, so the order between them is free.
    return [
        rf"(?=[(+]|{_dl(0, 5, 9)})(?<!\d[.,]){_DATE_AHEAD}(?:\(?{_dl(0)}?{_dl(5)}{_DG}{{2}}\)?{_GS})?{_TRUNK}\(?"
        rf"(?:{_dl(5)}(?:{_GS}?{_DG}){{8,9}}|{_dl(2, 3, 4, 8)}(?:{_GS}?{_DG}){{9}})(?!{_GS0}?{_DG0})",   # 8: 0850/0800
        rf"(?=[(+]|{_dl(0, 9)})(?<!\d[.,]){_TRUNK}\(?{_dl(2, 3, 4, 5, 8)}{_DG}{{2}}\)?{_SEP}?{_DG}{{3}}{_SEP}?{_DG}{{2}}{_SEP}?{_DG}{{2}}",
        rf"(?:(?<!\w){_GLUED})(?<!\d[.,\-]){_dl(5)}{_DG}{{2}}{_SEP}?{_DG}{{3}}{_SEP}?{_DG}{{2}}{_SEP}?{_DG}{{2}}",   # oneksiz TR cep
        rf"(?<!\w)(?<!\d[.,\-])\({_dl(2, 3, 4, 5)}{_DG}{{2}}\){_SEP}?{_DG}{{3}}{_SEP}?{_DG}{{2}}{_SEP}?{_DG}{{2}}",  # (322) 000 00 01
    ]


LABELS = Labels(
    chat="Sohbet-{n}",
    chat_fallback="sohbet",
    person_word="Kişi",
    person_sep=" ",
    unknown_mark="?",
    masks={"phone": "[telefon]", "company": "[firma]", "path": "[yol]", "email": "[e-posta]", "user": "[kullanıcı]",
           "password": "[parola]", "code": "[kod]", "iban": "[iban]", "national_id": "[tckn]", "plate": "[plaka]"},
    media="medya-{n}{ext}",
    participants="Katılımcılar",
    message_count="Mesaj sayısı",
    date_range="Tarih aralığı",
    media_omitted="_(medya dahil edilmemiş)_",
    file_missing="_(dosya eksik: {name})_",
    attachment_not_copied="_(ek kopyalanmadı: {name}, {kind})_",
    forwarded="Yönlendirilmiş mesaj",
    deleted="Bu mesaj silindi",
    download_failed="{kind} indirilemedi: {label}",
    own_name="Ben",
    web_kinds={"image": "fotoğraf", "gif": "gif", "video": "video", "audio": "ses", "document": "belge"},
    kinds={"image": "görüntü", "video": "video", "audio": "ses", "contact": "kişi kartı", "pdf": "PDF",
           "office": "ofis belgesi", "archive": "arşiv", "other": "diğer"},
    manifest_file="ekler.md",
    manifest_head=("# Ekler", "",
                   "Her ekin durumu. **Kopyalanan her dosya elle kontrol edilmeli**: görüntü/video/ses içeriği (yüzler, "
                   "ekran görüntüleri, sesler, belgelerdeki adlar) anonimleştirilmez.", "",
                   "| Dosya | Tür | Durum |", "|---|---|---|"),
    status_copied="kopyalandı, elle kontrol gerekli",
    status_no_media="kopyalanmadı (--medya-yok)",
    status_missing="eksik (dışa aktarımda yok)",
    status_not_copied="kopyalanmadı (kişisel veri içerebilir; --belgeleri-kopyala)",
    review_suffix="-supheli-adlar.txt",
)


PACK = LanguagePack(
    code="tr",
    name="Türkçe",
    labels=LABELS,
    fold_i="iIıİ",
    fold_pairs={"c": "çÇ", "g": "ğĞ", "o": "öÖ", "s": "şŞ", "u": "üÜ"},
    ampm=r"[AaPp]\.?\s?[Mm]\.?|ÖÖ|ÖS|öö|ös",
    pm=r"p|ös$",
    attach_android=r"dosya ekli|file attached",
    attach_ios=r"ek|attached",
    omitted=r"dahil edilmedi|omitted",
    strip_name=[r"^WhatsApp Chat with\s+", r"\s+ile WhatsApp Sohbeti$", r"^WhatsApp Chat\s*-\s*",
                  r"^WhatsApp Sohbeti\s*-\s*"],
    # ---- sistem satirlarindaki kisiler (eklendi/katildi/ayrildi/...): Ingilizce ve Turkce yerel
    system_patterns=(
        r"^your security code with (?P<s>.+?) changed\b",
        r"^(?P<s>.+?) changed to (?P<same>\+?\d[\d ()\-]{6,}\d)\b",
        r"^(?P<s>.+?) made (?P<o>.+?) an? admin\b",
        r"^(?P<s>.+?) (?:added|removed) (?P<o>.+?)\.?$",
        r"^(?P<s>.+?) (?:created group|created this group|changed the subject|changed the group|changed this group|"
        r"deleted this group|reset this group|joined using|joined from|joined via|left\b|was added|was removed|"
        r"is now an admin|requested to join|changed their phone number|changed the settings|pinned a message|"
        r"started a (?:video |voice )?call|turned (?:on|off))",
        r"^(?P<s>.+?) ile güvenlik kodunuz değişti",
        r"^(?P<s>.+?),? (?P<same>\+?\d[\d ()\-]{6,}\d) numaras[ıi]na geçti",
        r"^(?P<s>[^,]+?), (?P<o>.+?)(?: adlı kişiyi| adlı kişileri| kişisini| kişilerini)? (?:ekledi|çıkardı|yönetici yaptı)\.?$",
        r"^(?P<s>.+?) (?:sizi|seni) (?:ekledi|çıkardı)",
        r"^(?P<s>.+?),? (?:[\"“].*[\"”] )?(?:grubunu|grubu) oluşturdu",
        r"^(?P<s>.+?) (?:bu grubun|grubun|grup |konuyu|telefon numarasını|numarasını|davet bağlantısı|bu grubu|topluluktan|"
        r"gruptan|bir mesajı sabitledi|aramayı başlattı|artık yönetici)",
        r"^(?P<s>.+?) (?:katıldı|ayrıldı|eklendi|çıkarıldı)\.?$",
    ),
    subject_change=r"created group|changed the subject|changed the group name|changed this group's name|"
                          r"grubunu oluşturdu|konuyu|grup adını|grubun adını|olarak değiştirdi",
    system_split=r",\s*(?:and\s+|ve\s+)?|\s+(?:and|ve)\s+",
    system_not_person=frozenset({"you", "your", "siz", "sizi", "seni", "sen", "ben", "beni", "biz"}),
    system_bad=r"[\"“”:/@]|https?|\b(?:messages?|mesaj\w*|group|grub?\w*|this|bu)\b",
    # iOS sistem satirlari gonderen yerinde grup adiyla gelir ('[..] Grup: Ali added Veli'); kisisiz bildirimler de oyle
    system_notice=r"end-to-end encrypted|uçtan uca şifreli|disappearing messages|süreli mesaj|security code|"
                             r"güvenlik kod|group description|grup açıklama|admin approval|only admins|yalnızca yönetici|"
                             r"changed (?:the|this) group|group icon|grup simgesi|grup resmi",
    group_event=r"\b(?:added|removed|joined|left|created (?:this )?group|changed the subject|changed (?:the|this) "
                            r"group|is now an admin|made .+ admin)\b|\b(?:ekledi|çıkardı|katıldı|ayrıldı|oluşturdu|gruptan|"
                            r"grubun|bu grubu|konuyu|yönetici)",
    # Yalniz grupta olan olaylar (tam satir): sohbetin grup oldugunu ve iOS'ta grup adiyla gelen satirin sistem satiri
    # oldugunu yalniz bunlar soyler. Siradan mesajda da gecen sozcukler ('Kardeşim de katıldı.', 'Ali ayrıldı') sayilmaz.
    group_only_patterns=(
        r'^(?P<s>.+?) created (?:group [\"“].*[\"”]|this group)\.?$',
        r"^(?P<s>.+?) (?:added|removed) (?P<o>.+?)\.?$",
        r"^(?P<s>.+?) joined (?:using this group's invite link|using an invite link|from the community|via invite link)",
        r"^(?P<s>.+?) changed (?:the subject|this group's icon|the group description|this group's settings|the group name|"
        r"this group's name|the group icon)\b",
        r"^(?P<s>.+?) (?:is now an admin|made .+ an? admin)\b",
        r"^you(?:'re| are) now an admin\b|^you were added\b",
        r'^(?P<s>.+?),? (?:[\"“].*[\"”] )?(?:grubunu|grubu) oluşturdu\.?$',
        r"^(?P<s>[^,]+?), (?P<o>.+?)(?: adlı kişiyi| adlı kişileri| kişisini| kişilerini)? (?:ekledi|çıkardı)\.?$",
        r"^(?P<s>.+?) (?:sizi|seni) (?:ekledi|çıkardı)\b",
        r"^(?P<s>.+?),? (?:bu grubun |grubun )?davet bağlantısı(?:yla| ile|nı kullanarak) katıldı",
        r"^(?P<s>.+?) (?:konuyu|grup adını|grubun adını|grup simgesini|grubun simgesini|bu grubun simgesini|grup açıklamasını|"
        r"grubun açıklamasını|grubun ayarlarını|bu grubun ayarlarını) ",
        r"^(?P<s>.+?),? gruptan ayrıldı\.?$",
        r"^(?P<s>.+?),? (?:artık yönetici|(?P<o>.+?) adlı kişiyi yönetici yaptı)",
    ),
    # grupta, grup adiyla gelen ad bicimli olay satiri ('Jorvik Plimm left', '+90 500 ... katıldı'): yalniz donusturmede
    group_weak=r"^(?P<s>.+?),? (?:left|joined|was added|was removed|ayrıldı|katıldı|eklendi|çıkarıldı)\.?$",
    # on eleme: olay, sistem satiri ve bildirim desenlerinin (_GRP_ONLY, _GRP_WEAK, _SYS_PATTERNS, _SYS_NOTICE) anahtar
    # sozcuklerinden biri yoksa satir olay/bildirim degildir (duz alt dize aramasi: buyuk mesaj akisinda hizli)
    event_words=(
        "added", "removed", "changed", "made", "created", "deleted", "reset", "joined", "left", "was ", "is now", "now an",
        "requested", "pinned", "started", "turned", "security", "you were", "encrypted", "disappearing", "description",
        "admin", "icon", "ekledi", "çıkardı", "çıkarıldı", "eklendi", "katıldı", "ayrıldı", "oluşturdu", "yönetici", "grubun",
        "grup ", "grubu", "gruptan", "konuyu", "numaras", "güvenlik", "davet", "topluluktan", "sabitledi", "aramayı",
        "şifreli", "süreli", "açıklama", "simgesi", "resmi"),
    self_refs=frozenset({"you", "sizi", "seni", "siz"}),
    name_suffix_strip=r"['’][a-zçğıöşü]+$",
    web_system_skip=r"uçtan uca şifrel|end-to-end encrypt|Bu sohbetteki mesajlar",
    web_weekdays=["pazartesi", "sali", "carsamba", "persembe", "cuma", "cumartesi", "pazar",
                 "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
    web_today=frozenset({"bugun", "today"}),
    web_yesterday=frozenset({"dun", "yesterday"}),
    # Kapali ek listesi (tek parca adlara apostrofsuz eklenebilen): kucultme/sevgi + cogul + iyelik + hal ekleri.
    name_suffixes=(
        [c + v + g + w + m for c in "cç" for v in "ıiuü" for g in ("ğ",) for w in "ıiuü" for m in ("m",)]
        + [c + v + k for c in "cç" for v in "ıiuü" for k in "mk"],                                       # kucultme/sevgi
        ["lar", "ler"],                                                                                  # cogul
        ["ım", "im", "um", "üm", "ın", "in", "un", "ün"],                                                # iyelik
        ["a", "e", "ya", "ye", "ı", "i", "u", "ü", "yı", "yi", "yu", "yü", "da", "de", "ta", "te", "dan", "den",
         "tan", "ten", "la", "le", "yla", "yle", "nın", "nin", "nun", "nün", "ca", "ce", "çe", "ça"],     # hal
    ),
    # Nakliye sektor sozcukleri: TEK liste. Ticari adda (_FIRM_TAIL, Anonymizer._special) ve ciplak alan adinda
    # (Anonymizer._web) ayni sozcukler; _SECTOR_GENERIC'tekiler genel ya da kisa oldugu icin alan adinda aranmaz (buyuk kargo
    # firmalari, 'translate', 'nakit'). Ekli bicimler (Nakliyattan, Nakliyatın, Lojistiği) _SECTOR_SFX ile.
    sector_words=("nakliyat nakliye nakliyeci nakliyecilik lojistik taşımacılık taşıma transport trans kargo logistics logistic "
                 "nak nakl nakliyatı nakliyesi lojistiği taşımacılığı").split(),
    sector_generic=frozenset("taşıma trans kargo nak nakl".split()),
    # ilke 4: GUCLU sektor sozcugu (ticari ad ilan imi olmadan da maskelenir): nakliyat, nakliye, nakliyeci(lik), lojistik,
    # taşımacılık, logistic(s) ve ekli bicimleri. Zayif tetikleyiciler (taşıma, trans, transport, kargo, Nak., şirketi,
    # firması) ilan imi ister ('HTTP Transport ayarı', 'Annem Kargo'dan aldı', 'Elektrik Şirketi aradı').
    sector_weak_extra=frozenset({"transport"}),
    sector_suffixes=("ı i sı si ın in nın nin a e ya ye da de ta te dan den tan ten la le yla yle lar ler ları leri cı ci "
                     "cılar ciler cılık cilik ımız imiz").split(),
    # F: ciplak isletme alan adi ('www.ornekfirmaNakliyat.com.tr', 'nakliyat.ornekfirma.com.tr', 'www.ornekfirma.nakliyat.com'). Dar kural:
    # yalniz ticari uzantilar (.com/.net/.biz/.info/.tr, .com.tr...; .org/.gov/.edu degil); yalniz kayitli ad ve hemen ustundeki
    # alt alan (www/m on ekleri sayilmaz) bakilir; bunlardan birinde genel olmayan sektor sozcugu varsa, bu iki etiketten AYIRT
    # EDICI olan(lar) [firma] olur. Sektor sozcugunu cikarinca yalniz ek kalan etiket ('nakliyat', 'transportation') genel
    # sozcuktur, firma degildir. Yazilim sohbetindeki baglantilar (github.com, belgeler, urunun kendi alan adlari) bu sozcukleri
    # icermez, okunur kalir. Ana makine dogrusal eslesir ([\w-]+ etiketleri); sektor sozcugu _web()'de aranir (eski kalip
    # '[\w-]*(sozcuk)[\w-]*' uzun sozcukte karesel taraniyordu). Buyuk/kucuk harf duyarsiz (KAPLONAKLİYAT.COM).
    web_affixes=frozenset(set("ation ations s er ers ci cilik i si in tr turk online net web app api mail portal panel blog shop "
                     "store admin destek".split()) | {""}),
    web_prefixes=frozenset({"www", "m", "mobile", "tr", "en", "web"}),
    web_noncommercial=frozenset({"org", "gov", "edu", "k12", "bel", "pol", "tsk", "av", "dr", "name", "tv", "bbs", "tel", "mil"}),
    web_tld=r"\.(?:com|net|biz|info)(?:\.tr)?|\.(?:web|gen|biz)\.tr|\.tr",
    web_tld_quick=r"\.(?:com|net|biz|info|tr)",
    # sektor sozcugu ve hukuki bicim: onlerindeki buyuk harfli sozcukler firma adinin ayirt edici kismidir -> [firma].
    # Hizmet sozcukleri zincirin parcasidir ('Kaplo Lojistik Hizmetleri Ltd. Şti.': tek maske).
    legal_words=("ltd limited şti şirketi firması san sanayi tic ticaret inş inşaat paz pazarlama ith ihr ithalat ihracat ve "
                "hizmetleri hizmet hizmetler").split(),
    legal_strong="ltd limited şti şirketi firması".split(),
    # hukuki bicim (ikinci ilan imi gerekmez): Ltd, Şti, A.Ş., San.+Tic., Limited+Şirketi. Tek 'Şirketi' siradan sozcuktur
    # ('Elektrik Şirketi aradı').
    legal_form="ltd şti".split(),
    legal_san="san sanayi".split(),
    legal_tic="tic ticaret".split(),
    legal_pair=("limited", "şirketi"),
    legal_glued=r"(?i:ltd\.|\.[şs]t[iİıI])",
    legal_special=r"[Aa]\.?[ ]?[Şş]",
    legal_special_chars="Şş",
    kin="kardeşler kardeşleri oğulları oğlu ve &".split(),
    kin_join=("ve", "&"),
    # ilke 4a: ticari ad kuralinin durdurma listesi: nakliye ilanlarinda ve gunluk konusmada sik genel nitelemeler (bunlar
    # ayirt edici sozcuk degildir: 'Şehirler Arası Nakliyat', 'Uygun Fiyatlı Taşımacılık', 'Güvenilir Nakliye Hizmeti',
    # 'Proje Lojistiği'). Il, ilan, hitap ve dolgu sozlukleri ayrica dislanir. Ad kurallari (main) bunlara yine uygulanir.
    # S4: dilbilgisi sozcukleri (belirtec, sayi, baglac, zamir, iyelikli akrabalik) hukuki bicimli zincirde de ad degildir;
    # listenin geri kalani (nitelemeler) ve yer adlari hukuki bicim varken ayirt edici sozcuktur ('Ekspres Lojistik A.Ş.')
    firm_func=(
        "her türlü bütün tüm bir iki üç dört beş altı yedi sekiz dokuz on yüz bin hangi bazı birçok başka aynı kendi dün "
        "sonra önce ama fakat ancak çünkü yani belki sanırım galiba ayrıca hatta zaten yine gene hep artık henüz biraz çok az "
        "en daha benim senin onun bizim sizin onların annem babam eşim oğlum kızım ailem").split(),
    firm_stop=(
        "şehirler arası şehir içi ulusal yerel bölgesel global kaliteli güvenilir profesyonel ekonomik fiyatlı garantili "
        "asansörlü ambalajlı paketli ekspres express özel kurumsal bireysel ticari ağır hafif proje soğuk zincir kombine "
        "karayolu denizyolu havayolu demiryolu büro piyano oto otomobil makine hayvan canlı kötü büyük küçük ürün tedarik "
        "zinciri satın alma tersine iç dış askeri sağlık dijital entegre festival kermes mahalle").split(),
    # ilke 4c: yalin hitap firma adi olabilir ('ABLA NAKLİYAT'); cogul/iyelik/hal ekli hitap hitap obegidir ('Değerli Abilerim
    # Nakliye', 'Hocam Nakliyat'), firma adi degil
    hon_base="bey beyefendi hanım hanımefendi abi abla hoca başkan kardeş amca teyze usta ağabey abey reis "
                 "dayı".split(),
    # S5: tekil iyelik ekli hitap ('DAYIM NAKLİYAT', 'Ustam Nakliyat') firma adi olabilir; hitap sifatindan sonra ('Değerli Dayım
    # Nakliye') ya da cogul bicimde ('Abilerim') hitap obegidir. Anahtar bicimi.
    hon_singular=r"(?:bey|beyefendi|hanim|hanimefendi|abi|abla|hoca|baskan|kardes|amca|teyze|usta|agabey|abey|reis"
                         r"|dayi)(?:im|um|m)",
    address_adjectives="sayın sn değerli kıymetli sevgili muhterem saygıdeğer aziz canım".split(),
    calendar_words=("ocak şubat mart nisan mayıs haziran temmuz ağustos eylül ekim kasım aralık pazartesi salı "
                                 "çarşamba perşembe cuma cumartesi pazar").split(),
    capitalized_words="türk ege asya medine islam kuzey güney doğu akdeniz karadeniz".split(),
    honorific_after=r"(?:bey|beyefendi|hanim|hanimefendi|abi|abla|hoca|baskan|kardes|amca|teyze|usta|agabey|abey|reis|dayi)"
                      r"(?:ler|lar)?(?:imiz|umuz|miz|muz|im|um|m)?(?:cigim|cugum|cim|cum)?"
                      r"(?:['\u2019]?(?:yle|yla|nin|nun|den|dan|ye|ya|yi|yu|in|un|de|da|le|la|si|e|a|i|u))?",
    honorific_org=r"baskani(?!m)[a-z]*|baskanlig[a-z]*",
    honorific_stop=(
        "tamam selam merhaba merhabalar günaydın iyi evet hayır sağol sağolun teşekkürler teşekkür aynen peki tabi tabii olur "
        "hadi haydi hayırlı kolay rica estağfurullah eyvallah valla vallahi allah sayın değerli kıymetli sevgili muhterem "
        "saygıdeğer canım ben sen siz biz onlar bu şu o ve ile ya yok var ne nasıl kusura geçmiş hoş hoşgeldin hoşgeldiniz "
        "lütfen bence genel yönetim kurulu kurul bölge şube il ilçe dernek derneği grup grubu ekip ekibi takım merkez müdür "
        "müdürlük daire belediye belediyesi oda odası vakıf vakfı federasyon kulüp kulübü birlik birliği komisyon meclis "
        "onursal eski yeni sağ baş başkan abi abla hocam hoca usta amca teyze kardeş bey hanım reis dayı ağabey "
        "selamlar selamün aleyküm aleykümselam teşekkürlerim kardeşim abim başkanım hocamız ustam hayırdır günler geceler "
        "akşamlar iyiyim tebrikler tebrik bravo süper harika güzel aferin maşallah inşallah amin hakkınızda hakkın "
        "doktor dr av müh öğretmen kaptan komutan şef ekibimiz arkadaşlar arkadaşım dostum kanka reisim").split(),
    title_before=frozenset({"sayin", "sn"}),
    title_not_name_suffix=r"(?:imiz|umuz|miz|muz|lar|ler|larimiz|lerimiz)$",
    title_stop=(
        "yetkili ilgili müşteri katılımcı arkadaş meslektaş hocam başkanım müdürüm bakanım valim vekilim kaymakamım dekanım "
        "rektörüm hakim savcı avukat doktor dr av müh prof doç yrd öğretmen veli üye vatandaş okuyucu yolcu "
        "komutanım amirim kurul heyet").split(),
    chat_title_stop="bizim benim sizin onların büyük küçük geniş mutlu canım güzel tatlı yeni eski".split(),
    family_words="aile ailesi ailemiz family kuzenler akrabalar sülale sülalesi".split(),
    surname_suffix=r"..(?:oglu|ogullari|gil|soy|turk|demir|kaya|tas|yildiz|aslan|arslan|dogan)$",
    landmark_before=r"(?:^|[^\w])(?:[Hh][Zz]|Hazreti|Hazret|HAZRETİ)\.?[ \t]*$",
    # yer/kurum adi: ad + bu sozcuk (ya da araya buyuk harfli sozcukler) -> dokunulmaz (Mimar Sinan Üniversitesi, Hz. Muhammed)
    institution_any=("üniversitesi lisesi hastanesi köprüsü caddesi bulvarı mahallesi camii stadı stadyumu ilkokulu ortaokulu "
                   "havalimanı havaalanı fakültesi enstitüsü müzesi kütüphanesi istasyonu otogarı kampüsü").split(),
    institution_cap=("sokağı sokak cad sok mah cami parkı meydanı okulu koleji barajı vakfı kışlası tüneli kulesi çarşısı pazarı "
                   "köyü ilçesi apartmanı sitesi hanı oteli limanı yolu terminali yurdu salonu merkezi gölü dağı çayı ırmağı "
                   "nehri tepesi kalesi türbesi").split(),
    # ---- nakliye ilanlari: iletisim baglami, ticari ad, ilan sozlugu (anahtar bicimi; tek kod yolu: Anonymizer._scan)
    # iletisim sozcugu: ardindaki (ayrac ya da satirda telefon varsa), onundeki ya da maskelenen telefonun yanindaki buyuk
    # harfli 1-3 sozcuk kisi adidir
    # S6: iletisim kanali sozcukleri ve sik yanlis yazimlari da (alan etiketidir, ad olarak ogrenilmez)
    contact_words=("irtibat irt iletişim ilt tel tlf telefon gsm cep yetkili sorumlu whatsapp wp whatsap watsap watsapp vatsap "
                  "vatsapp wtsp wsp telegram").split(),
    # S3c: birim adi ('Muhasebe Birimi', 'Satış Departmanı', 'Gündüz Ekibi') kisi degildir: iletisim adi olarak alinmaz. Anahtar
    # bicimi; iyelik eki sart, hal eki olabilir ('Biriminden'). Ticari ad kuralinda dislama yalniz durdurma listesidir (5. tur).
    org_unit=r"(?:birim|departman|ekib|bolum|mudurlug|sube|ofis|servis|depo|merkez|grub|takim|kalem|sekreterlig)"
                           r"(?:i|u|si|su)(?:n|ne|na|nde|nda|nden|ndan|nin|nun|yle|yla)?",
    # dolgu ve alan etiketi sozcukleri: iletisim baglaminda hicbir zaman ad degildir ('İRTİBAT İÇİN:', 'Tel No:',
    # 'Hafta İçi Arayınız', '[telefon] Sadece WhatsApp', 'Yetkili Servis'); numara*/telefon*/iletişim*/irtibat* ekli bicimleri de
    filler_words=("no nu nr numara için icin sadece yalnız yalnızca lütfen arayınız arayın ara arama arayabilirsiniz ulaşın "
                 "ulaşınız ulaşabilirsiniz bilgi bilgileri bilgisi bilgilendirme kişi kişisi hat hattı hattımız hafta içi sonu "
                 "mesai saat saatleri saatlerinde servis servisi destek müşteri hizmet hizmeti hizmetleri fatura faturası web "
                 "mesaj mesajı sms adres adresi mail eposta email faks fax sabit mobil ev iş işyeri satış muhasebe operasyon "
                 "randevu rezervasyon business api phone contact call mobile number info only büro "
                 "ad adı soyad soyadı isim ismi unvan unvanı ünvan ünvanı diğer ikinci birinci alternatif yedek santral "
                 "dahili ofis").split(),
    filler_prefixes="numara telefon iletişim irtibat whatsapp".split(),
    ordinary_words=(
        "ola olsun olur gele kolaylıklar bereketli uğurlu geçmiş sevgiler saygılar selamlar teşekkürler rica ederim "
        "bilginize bilgilerinize duyurulur önemle aşağıda yukarıda burada orada şurada içeride dışarıda dostlar cepten "
        "cebimden numaradan").split(),
    # ilke 3: siradan sozcuk testi (zayif kanit yalniz bundan gecerse maskelenir; guclu bulgu gecmezse yalniz o yerde kalir).
    # Anahtar bicimi (_key: ı->i, ü->u, ş->s, ç->c, ğ->g, ö->o). Cekim ekleri: simdiki/gecmis/gelecek zaman, emir, gereklilik,
    # mastar, yeterlilik, -ArIm/-ArIz, cogul (+iyelik, hal), iyelik, -deki, ulac. Soyadlarinda sik olan '-an/-en' (Doğan,
    # Gülen), '-ar/-er' (Uçar), '-maz' (Yılmaz), '-li' (Erdemli) bilerek YOK; listedeki ad/soyad hic sayilmaz.
    ordinary_suffix=r"(?:[iu]?yor(?:um|sun|uz|sunuz|lar|ler|du|dum|duk|dunuz|mus|sa)?|s[iu]n(?:lar|ler)?"
        r"|[dt][iu](?:m|n|k|niz|nuz|lar|ler)?|m[iu]s(?:im|sin|iz|siniz|lar|ler|tir)?"
        r"|[ae]c[ae]k(?:sin|im|iz|siniz|lar|ler|tir)?|[ae]c[ae]g[iu][mz]|m[ae]l[iu](?:yim|sin|yiz|siniz|lar|ler|dir|ydi)?"
        r"|m[ae]k|[ae]bil[iu]r(?:im|sin|iz|siniz|ler|lar)?|[aeiu]r[iu][mz]"
        r"|l[ae]r[iu]?(?:m|n|miz|niz|n[iu]n)?(?:l[ae]|[ae]|d[ae]|d[ae]n)?|[iu]ml[ae]|[iu]n[iu]z(?:l[ae])?|[iu]m[iu]z"
        r"|[aeiou]s[iu]|[dt][ae]ki|[iu]nc[ae]|[ae]r[ae]k)$",
    # ilan sozlugu: il adlarinin gayriresmi bicimleri, yuk merkezi semtleri, ulke/bolge, arac/dorse, birim, sik ilan sozcukleri.
    # Bunlar kisi ya da firma adi sayilmaz. Il ve ilce adlarinin TEK kaynagi yer listesidir (adlar/tr-yerler.txt, places());
    # il adlari yuklenince bu sozluge katilir (_LISTS['ilan']).
    listing_places=("afyon antep maraş urfa içel hadımköy ambarlı "
                     "türkiye irak iran suriye gürcistan azerbaycan nahçıvan bulgaristan yunanistan romanya rusya ukrayna "
                     "almanya avrupa asya trakya anadolu marmara doğu batı orta").split(),
    listing_words=(
        "tır tir kamyon kamyonet kırkayak onteker teker lowbed lowbet tenteli tente damper frigo frigorifik dorse çekici "
        "panelvan pikap kasa açık kapalı sal sallı platform konteyner tanker silobas flatbed mega jumbo minivan vinç "
        "ton kg kilo palet paletli metre km tl lira euro dolar adet desi "
        "acil yük yükü yükler araç aracı araçlar aranıyor aranır lazım gerekli var yok boş dolu müsait fiyat fiyatı ücret "
        "navlun peşin nakit havale komisyon yükleme boşaltma indirme teslim teslimat çıkış çıkışlı varış dönüş gidiş "
        "parsiyel komple günlük haftalık aylık sefer sevkiyat ilan bilgi detay detaylı not uygun ucuz hızlı güvenli "
        "sigortalı sahibinden firma firması şirket merkez şube depo antrepo liman gümrük fabrika ofis sabah akşam gece "
        "bugün yarın hemen şimdi evden eve şehirlerarası şehiriçi uluslararası yurtiçi yurtdışı ithalat ihracat parça eşya "
        "mobilya hurda malzeme gıda çimento kum tuğla kereste hububat buğday arpa mısır saman meyve sebze mimar mühendis "
        "şoför sürücü dikkat duyuru önemli").split(),
    place_region_kind="il",
    # S8: yalniz kisinin ozne olamayacagi bicimler ('X yüklemeli', 'X çıkışlı'); 'X indirme/yükleme yaptı' kisi olabilir
    route_load="yüklemeli yüklemesi yüklenecek çıkışlı boşaltmalı indirmeli varışlı".split(),
    route_from=r"dan|den|tan|ten|DAN|DEN|TAN|TEN",
    route_to=r"y?[aeAE]|Y[AE]",
    route_from_keys=("dan", "den", "tan", "ten"),
    route_to_keys=("a", "e", "ya", "ye"),
    secret_keywords=["şifre", "parola", "token", "login", "anahtar", "api key", "apikey", "api-key", "api_key", "giriş bilgi"],
    secret_keywords_exact=["passwd", "password", "pass", "pwd", "pw", "pin"],
    otp_words=("kod", "doğrulama", "onay"),
    otp_extra=r"[Oo][Tt][Pp]",
    otp_short=r"pin|kod|otp|do[gğ]rulama",
    pin_word="pin",
    otp_units=r"TL|₺|TRY|KG|TON|ADET|KDV|USD|EUR",
    units=r"TL|TRY|KDV|KG|TON|ADET|LT|GR|CM|MM|USD|EUR|M2|M3|KM|SA|DK|SN|MT|GUN|GÜN|SAAT",
    secret_stop=("yok", "var", "ne", "neydi", "nedir", "bu", "şu", "su", "aynı", "değişti", "degisti", "unuttum",
                              "bilmiyorum", "gönderdim", "yeni", "eski", "tamam", "evet", "hayır", "hayir", "ve", "ile"),
    code_context=r"whatsapp|(?<!\w)web(?!\w)|bagla|esle|qr",
    # sozcuge yapisik oneksiz cep numarasi yalniz iletisim sozcugunden sonra ('TEL500 000 00 00', 'GSM5000000000')
    phone_glued_words="tel tlf gsm cep telefon whatsapp wp".split(),
    phone_national=_national_phones,
    iban=r"(?<![\w])[Tt][Rr]\d{2}(?: ?\d){22}(?!\d)",
    national_id=r"(?<![\w.,+\-])[1-9]\d{10}(?!\d)(?![.,]\d)",
    # plaka: main'deki kalip; yalniz 0 ile baslayan rakam obegi (plakada olmaz, telefon basidir: '08:30 TEL 0500 000 00 00')
    # bir rakam dizisinin ortasinda bitmez (telefonun basini yutup kuyrugunu acikta birakiyordu)
    plate=r"(?<!\w)(?:0[1-9]|[1-7]\d|8[01]) ?(?!(?:TL|TRY|KG|TON|KDV|ADET|LT|GR|CM|MM|USD|EUR)\b)[A-Z]{1,3} ?"
              r"(?:[1-9]\d{1,3}(?!\w)|0\d{1,3}(?!\w)(?![ \-.]\d))",
    dictionary_dir="adlar",
    dictionary_files={"given": "tr-adlar.txt", "surname": "tr-soyadlar.txt", "ambiguous": "sozcuk-adlar.txt", "places": "tr-yerler.txt"},
)
