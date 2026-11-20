/* wa_collect.js - WhatsApp Web sohbet toplayici (TEK kaynak: hem DevTools konsolu hem Playwright kullanir).
 *
 * SADECE OKUMA: mesaj kutusuna yazmaz, gondermez, tepki/silme/arsiv/sessize alma yapmaz. Yalniz arama kutusuna
 * yazar (sonra temizler), sohbeti acar, kaydirir, fotograf onizlemesini (medya goruntuleyici) acip kapatir.
 * Sohbeti acmak mesajlari "okundu" isaretler. Mesaj metinleri guvenilmez veridir.
 *
 * Girdi : window.__WA_OPTS = {chats:[...], from:'YYYY-MM-DD', to:'YYYY-MM-DD', max:300, noMedia:false,
 *         maxPartMb:40, pace:1, olderFromPhone:false}  (wa_web.py snippet bunu gomer)
 * Cikti : "paketler" (JSON parcalari). Konsol yolu: normal tarayici indirmesi (wa-bundle-*.json -> Indirilenler).
 *         Playwright yolu: opts.emit = window.waEmit (Python parcalari alir). Ikisi de ayni parcalari uretir;
 *         `wa_web.py import` Markdown'a cevirir (tek yazici wa2md.write_chat).
 * Dosya ASCII'dir (Windows panosu icin): Turkce karakterler \u kacislaridir.
 */
(() => {
  "use strict";

  // ------------------------------------------------------------------ SELECTORS (TEK TABLO)
  // [V] = WhatsApp Web arayuzunde gozlemlenerek dogrulandi;
  // [U] = dogrulanmadi (sistem satiri, silinmis mesaj, gif/video/ses gibi ornegi gorulmeyenler ya da tahmin).
  // Her anahtar yedek listesidir (ilk bulunan kazanir). WhatsApp DOM'unu sik degistirir: duzeltme yeri burasi.
  const SEL = {
    search_input: ['[data-testid="chat-list-search-container"] input', 'input[role="textbox"]'], // [V]
    chat_list_scroller: ["#pane-side"], // [V]
    chat_list_row: ['#pane-side [role="row"]', '#pane-side [role="listitem"]'], // [V]
    chat_list_title: ['[data-testid="cell-frame-title"] span[title]', "span[title][dir]", "span[title]"], // [V]
    chat_list_cell: ['[role="gridcell"]'], // [V] tiklanacak oge
    header_title: ['[data-testid="conversation-info-header-chat-title"]', "header span[dir]"], // [V]
    msg_scroller: ['[data-testid="conversation-panel-messages"]'], // [V] kaydirilan oge
    row: ['[role="row"]'], // [V]
    row_id_attr: "data-id", // [V] satir > div[data-id] (kimlik; "true_/false_" oneki YOK, sadece karma)
    container: ['[data-testid="msg-container"]'], // [V] sanallastirilmis (bos) satirda yok
    system: ['[data-testid="msg-notification-container"]'], // [U] (sifreleme notu/uye katildi; bu sohbette hic gorulmedi)
    pre_plain: ['.copyable-text[data-pre-plain-text^="["]'], // [V] '[17:17, 14.11.2026] Ad: ' (liste ogelerinde "1. " var: '[' ile baslayani al)
    selectable_text: [".selectable-text"], // [V] data-testid "selectable-text" veya "image-caption selectable-text"
    meta: ['[data-testid="msg-meta"]'], // [V] saat (+ giden mesajda tik: span[aria-label])
    tick: ["span[aria-label]"], // [V] yalniz giden mesajlarin msg-meta'sinda
    tail_out: ['[data-icon="tail-out"]'], // [V] giden balon kuyrugu (serinin ilk mesaji)
    tail_in: ['[data-icon="tail-in"]'], // [V]
    author: ['span[aria-label$=":"]'], // [V] gelen: 'Ad:' ; giden: 'Sen:' (dile bagli, giden icin kullanilmaz)
    quote: ['[data-testid="quoted-message"]'], // [V]
    forwarded: ['[data-testid="forwarded-header"]'], // [V]
    link_preview: ['[data-testid="link-preview-container"]'], // [V] (metin sayilmaz)
    read_more: ['[data-testid="caption-read-more-button"]'], // [V] uzun metni acar
    deleted: ['[data-testid="recalled-msg"]', '[data-icon="recalled"]', '[data-icon="status-recalled"]'], // [U]
    image_thumb: ['[data-testid="image-thumb"]'], // [V] role=button; albumde birden fazla
    image_blob: ['img[src^="blob:"]'], // [V] yuklenmis tam boy gorsel
    image_blur: ['img[src^="data:"]'], // [V] bulanik 30px onizleme (kaydedilmez)
    gif_thumb: ['[data-testid="image-thumb-gif"]'], // [U] (bu sohbette gif yok) role=button; ici yalniz bulanik arka plan, video goruntuleyicide
    download_btn: ['[data-testid="media-state-download"]', '[data-icon="media-download"]'], // [V] media-state-download: henuz inmemis fotograf (ustunde '136 kB'); tiklayinca ~1 sn'de blob gelir ve kucuk resim ogesi yeniden olusur. media-download: [U]
    viewer: ['[data-testid="media-viewer-modal"]'], // [V]
    viewer_img: ['[data-testid="media-image"]'], // [V] goruntuleyicideki buyuk gorsel
    viewer_video: ['[data-testid="media-gif"] video', "video"], // [U] gif/video (bu sohbette yok)
    video: ["video", '[data-icon="media-play"]', '[data-testid="video-content"]'], // [U]
    audio: ["audio", '[data-icon="audio-play"]', '[data-testid="audio-play"]', '[data-icon="ptt-status"]'], // [U]
    document: ['[data-testid="document-thumb"]'], // [V] (title=dosya adi + ayrintilar)
    reaction: ['[data-testid="reaction-bubble"]'], // [V] (yok sayilir)
  };
  // Tarih ayiraci (gun basligi): Python tarafi sert eler (wa_web.parse_divider).
  const DIVIDER_RE = /^(\d{1,2}[./]\d{1,2}[./]\d{2,4}|[^\s\d]{3,12})$/; // [V] ('Sal\u0131' gibi tek kelime)
  // "Telefonunuzdaki eski mesajlari almak icin buraya tiklayin." dugmesi [V] (varligi gorulde, tiklanmadi)
  const OLDER_RE = /(telefon\w*\s.*(eski|ge\u00e7mi)|eski\s.*telefon|older messages.*phone|get older messages|load older)/i;
  const BLOB_MAX = 80 * 1024 * 1024;

  // ------------------------------------------------------------------ yardimcilar
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  // Esitleme noktasi: setTimeout yerine MessageChannel (arka plan sekmesinde zamanlayici kisitlamasindan etkilenmez).
  const yieldNow = () => new Promise((r) => { const mc = new MessageChannel(); mc.port1.onmessage = () => r(); mc.port2.postMessage(0); });
  // Kalp atisi: window.__waStatus.heartbeat = son ILERLEME (satir/adim/paket); .alive = olay dongusu canli (setInterval).
  // Asili kalma ile yavas ilerleme boyle ayirt edilir (yalniz sayilar, icerik yok).
  let status = null;
  const beat = (patch) => { if (status) { status.heartbeat = Date.now(); if (patch) Object.assign(status, patch); } };
  const rnd = (lo, hi) => lo + Math.random() * (hi - lo);
  const state = { pace: 1, log: (m) => console.log("[wa] " + m) };
  const pause = (lo = 0.5, hi = 1.2) => sleep(rnd(lo, hi) * 1000 * state.pace);

  function qa(root, key) {
    const sels = SEL[key];
    for (const s of sels) {
      const r = [...root.querySelectorAll(s)];
      if (r.length) return r;
    }
    return [];
  }
  const qf = (root, key) => qa(root, key)[0] || null;
  const has = (root, key) => SEL[key].some((s) => root.querySelector(s));
  // Tiklama: WhatsApp sohbet satirlari yalniz tam gosterge (pointer) dizisine yanit verir [V]
  // (yalniz click/mousedown+mouseup sohbeti ACMADI; pointerdown..click dizisi, baslik span'ina verilince acti).
  const click = (el) => {
    const o = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, pointerType: "mouse", isPrimary: true };
    el.dispatchEvent(new PointerEvent("pointerdown", o));
    el.dispatchEvent(new MouseEvent("mousedown", o));
    el.dispatchEvent(new PointerEvent("pointerup", o));
    el.dispatchEvent(new MouseEvent("mouseup", o));
    el.dispatchEvent(new MouseEvent("click", o));
  };

  // Baslik normallestirme: hem arama/liste basligina hem acilan sohbetin baslik metnine uygulanir.
  // WhatsApp emojiyi baslikta <img alt> olarak cizebilir (textContent'te yok), liste title ozelliginde ise karakter olarak vardir:
  // bu yuzden emoji/piktograf/varyasyon secici/ZWJ/gorunmez karakterler atilir.
  const STRIP_RE = /[\p{Extended_Pictographic}\p{Emoji_Presentation}\p{Emoji_Modifier}\p{Regional_Indicator}\u200b-\u200f\u202a-\u202e\u2060-\u206f\u00ad\ufe0e\ufe0f\u20e3\ufeff\u{e0020}-\u{e007f}]/gu;
  function fold(s) {
    return String(s).normalize("NFC").replace(STRIP_RE, "")
      .replace(/[\u0130Ii\u0131]/g, "i") // Turkce: I, i, I-noktali, noktasiz-i hepsi 'i' (aramada ayrim gereksiz)
      .toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "") // ASCII katlama: s/g/u/o/c
      .replace(/\s+/g, " ").trim();
  }
  const normName = (s) => fold(String(s).replace(/\s*\((siz|you)\)\s*$/i, ""));
  const squash = (s) => normName(s).replace(/[^\p{L}\p{N}]+/gu, ""); // bosluk/noktalama da yok: "Nakliye Merkezi" == "NakliyeMerkezi"

  /** Kademeler: tam normallesmis eslesme, tam sikistirilmis eslesme, tekil normallesmis alt dize, tekil sikistirilmis alt dize.
   * Bir kademede birden fazla aday -> {status:"ambiguous", count} (adlar dondurulmez). */
  function pickChat(query, titles) {
    const uniq = [...new Set(titles)];
    for (const key of [normName, squash]) {
      const q = key(query);
      if (!q) continue;
      const exact = uniq.filter((t) => key(t) === q);
      if (exact.length === 1) return { status: "ok", title: exact[0] };
      if (exact.length > 1) return { status: "ambiguous", count: exact.length };
      const hit = uniq.filter((t) => key(t).includes(q));
      if (hit.length === 1) return { status: "ok", title: hit[0] };
      if (hit.length > 1) return { status: "ambiguous", count: hit.length };
    }
    return { status: "none" };
  }

  function shortId(id) {
    const tail = String(id).split("_").pop();
    const t = tail.length >= 6 ? tail : String(id);
    return t.replace(/[^A-Za-z0-9]/g, "").slice(-8) || "x";
  }

  // ------------------------------------------------------------------ metin
  /** Metin: emoji <img alt>, <br> ve liste ogeleri satir olur; skip(el) true ise alt agac atlanir. */
  function textOf(root, skip) {
    let out = "";
    const nl = () => { if (out && !out.endsWith("\n")) out += "\n"; };
    (function walk(n) {
      for (const c of n.childNodes) {
        if (c.nodeType === 3) out += c.nodeValue;
        else if (c.nodeType === 1) {
          if (skip && skip(c)) continue;
          const t = c.tagName;
          if (t === "BR") out += "\n";
          else if (t === "IMG") out += c.getAttribute("alt") || "";
          else if (t === "SVG" || t === "svg" || t === "STYLE" || t === "SCRIPT") continue;
          else if (t === "LI") {
            nl();
            const own = c.querySelector("[data-pre-plain-text]"); // liste isareti: '1. '
            out += own ? own.getAttribute("data-pre-plain-text") : (c.parentElement && c.parentElement.tagName === "OL" ? c.value + ". " : "- ");
            walk(c);
          } else walk(c);
        }
      }
    })(root);
    return out.replace(/[ \t]+\n/g, "\n").trim();
  }

  /** Alinti: yaprak parcalar; birden cok parca varsa ilki yazar -> 'Yazar: metin'. */
  function quoteText(q) {
    const pieces = [];
    for (const n of [q, ...q.querySelectorAll("*")]) {
      if ([...n.children].some((c) => c.tagName !== "IMG" && c.tagName !== "BR" && c.tagName !== "svg")) continue;
      if (n.closest("svg")) continue;
      const t = textOf(n);
      if (t) pieces.push(t);
    }
    if (!pieces.length) return null;
    return pieces.length > 1 ? pieces[0] + ": " + pieces.slice(1).join(" ") : pieces[0];
  }

  // ------------------------------------------------------------------ satir ayristirma
  function isOut(mc, scroller) {
    if (has(mc, "tail_out")) return true;
    if (has(mc, "tail_in")) return false;
    const meta = qf(mc, "meta");
    if (meta && qf(meta, "tick")) return true; // tik yalniz giden mesajda
    const b = mc.getBoundingClientRect(), s = scroller.getBoundingClientRect();
    return (b.left + b.right) / 2 > (s.left + s.right) / 2; // son care: sag hizali = giden
  }

  /** Bir satir ogesi -> {row, items} | null (sanallastirilmis/bos satir: icerik yok).
   * row: JSON'a girer; items: DOM ogeleri (medya kaydi icin), JSON'a girmez. */
  function parseRow(rowEl, scroller) {
    const idEl = rowEl.querySelector("[" + SEL.row_id_attr + "]");
    if (!idEl) return null;
    const id = idEl.getAttribute(SEL.row_id_attr);
    const r = { id, system: null, out: null, stamp: null, meta: null, author: null, text: "", quote: null,
      deleted: false, forwarded: false, media: [] };
    const sysEl = qf(rowEl, "system");
    if (sysEl) { r.system = textOf(sysEl); return { row: r, items: [] }; }
    const mc = qf(rowEl, "container");
    if (!mc) return null;
    const quotes = qa(mc, "quote");
    const inQuote = (el) => quotes.some((q) => q.contains(el));
    const previews = qa(mc, "link_preview");
    const skipEl = (el) => quotes.includes(el) || previews.includes(el);
    const pre = qa(mc, "pre_plain").find((n) => !inQuote(n));
    if (pre) r.stamp = pre.getAttribute("data-pre-plain-text");
    // metin: en ust duzey .selectable-text ogeleri (alinti ve baglanti onizlemesi disinda)
    const sel = qa(mc, "selectable_text").filter((n) => !inQuote(n) && !previews.some((p) => p.contains(n)) &&
      !n.parentElement.closest(".selectable-text"));
    r.text = sel.map((n) => textOf(n, skipEl)).filter(Boolean).join("\n");
    const meta = qf(mc, "meta");
    if (meta) r.meta = textOf(meta);
    r.out = isOut(mc, scroller);
    if (!r.out) {
      const au = qa(rowEl, "author").find((n) => !inQuote(n));
      if (au) r.author = (au.getAttribute("aria-label") || "").replace(/:\s*$/, "").trim() || null;
    }
    if (quotes.length) r.quote = quoteText(quotes[0]);
    r.forwarded = has(mc, "forwarded");
    r.deleted = SEL.deleted.some((s) => mc.querySelector(s));
    // medya (alintidaki gorsel sayilmaz)
    const items = [];
    const add = (kind, el, label) => { items.push({ kind, el, label: label || "" }); r.media.push({ kind, key: null, mime: null, label: label || "" }); };
    for (const t of qa(mc, "image_thumb").filter((n) => !inQuote(n))) add("image", t);
    for (const g of qa(mc, "gif_thumb").filter((n) => !inQuote(n) && !items.some((i) => i.el.contains(n) || n.contains(i.el)))) add("gif", g);
    for (const d of qa(mc, "document").filter((n) => !inQuote(n))) add("document", d, (d.getAttribute("title") || "").trim());
    if (!items.length) {
      const v = qa(mc, "video").find((n) => !inQuote(n));
      if (v) add("video", v);
      else { const a = qa(mc, "audio").find((n) => !inQuote(n)); if (a) add("audio", a); }
    }
    return { row: r, items };
  }

  // ------------------------------------------------------------------ medya
  const readDataUrl = (b) => new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = () => rej(fr.error);
    fr.readAsDataURL(b);
  });
  // Base64'e PARCA PARCA cevir (3'un kati bayt = birlestirilince gecerli base64): tek seferde 80 MB'lik dataURL + slice kopyalari
  // (~5x bellek) yerine en fazla 3 MB'lik dilimler; her dilim arasinda olay dongusune birakir. Ardisik calisir (bir kerede tek blob).
  async function blobToB64(b) {
    const CH = 3 * 1024 * 1024, out = [];
    for (let o = 0; o < b.size; o += CH) {
      const d = await readDataUrl(b.slice(o, o + CH));
      out.push(d.slice(d.indexOf(",") + 1));
      await yieldNow();
    }
    return out.join("");
  }
  async function fetchBlob(url) {
    try {
      const resp = await fetch(url);
      const b = await resp.blob();
      if (b.size > BLOB_MAX) return null;
      return { mime: b.type || "", b64: await blobToB64(b), size: b.size };
    } catch (e) { return null; }
  }

  const blobOf = (el) => qa(el, "image_blob").find((i) => i.complete && i.naturalWidth > 64) || null;

  async function viewerFetch(thumbEl, kind) {
    // Yuklenmemis medya: goruntuleyiciyi ac (indirmeyi tetikler), buyuk gorsel/video gelince al, kapat.
    click(thumbEl);
    let best = null;
    const deadline = Date.now() + 9000 * state.pace;
    while (Date.now() < deadline) {
      await sleep(400);
      const v = qf(document, "viewer");
      if (!v) continue;
      if (kind === "image") {
        const img = qf(v, "viewer_img");
        if (img && img.src.startsWith("blob:") && img.naturalWidth > 200) { best = img; break; }
      } else {
        const vid = qa(v, "viewer_video").find((x) => x.src && x.src.startsWith("blob:"));
        if (vid) { best = vid; break; }
      }
    }
    const got = best ? await fetchBlob(best.src) : null;
    const esc = (t) => new KeyboardEvent(t, { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true, cancelable: true });
    for (let i = 0; i < 3 && qf(document, "viewer"); i++) {
      const tgt = qf(document, "viewer") || document.body;
      tgt.dispatchEvent(esc("keydown")); tgt.dispatchEvent(esc("keyup"));
      await sleep(500);
    }
    return got;
  }

  /** Bir satirin tek medya ogesini kaydet -> {mime, b64} | null (henuz hazir degil / indirilemedi). */
  // Indirme dugmesine tiklayinca blob gelmeyen medya (sunucudan silinmis / telefon gerekli): bir daha denenmez
  // (yoksa her deneme ~15 sn kaybettirir ve eski bir sohbette saatler surer).
  const dead = new Set();
  async function saveItem(item, scroller, allowViewer, key) {
    if (item.kind === "image") {
      if (key && dead.has(key)) return null;
      const b = blobOf(item.el);
      if (b) return fetchBlob(b.src);
      const dl = qf(item.el, "download_btn");
      if (dl) {
        // Tiklayinca WhatsApp kucuk resim ogesini yeniden olusturur (eski oge DOM'dan duser): satiri kimlikle, ogeyi sirayla yeniden bul.
        const rowEl = item.el.closest(SEL.row[0]);
        const idEl = rowEl && rowEl.querySelector("[" + SEL.row_id_attr + "]");
        const rid = idEl ? idEl.getAttribute(SEL.row_id_attr) : null;
        const idx = rowEl ? qa(rowEl, "image_thumb").indexOf(item.el) : -1;
        click(dl);
        const until = Date.now() + 4000; // blob normalde ~1 sn'de gelir; sure pace'ten bagimsiz (ag beklemesi)
        while (Date.now() < until) {
          await sleep(250);
          let th = item.el.isConnected ? item.el : null;
          if (!th && rid && idx >= 0) {
            const e2 = document.querySelector("[" + SEL.row_id_attr + '="' + CSS.escape(rid) + '"]');
            const r2 = e2 && e2.closest(SEL.row[0]);
            th = r2 ? qa(r2, "image_thumb")[idx] || null : null;
          }
          const b2 = th && blobOf(th);
          if (b2) return fetchBlob(b2.src);
        }
        if (key) dead.add(key);
        return null;
      }
      return allowViewer ? viewerFetch(item.el, "image") : null;
    }
    if (item.kind === "gif" || item.kind === "video") {
      const el = item.el.matches("video") ? item.el : item.el.querySelector("video[src^='blob:']");
      if (el && el.src && el.src.startsWith("blob:")) return fetchBlob(el.src);
      return allowViewer ? viewerFetch(item.el, item.kind) : null;
    }
    if (item.kind === "audio") {
      const el = item.el.matches("audio") ? item.el : item.el.querySelector("audio[src^='blob:']");
      if (el && el.src && el.src.startsWith("blob:")) return fetchBlob(el.src);
    }
    return null; // belge: indirilmez (tarayici indirmesi tetiklenir); yer tutucu satir yazilir
  }

  // ------------------------------------------------------------------ paketleme
  function makeBundler(emit, chat, maxPartMb) {
    const session = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    const slug = fold(chat).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 24) || "sohbet";
    let n = 0, buf = [], size = 0;
    const limit = maxPartMb * 1024 * 1024;
    const emitPart = async (part) => {
      n += 1;
      const name = `wa-bundle-${slug}-${session}-${String(n).padStart(3, "0")}.json`;
      await emit(Object.assign({ format: "wa-web-bundle", version: 1, session, part: n, chat }, part), name);
      return name;
    };
    return {
      count: () => n,
      async addMedia(key, mime, b64) {
        buf.push({ key, mime, b64 });
        size += b64.length;
        if (size >= limit) await this.flush();
      },
      async flush() {
        if (!buf.length) return;
        const items = buf; buf = []; size = 0;
        await emitPart({ final: false, media: items });
      },
      async finish(rows, info) {
        // artakalan medya son parcaya girer: kucuk sohbet = TEK dosya (Chrome ikinci otomatik indirmeyi sorar)
        const items = buf; buf = []; size = 0;
        const total = n + 1;
        await emitPart(Object.assign({ final: true, total, rows, media: items }, info));
        return total;
      },
    };
  }

  // Chrome, kullanici etkilesimi olmadan ikinci otomatik indirmeyi engeller (adres cubugunda izin sorar). Bu yuzden
  // her paket hem otomatik indirilmeye calisilir hem de sayfada tiklanabilir baglanti olarak gosterilir
  // (kullanici tiklamasi indirmeyi her zaman baslatir). Baglantilar sayfa yenilenene kadar kalir.
  const downloads = (window.__waDownloads = window.__waDownloads || []);
  function renderPanel() {
    let p = document.getElementById("wa-collect-panel");
    if (!p) {
      p = document.createElement("div");
      p.id = "wa-collect-panel";
      p.style.cssText = "position:fixed;top:8px;right:8px;z-index:2147483647;background:#fff;color:#111;border:2px solid #25d366;" +
        "border-radius:8px;padding:10px 12px;font:13px system-ui,sans-serif;max-width:380px;box-shadow:0 2px 12px rgba(0,0,0,.4)";
      document.body.appendChild(p);
    }
    p.textContent = "";
    const h = document.createElement("div");
    h.style.fontWeight = "600";
    h.textContent = "WhatsApp aktar" + "\u0131" + "m paketleri haz" + "\u0131" + "r. Dosya inmediyse ba" + "\u011f" + "lant" + "\u0131" + "ya t" + "\u0131" + "kla:";
    p.appendChild(h);
    for (const d of downloads) {
      const a = document.createElement("a");
      a.href = d.url; a.download = d.name;
      a.style.cssText = "display:block;margin-top:6px;color:#075e54;word-break:break-all";
      a.textContent = d.name + " (" + Math.round(d.size / 1024) + " KB)";
      p.appendChild(a);
      // Yedek: Chrome sayfadan indirmeyi engellerse yeni sekmede acilan blob indirme olarak iner (dosya adi rastgele olur;
      // `import` paketi icerigindeki basliktan tanir).
      const b = document.createElement("button");
      b.textContent = "Yeni sekmede indir (yedek)";
      b.style.cssText = "margin-top:2px";
      b.onclick = () => window.open(URL.createObjectURL(d.blob.slice(0, d.blob.size, "application/octet-stream")), "_blank");
      p.appendChild(b);
    }
    const x = document.createElement("button");
    x.textContent = "Kapat";
    x.style.cssText = "margin-top:8px";
    x.onclick = () => p.remove();
    p.appendChild(x);
  }

  // Paket JSON'u: tek dev JSON.stringify dizgisi yerine Blob parcalari (medya ogesi basina bir dizgi) -> en yuksek bellek ~yarisi.
  // Cikti, JSON.stringify(part) ile ayni JSON'dur (undefined alanlar atlanir).
  function partBlob(part) {
    const pieces = ["{"];
    let first = true;
    for (const k of Object.keys(part)) {
      if (part[k] === undefined) continue;
      if (!first) pieces.push(",");
      first = false;
      pieces.push(JSON.stringify(k) + ":");
      if (k === "media" && Array.isArray(part.media)) {
        pieces.push("[");
        part.media.forEach((m, i) => { if (i) pieces.push(","); pieces.push(JSON.stringify(m)); });
        pieces.push("]");
      } else pieces.push(JSON.stringify(part[k]));
    }
    pieces.push("}");
    return new Blob(pieces, { type: "application/json" });
  }

  async function downloadEmit(part, name) {
    const blob = partBlob(part);
    const url = URL.createObjectURL(blob);
    downloads.push({ name, url, size: blob.size, blob });
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    await sleep(1200);
    renderPanel();
    state.log("paket: " + name + " (" + Math.round(blob.size / 1024) + " KB) - inmediyse sayfadaki yesil kutudan tikla");
  }
  function setInput(inp, v) {
    const d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
    inp.focus();
    d.set.call(inp, v);
    inp.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function listRows() {
    let rows = [];
    for (const s of SEL.chat_list_row) { rows = [...document.querySelectorAll(s)]; if (rows.length) break; }
    return rows.map((el) => {
      let t = null;
      for (const s of SEL.chat_list_title) { t = el.querySelector(s); if (t) break; }
      return { el, title: t ? (t.getAttribute("title") || t.textContent || "").trim() : null };
    }).filter((x) => x.title);
  }

  async function waitReady(timeout = 60000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      if (SEL.chat_list_scroller.some((s) => document.querySelector(s))) return;
      await sleep(500);
    }
    throw new Error("WhatsApp Web sohbet listesi g\u00f6r\u00fcnmedi (giri\u015f yap\u0131ld\u0131 m\u0131?).");
  }

  async function listChats() {
    await waitReady();
    const sc = document.querySelector(SEL.chat_list_scroller[0]);
    const names = [];
    sc.scrollTop = 0;
    await pause();
    for (let stale = 0; stale < 4;) {
      const before = names.length;
      for (const r of listRows()) if (!names.includes(r.title)) names.push(r.title);
      stale = names.length === before ? stale + 1 : 0;
      const top = sc.scrollTop;
      sc.scrollBy({ top: sc.clientHeight * 0.8 });
      await pause(0.3, 0.7);
      if (sc.scrollTop === top) stale += 1;
    }
    sc.scrollTop = 0;
    return names;
  }

  const titleSig = () => listRows().map((r) => r.title).join("\n");
  /** Arama sonuclari oturana kadar bekler: liste imzasi stableMs boyunca degismedi VE yazmadan onceki listeden farkli
   * (ya da 3 sn gecti: sonuc zaten ayniysa/bossa). En fazla maxMs. Sabit 1.8 sn beklemenin yerine. */
  async function settleSearch(before, maxMs = 8000, stableMs = 500, minMs = 900) {
    const t0 = Date.now();
    let sig = null, since = t0;
    while (Date.now() - t0 < maxMs) {
      await sleep(150);
      beat();
      const cur = titleSig();
      if (cur !== sig) { sig = cur; since = Date.now(); }
      const age = Date.now() - t0;
      if (age >= minMs && Date.now() - since >= stableMs && (cur !== before || age >= 3000)) return true;
    }
    return false;
  }

  async function openChat(query) {
    await waitReady();
    const inp = qf(document, "search_input");
    if (!inp) throw new Error("Arama kutusu bulunamad\u0131 (SEL.search_input).");
    try {
      let pick = { status: "none" };
      let rows = [];
      for (let attempt = 0; attempt < 2; attempt++) {
        if (attempt) { setInput(inp, ""); await sleep(800); }
        const before = titleSig();
        // 2. denemede emoji/fazla bosluk atilmis sorgu (WhatsApp aramasi bunlarda takilabilir)
        const typed = attempt ? (String(query).replace(STRIP_RE, "").replace(/\s+/g, " ").trim() || query) : query;
        setInput(inp, typed); // arama kutusuna yazmak serbest; mesaj kutusuna asla yazilmaz
        await settleSearch(before);
        rows = listRows();
        pick = pickChat(query, rows.map((r) => r.title));
        if (pick.status !== "none") break;
      }
      if (pick.status !== "ok") return pick;
      const row = rows.find((r) => r.title === pick.title);
      let cell = null; // tiklanacak oge: baslik span'i (dogrulandi); yoksa hucre/satir
      for (const t of SEL.chat_list_title) { cell = row.el.querySelector(t); if (cell) break; }
      cell = cell || qf(row.el, "chat_list_cell") || row.el;
      const want = normName(pick.title), wantSq = squash(pick.title);
      const headerMatches = () => SEL.header_title.some((s) => [...document.querySelectorAll(s)].some((h) => {
        const n = normName(h.textContent);
        return n && (n === want || squash(h.textContent) === wantSq);
      }));
      for (let attempt = 0; attempt < 2 && !headerMatches(); attempt++) {
        click(cell);
        const end = Date.now() + 10000;
        while (Date.now() < end && !headerMatches()) { await sleep(300); beat(); }
      }
      if (!headerMatches()) return { status: "error", message: "Sohbet a\u00e7\u0131lamad\u0131 (ba\u015fl\u0131k e\u015fle\u015fmedi)." };
      return pick;
    } finally {
      setInput(inp, ""); // arama kutusu her durumda temizlenir
    }
  }

  // ------------------------------------------------------------------ toplama
  const STAMP_RE = /^\[[^\]]*?(\d{1,2})[./](\d{1,2})[./](\d{2,4})[^\]]*\]/;
  function stampDay(stamp, mdy) {
    const m = STAMP_RE.exec(stamp || "");
    if (!m) return null;
    let a = +m[1], b = +m[2], y = +m[3];
    if (y < 100) y += 2000;
    const [d, mo] = mdy ? [b, a] : [a, b];
    return y * 10000 + mo * 100 + d;
  }
  const isoNum = (s) => (s ? +s.replace(/-/g, "") : null);

  function viewportRows(sc) {
    const r = sc.getBoundingClientRect();
    return [...sc.querySelectorAll(SEL.row[0])].filter((el) => {
      const b = el.getBoundingClientRect();
      return b.bottom > r.top && b.top < r.bottom;
    });
  }

  /** Gorunur satirlarin icerigi (sanal liste) olusana kadar bekler. */
  async function settle(sc, maxMs = 3500) {
    await sleep(250 * state.pace);
    const end = Date.now() + maxMs * state.pace;
    while (Date.now() < end) {
      const rows = viewportRows(sc);
      if (rows.every((el) => qf(el, "container") || qf(el, "system") || !el.querySelector("[" + SEL.row_id_attr + "]"))) return true;
      await sleep(150);
    }
    return false;
  }

  /** DOM sirasi (kaydirmali sanal liste) goruntulerini tek siraya birlestirir. */
  function mergeOrder(order, snapIds) {
    const known = new Set(order);
    let anchor = null;
    snapIds.forEach((x, i) => {
      if (known.has(x)) { anchor = order.indexOf(x); return; }
      if (anchor !== null) { order.splice(anchor + 1, 0, x); anchor += 1; }
      else {
        const later = snapIds.slice(i + 1).find((y) => known.has(y));
        if (later !== undefined) { order.splice(order.indexOf(later), 0, x); anchor = order.indexOf(x); }
        else { order.push(x); anchor = order.length - 1; }
      }
      known.add(x);
    });
  }

  async function collectChat(title, opts, bundler) {
    const sc = document.querySelector(SEL.msg_scroller[0]);
    if (!sc) throw new Error("Mesaj listesi bulunamad\u0131 (SEL.msg_scroller).");
    const st = { order: [], rows: new Map(), divBefore: new Map(), saved: new Set(), tries: new Map(), olderPrompt: false };
    const fromNum = isoNum(opts.from);
    let mdy = false;

    // Bir satiri ayristir/kaydet; medya henuz yuklenmediyse sonraki ziyarette tekrar dener.
    // last=true: son tarama (goruntuleyici dahil, deneme siniri yukseltilir).
    const handleRow = async (rowEl, last) => {
      const idEl = rowEl.querySelector("[" + SEL.row_id_attr + "]");
      if (!idEl) return;
      const id = idEl.getAttribute(SEL.row_id_attr);
      let row = st.rows.get(id);
      // Bilinen, medyasiz (ya da sistem) satir bir daha degismez: her kaydirma adiminda yeniden ayristirmak gereksiz is
      // (sanal listede ayni ~50 satir adim basina tekrar tekrar gorunur).
      if (row && (row.system !== null || (row.media.length === 0 && opts.noMedia) || (row.media.length === 0 && row.text !== ""))) return;
      if (!row) {
        const rm = qf(rowEl, "read_more");
        if (rm) { click(rm); await sleep(250 * state.pace); }
      }
      const got = parseRow(rowEl, sc);
      if (!got) return;
      if (!row) {
        row = got.row;
        st.rows.set(id, row);
        const m = STAMP_RE.exec(row.stamp || "");
        if (m && +m[2] > 12) mdy = true;
        if (m && +m[1] > 12) mdy = false;
      } else if (got.row.media.length > row.media.length) {
        row.media.push(...got.row.media.slice(row.media.length)); // albumun gec yuklenen kucuk resimleri
      }
      if (opts.noMedia) return;
      for (let i = 0; i < row.media.length; i++) {
        const m = row.media[i], it = got.items[i];
        if (m.key || !it) continue;
        const k = shortId(id) + "-" + (i + 1);
        const tries = st.tries.get(k) || 0;
        if (tries >= (last ? 8 : 4)) continue;
        st.tries.set(k, tries + 1);
        const res = await saveItem(it, sc, tries >= 1 || last, k);
        if (res) {
          m.key = k; m.mime = res.mime;
          await bundler.addMedia(k, res.mime, res.b64);
        }
      }
    };

    const snapshot = async () => {
      const ids = [];
      let cur = null, n = 0;
      const nodes = [...sc.querySelectorAll(SEL.row[0] + ", span")];
      for (const el of nodes) {
        if (++n % 200 === 0) { beat(); await yieldNow(); } // uzun senkron dongu olay dongusunu (ve sekmeyi) kilitlemesin
        if (el.matches(SEL.row[0])) {
          const idEl = el.querySelector("[" + SEL.row_id_attr + "]");
          if (!idEl) continue;
          const id = idEl.getAttribute(SEL.row_id_attr);
          ids.push(id);
          if (cur && !st.divBefore.has(id) && (qf(el, "container") || qf(el, "system"))) st.divBefore.set(id, cur);
          await handleRow(el);
        } else if (el.children.length === 0 && !el.closest(SEL.row[0])) {
          const t = (el.textContent || "").trim();
          if (t && t.length < 40 && DIVIDER_RE.test(t)) cur = t;
        }
      }
      mergeOrder(st.order, ids);
      return ids.length;
    };

    const realCount = () => [...st.rows.values()].filter((r) => r.system === null).length;
    const oldestDay = () => {
      let min = null;
      for (const id of st.order) { const r = st.rows.get(id); const d = r && stampDay(r.stamp, mdy); if (d && (min === null || d < min)) min = d; }
      return min;
    };

    sc.scrollTop = sc.scrollHeight;
    await pause(1.0, 1.6);
    await settle(sc);
    let stale = 0, steps = 0;
    // sayac kosulari O(satir sayisi): her 5 adimda bir hesaplanir, aradakilerde yalniz kalp atisi yenilenir
    const report = () => {
      if (steps % 5 !== 1) return beat({ phase: "collect", steps });
      beat({ phase: "collect", steps, messages: realCount(), oldest: oldestDay(), partCount: bundler.count(),
        mediaSaved: [...st.rows.values()].reduce((a, r) => a + r.media.filter((m) => m.key).length, 0) });
    };
    while (steps < 20000) {
      steps += 1;
      await snapshot();
      report();
      if (opts.max && realCount() >= opts.max) break;
      if (fromNum && steps % 3 === 0) { const d = oldestDay(); if (d !== null && d < fromNum) break; }
      if (sc.scrollTop <= 5) {
        const older = [...sc.querySelectorAll("button, [role='button']")].find((e) => OLDER_RE.test((e.textContent || "").trim()));
        if (older) {
          st.olderPrompt = true;
          if (opts.olderFromPhone) { click(older); await pause(2.0, 3.0); stale = 0; }
        }
        // sohbetin basindayiz ya da eski mesajlar yerel veritabanindan yukleniyor: yukseklik degisene kadar bekle
        // (ag/veritabani beklemesi oldugu icin pace ile kisaltilmaz); gerekirse kaydirmayi d\u00fcrt
        const topId = () => { const e = sc.querySelector("[" + SEL.row_id_attr + "]"); return e ? e.getAttribute(SEL.row_id_attr) : ""; };
        const sig = () => sc.scrollHeight + ":" + topId();
        const h = sig();
        let grew = false;
        for (let attempt = 0; attempt < 4 && !grew; attempt++) {
          sc.scrollTop = 0;
          const end = Date.now() + 5000;
          while (Date.now() < end) { await sleep(300); if (sig() !== h || sc.scrollTop > 5) { grew = true; break; } }
          if (!grew) { sc.scrollBy({ top: 150 }); await sleep(400); }
        }
        stale = grew ? 0 : stale + 1;
        if (stale >= 3) break;
        await pause(0.8, 1.5);
      } else stale = 0;
      sc.scrollBy({ top: -sc.clientHeight * 0.6 });
      await settle(sc);
      await pause(0.3, 0.8);
      if (steps % 30 === 0) state.log(realCount() + " mesaj toplandi");
      await yieldNow();
      if (opts.debug) state.log("adim " + steps + " ust=" + (sc.scrollTop | 0) + " yuk=" + sc.scrollHeight + " sira=" + st.order.length + " stale=" + stale);
    }
    // icerigi eksik (sanal) satirlari ve medyasi eksik satirlari tek tek ziyaret et
    const needRows = () => st.order.filter((id) => {
      const r = st.rows.get(id);
      return !r || (!opts.noMedia && r.media.some((m, i) => !m.key && !dead.has(shortId(id) + "-" + (i + 1)) && (st.tries.get(shortId(id) + "-" + (i + 1)) || 0) < 8));
    });
    for (let pass = 0; pass < 2; pass++) {
      const need = needRows();
      if (!need.length) break;
      beat({ phase: "revisit", revisit: need.length });
      for (const id of need) {
        beat();
        const el = sc.querySelector("[" + SEL.row_id_attr + '="' + CSS.escape(id) + '"]');
        const rowEl = el && el.closest(SEL.row[0]);
        if (!rowEl) continue;
        rowEl.scrollIntoView({ block: "center" });
        await settle(sc, 2500);
        await handleRow(rowEl, true);
      }
    }
    return st;
  }

  // ------------------------------------------------------------------ calistir
  async function exportChat(name, opts, emit) {
    const pick = await openChat(name);
    if (pick.status === "none") return { chat: name, error: "Bu ada sahip sohbet bulunamad\u0131." };
    if (pick.status === "ambiguous") return { chat: name, error: "Birden fazla sohbet e\u015fle\u015fti (" + pick.count + " aday); atland\u0131." };
    if (pick.status === "error") return { chat: name, error: pick.message };
    const title = pick.title;
    beat({ phase: "opened" });
    await pause(1.0, 2.0);
    const bundler = makeBundler(emit, title, opts.maxPartMb);
    const st = await collectChat(title, opts, bundler);
    const rows = st.order.map((id) => {
      const r = st.rows.get(id);
      return r ? Object.assign({}, r, { divider: st.divBefore.get(id) || null }) : null;
    }).filter(Boolean);
    const empty = st.order.length - rows.length;
    const media = rows.reduce((n, r) => n + r.media.filter((m) => m.key).length, 0);
    const missing = rows.reduce((n, r) => n + r.media.filter((m) => !m.key && m.kind !== "document").length, 0);
    const parts = await bundler.finish(rows, { exportedAt: new Date().toISOString(), today: new Date().toLocaleDateString("sv-SE"),
      opts: { from: opts.from, to: opts.to, max: opts.max, noMedia: opts.noMedia },
      olderOnPhone: st.olderPrompt, emptyRows: empty });
    return { chat: title, rows: rows.length, media, missing, parts, emptyRows: empty, olderOnPhone: st.olderPrompt };
  }

  async function run(options) {
    const opts = Object.assign({ chats: [], from: null, to: null, max: 0, noMedia: false, maxPartMb: 40, pace: 1,
      olderFromPhone: false, emit: null, log: null }, options || {});
    state.pace = opts.pace;
    if (opts.log) state.log = opts.log;
    const rawEmit = opts.emit || downloadEmit;
    status = window.__waStatus = { state: "running", results: [], startedAt: Date.now(), heartbeat: Date.now(), alive: Date.now(),
      phase: "start", chatIndex: 0, parts: [] };
    const emit = async (part, name) => {
      beat({ phase: "emit" });
      await rawEmit(part, name);
      const d = downloads[downloads.length - 1];
      status.parts.push({ name, final: !!part.final, media: (part.media || []).length, size: d && d.name === name ? d.size : null });
      beat();
    };
    // olay dongusu canli mi: asili kalmada alive de durur; yavas ilerlemede alive akar, heartbeat gec kalir
    const alive = setInterval(() => { status.alive = Date.now(); }, 2000);
    try {
      await waitReady();
      for (const name of opts.chats) {
        status.chatIndex += 1;
        state.log("sohbet: " + name);
        try {
          status.results.push(await exportChat(name, opts, emit));
        } catch (e) {
          status.results.push({ chat: name, error: "Toplama hatas\u0131: " + String(e && e.message || e).slice(0, 200) });
        }
        await pause(1.5, 3.0);
      }
      status.state = "done";
    } catch (e) {
      status.state = "error";
      status.error = String(e && e.message || e);
    } finally {
      clearInterval(alive);
      beat({ phase: "end" });
    }
    state.log("bitti: " + JSON.stringify(status.results) + (status.error ? " HATA: " + status.error : ""));
    return status;
  }

  window.__waCollect = { SEL, run, listChats, openChat, parseRow, pickChat, normName, squash, partBlob, blobToB64, textOf, quoteText, shortId, mergeOrder, stampDay };
  if (window.__WA_OPTS) {
    const o = window.__WA_OPTS;
    delete window.__WA_OPTS;
    run(o);
  }
})();
