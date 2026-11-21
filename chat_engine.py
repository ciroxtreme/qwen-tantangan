import time
import json
import re
import os
import urllib.request
import urllib.parse

JS_DISMISS_ALL_POPUPS = """() => {
    const cookieBtns = document.querySelectorAll('button');
    for (const b of cookieBtns) {
        const txt = (b.innerText || '').toLowerCase();
        if (txt.includes('terima semua cookie') || txt.includes('accept all') || txt.includes('accept cookies') || txt.includes('terima semua')) {
            try { b.click(); } catch(e) {}
        }
    }
    const closeBtns = document.querySelectorAll('.ant-modal-close, .ant-modal-close-x, [aria-label="Close"], button.close, [class*="modal-close"]');
    for (const b of closeBtns) {
        try { b.click(); } catch(e) {}
    }
}"""

JS_CHECK_STREAM_DONE = r"""() => {
    let isGenerating = false;
    const buttons = document.querySelectorAll('button, div[role="button"]');
    for (const b of buttons) {
        const txt = (b.innerText || '').toLowerCase();
        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
        const cls = (b.className || '').toLowerCase();
        if (txt.includes('stop') || aria.includes('stop') || aria.includes('berhenti') || cls.includes('stop') || cls.includes('generating')) {
            isGenerating = true;
            break;
        }
    }
    // Cek juga apakah ada cursor blinking stream atau loading indicator
    const streamIndicators = document.querySelectorAll('.streaming, [class*="cursor"], [class*="loading-dot"], .ant-spin');
    if (streamIndicators.length > 0) {
        isGenerating = true;
    }

    // Hitung panjang jawaban FINAL dengan cara yang SAMA seperti extractor:
    // gabungkan blok-blok jawaban (tanpa duplikasi) di item assistant
    // terakhir. Run #74 membuktikan .markdown-body saja BUTA: selama 900
    // detik answerLen selalu 0 padahal jawaban sudah 75.416 karakter —
    // konten live Qwen berada di elemen [class*="content"], bukan
    // .markdown-body. Akibatnya loop tidak pernah melihat jawaban tumbuh
    // dan selalu mentok di pengaman absolut.
    const THINK_SEL = '[class*="thinking"], [class*="reasoning"], [class*="thought"], [class*="collapse"], [class*="think-"]';
    const isBadEl = (el) => el.closest(THINK_SEL) !== null || el.closest('[class*="user"]') !== null;
    const stripPrefixEl = (t) => (t || '').replace(/^(Berpikir selesai|Thinking completed)\s*/i, '').trim();
    const isGreetingEl = (t) => t.includes('How can I help') || t.includes('Ada yang bisa saya bantu');
    const isThinkingOnlyEl = (t) => /^(thinking|berpikir|memikirkan|menalar|reasoning)[\s.…。]*$/i.test(t)
        || /^(thinking completed|berpikir selesai|pemikiran selesai|thinking done)[\s.…。]*$/i.test(t)
        || /^thought for .+$/i.test(t)
        || /^berpikir selama .+$/i.test(t)
        || (/^(synthesizing|analyzing)\b/i.test(t) && t.length < 200);
    const measureEls = (els) => {
        const top = els.filter(el => !els.some(o => o !== el && o.contains(el)));
        const parts = [];
        for (const el of top) {
            if (isBadEl(el)) continue;
            let t = stripPrefixEl(el.innerText);
            if (!t || t.length <= 5 || isGreetingEl(t) || isThinkingOnlyEl(t)) continue;
            if (parts.some(p => p.includes(t) || t.includes(p))) continue;
            parts.push(t);
        }
        return parts.join('\n\n').length;
    };
    let answerLen = 0;
    const items = document.querySelectorAll('[class*="chat-item-assistant"], [class*="message-assistant"], [class*="assistant-message"]');
    if (items.length > 0) {
        const lastItem = items[items.length - 1];
        const mds = Array.from(lastItem.querySelectorAll('.markdown-body, [class*="markdown"], [class*="content"]'));
        answerLen = measureEls(mds);
    }
    if (answerLen === 0) {
        const allMd = Array.from(document.querySelectorAll('.markdown-body'));
        const valid = allMd.filter(el => !isBadEl(el));
        if (valid.length > 0) {
            let txt = stripPrefixEl(valid[valid.length - 1].innerText);
            if (txt && !isGreetingEl(txt) && !isThinkingOnlyEl(txt)) answerLen = txt.length;
        }
    }

    // Apakah Qwen masih dalam fase thinking? Indikator aktif bisa berbunyi
    // "Thinking..." / "Berpikir..." ATAU berupa kalimat status singkat
    // seperti "Synthesizing core concepts..." (ikon lampu, di bawah bubble
    // user) — run #73 membuktikan Qwen pakai kalimat status, bukan kata
    // "Thinking". Trace yang SUDAH selesai ("Thinking completed",
    // "Thought for 12s") bukan thinking aktif — jangan sampai bikin loop
    // nunggu selamanya. Baris status itu singkat (< 200 karakter).
    let isThinking = false;
    const thinkEls = document.querySelectorAll(THINK_SEL);
    for (const el of thinkEls) {
        const t = (el.innerText || '').trim();
        if (!t || t.length > 200) continue;
        if (/completed|selesai|thought for|berpikir selama/i.test(t)) continue;
        const vis = el.offsetParent !== null || el.getClientRects().length > 0;
        if (!vis) continue;
        if (/thinking\s*(\.{2,}|…)/i.test(t) || /berpikir\s*(\.{2,}|…)/i.test(t)
            || /^(synthesizing|analyzing|reasoning|menalar|menganalisis|menyintesis)\b/i.test(t)) { isThinking = true; break; }
    }
    // Baris status juga bisa berada di luar container thinking (run #73:
    // kalimat "Synthesizing..." keambil extractor dari [class*="content"]).
    // Cek juga elemen konten di item assistant terakhir (pakai `items` yang
    // sudah dihitung di atas).
    if (!isThinking) {
        if (items.length > 0) {
            const lastItem = items[items.length - 1];
            const cands = lastItem.querySelectorAll('[class*="content"], .markdown-body');
            for (const el of cands) {
                const t = (el.innerText || '').trim();
                if (!t || t.length > 200) continue;
                if (/completed|selesai|thought for|berpikir selama/i.test(t)) continue;
                const vis = el.offsetParent !== null || el.getClientRects().length > 0;
                if (!vis) continue;
                if (/^(synthesizing|analyzing|reasoning|menalar|menganalisis|menyintesis)\b/i.test(t)) { isThinking = true; break; }
            }
        }
    }

    // Toast error jaringan ("Network error, reconnecting...") — diagnostik
    // saja, tidak mengubah perilaku loop.
    const bodyTxt = (document.body.innerText || '');
    const hasNetworkError = /network error/i.test(bodyTxt);

    return {
        isGenerating: isGenerating,
        isThinking: isThinking,
        hasNetworkError: hasNetworkError,
        answerLen: answerLen
    };
}"""

JS_EXTRACTOR = r"""() => {
    try {
        const THINK_SEL = '[class*="thinking"], [class*="reasoning"], [class*="thought"], [class*="collapse"], [class*="think-"]';
        const isBad = (el) => el.closest(THINK_SEL) !== null || el.closest('[class*="user"]') !== null;
        const stripPrefix = (t) => (t || '').replace(/^(Berpikir selesai|Thinking completed)\s*/i, '').trim();
        const isGreeting = (t) => t.includes('How can I help') || t.includes('Ada yang bisa saya bantu');
        // "Thinking..." / "Berpikir..." / "Thought for 12s" adalah indikator
        // status, BUKAN jawaban. Kalau ini yang keambil (Qwen masih mikir
        // saat diekstrak), jangan pernah dijadiin jawaban — kembalikan ''.
        const isThinkingOnly = (t) => /^(thinking|berpikir|memikirkan|menalar|reasoning)[\s.…。]*$/i.test(t)
            || /^(thinking completed|berpikir selesai|pemikiran selesai|thinking done)[\s.…。]*$/i.test(t)
            || /^thought for .+$/i.test(t)
            || /^berpikir selama .+$/i.test(t)
            // Baris status fase thinking ("Synthesizing core concepts...")
            // — singkat, bukan jawaban. Hanya filter kalau pendek (< 200).
            || (/^(synthesizing|analyzing)\b/i.test(t) && t.length < 200);

        // Gabungkan blok-blok jawaban TANPA duplikasi:
        //  - buang elemen yang punya ancestor di daftar yang sama (parent +
        //    child punya innerText yang sama -> inilah penyebab jawaban
        //    keulang 6x di versi sebelumnya)
        //  - buang blok yang teksnya sudah tercakup blok lain
        const dedupeJoin = (els) => {
            const top = els.filter(el => !els.some(o => o !== el && o.contains(el)));
            const parts = [];
            for (const el of top) {
                if (isBad(el)) continue;
                let t = stripPrefix(el.innerText);
                if (!t || t.length <= 5 || isGreeting(t) || isThinkingOnly(t)) continue;
                if (parts.some(p => p.includes(t) || t.includes(p))) continue;
                parts.push(t);
            }
            return parts.join(String.fromCharCode(10) + String.fromCharCode(10));
        };

        const items = document.querySelectorAll('[class*="chat-item-assistant"], [class*="message-assistant"], [class*="assistant-message"]');
        if (items.length > 0) {
            const lastItem = items[items.length - 1];
            const mds = Array.from(lastItem.querySelectorAll('.markdown-body, [class*="markdown"], [class*="content"]'));
            const txt = dedupeJoin(mds);
            if (txt) return txt;
        }
        // Fallback: blok markdown terakhir yang valid di seluruh halaman
        const allMd = Array.from(document.querySelectorAll('.markdown-body'));
        const valid = allMd.filter(el => !isBad(el));
        if (valid.length > 0) {
            const last = valid[valid.length - 1];
            let txt = stripPrefix(last.innerText);
            if (txt && !isGreeting(txt) && !isThinkingOnly(txt)) {
                return txt;
            }
        }
        return '';
    } catch(e) {
        return '';
    }
}"""

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_chat_screenshot(photo_path: str, caption: str = ""):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) or not os.path.exists(photo_path):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    with open(photo_path, "rb") as f:
        photo_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{TELEGRAM_CHAT_ID}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="caption"\r\n\r\n'
        f"{caption}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="photo"; filename="shot.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + photo_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        urllib.request.urlopen(req, timeout=15)
        print("📸 Screenshot jawaban terkirim ke Telegram!")
    except Exception as e:
        print(f"[TG Photo Error] {e}")

def wait_for_answer_done(page, timeout_sec: int = 2400, idle_sec: int = 300) -> str:
    """Tunggu jawaban Qwen selesai, TANPA patokan waktu absolut yang motong
    jawaban panjang (dulu: timeout 150s/300s — jawaban berat kepotong di tengah).

    "Perkembangan" = panjang jawaban nambah, ATAU tombol stop masih aktif
    (isGenerating), ATAU indikator thinking masih aktif (isThinking).
    Tombol stop dihitung karena fase thinking Qwen ditandai tombol stop yang
    masih nyala (run #73: status "Synthesizing..." + tombol stop aktif,
    jawaban 0 karakter selama 300 detik — loop lama salah mengira stuck).

    Berhenti kalau:
      (a) jawaban lengkap — panjang stabil 4x cek (8 detik) + tidak ada
          indikator thinking/generating; atau stabil 30x cek (60 detik)
          tanpa thinking walau indikator generating masih nyala (jaga-jaga
          kalau deteksi tombol stop meleset);
      (a3) stabil 150x cek (300 detik) apa pun indikatornya — pembatas kalau
          thinking+generating dua-duanya nyangkut nyala;
      (b) stuck — 300 detik tidak ada perkembangan sama sekali (panjang tidak
          nambah, tidak ada tombol stop, tidak ada indikator thinking);
      (c) pengaman absolut — 2400 detik (40 menit). Run #75 butuh 1500 detik
          untuk jawaban 75 ribu karakter yang masih streaming, jadi cap lama
          (900s) yang motongnya; job timeout harus ikut naik ke 30 menit.
    Selama jawaban masih nambah atau Qwen masih mikir, tunggu terus — jawaban
    cepat selesai cepat, jawaban lambat ditungguin sampai beneran kelar.
    Return: alasan berhenti ('done' | 'idle' | 'timeout').
    """
    start_t = time.time()
    prev_len = 0
    stable_count = 0
    last_progress_t = start_t
    tick = 0
    while True:
        time.sleep(2)
        tick += 1
        status = page.evaluate(JS_CHECK_STREAM_DONE)
        current_len = status.get("answerLen", 0)
        is_gen = status.get("isGenerating", False)
        is_thinking = status.get("isThinking", False)
        has_net_err = status.get("hasNetworkError", False)
        now = time.time()
        elapsed = int(now - start_t)
        if current_len > prev_len or is_gen or is_thinking:
            last_progress_t = now
        if current_len > 0 and current_len != prev_len:
            print(f"[{elapsed}s] Streaming ({current_len} karakter)...")
        # Diagnostik berkala: biar log run berikutnya kelihatan jelas apa
        # yang loop lihat (len / tombol stop / thinking / error jaringan).
        if tick % 15 == 0:
            print(f"[{elapsed}s] ⏳ len={current_len} gen={is_gen} think={is_thinking} netErr={has_net_err}")
        if current_len > 0:
            if current_len == prev_len:
                stable_count += 1
                # Jangan pernah stop jika tombol stop/generating masih aktif!
                # Harus stabil minimal 4 tick (8 detik) dan tombol stop sudah hilang
                if not is_gen and not is_thinking and stable_count >= 4 and elapsed >= 10:
                    print(f"[{elapsed}s] 🚀 Respon selesai lengkap dan tuntas!")
                    return "done"
                # Jalur lambat: 60 detik stabil tanpa thinking = selesai,
                # walau indikator generating masih nyala (deteksinya bisa meleset)
                if not is_thinking and stable_count >= 30:
                    print(f"[{elapsed}s] 🚀 Respon stabil 60 detik — dianggap selesai!")
                    return "done"
                # Jalur paling lambat: 300 detik stabil apa pun indikatornya.
                if stable_count >= 150:
                    print(f"[{elapsed}s] 🚀 Respon stabil 300 detik — dianggap selesai!")
                    return "done"
            else:
                stable_count = 0
        prev_len = current_len
        if now - last_progress_t > idle_sec:
            print(f"[{elapsed}s] ⏸️ Tidak ada perkembangan selama {idle_sec}s — dianggap stuck, ambil jawaban yang ada.")
            return "idle"
        if now - start_t > timeout_sec:
            print(f"[{elapsed}s] ⏰ Pengaman absolut {timeout_sec}s tercapai — ambil jawaban yang ada.")
            return "timeout"

def send_prompt_and_extract_answer(page, prompt: str, timeout_sec: int = 2400, idle_sec: int = 300) -> str:
    print(f"👉 Menyiapkan pengiriman pertanyaan ke Qwen: '{prompt}'...")
    page.goto("https://chat.qwen.ai/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)
    page.evaluate(JS_DISMISS_ALL_POPUPS)

    # Intercept route untuk force model qwen4-max jika belum
    def handle_route(route):
        req = route.request
        if "/api/v2/chat/completions" in req.url and req.method == "POST":
            try:
                post_data = req.post_data
                if post_data:
                    data = json.loads(post_data)
                    data["model"] = "qwen4-max"
                    if "messages" in data and isinstance(data["messages"], list):
                        for msg in data["messages"]:
                            if isinstance(msg, dict) and "models" in msg:
                                msg["models"] = ["qwen4-max"]
                    route.continue_(post_data=json.dumps(data))
                    return
            except Exception:
                pass
        route.continue_()

    page.route("**/api/v2/chat/completions*", handle_route)

    # Pindah model secara visual di dropdown UI ke Qwen 4 Max jika belum
    try:
        print("👉 Membuka dropdown model di pojok kiri atas...")
        # Klik elemen trigger model yang berada di area header (bukan di sidebar history chat)
        trigger = page.locator("header [class*='trigger'], header .wms-trigger__text, main [class*='model-select'], [class*='header'] [class*='trigger'], .wms-trigger__text").first
        if trigger.is_visible(timeout=4000):
            trigger.click(force=True)
            time.sleep(1.5)
            # Ambil semua teks dari item menu yang muncul
            menu_items = page.evaluate("""() => {
                const els = document.querySelectorAll('.ant-dropdown-menu-item, [role="menuitem"], div[class*="item"], span[class*="item"]');
                return Array.from(els).map(e => (e.innerText || '').trim()).filter(Boolean);
            }""")
            print(f"[DEBUG MODEL MENU] Opsi tersedia ({len(menu_items)} item): {menu_items}")
            
            # Cari dan klik opsi Qwen 4 Max
            clicked = False
            for selector in [
                "text='Qwen4-Max'",
                "text='Qwen 4 Max'",
                "text='4 Max'",
                "[role='menuitem']:has-text('Max')",
                ".ant-dropdown-menu-item:has-text('Max')",
                "div:has-text('Qwen4-Max')"
            ]:
                loc = page.locator(selector).first
                if loc.is_visible(timeout=1000):
                    loc.click(force=True)
                    clicked = True
                    print(f"🎯 Sukses mengklik model via selector: {selector}")
                    break
                    
            if not clicked:
                # Coba via JS evaluator
                page.evaluate("""() => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const t = (el.innerText || '').trim();
                        if (t === 'Qwen4-Max' || t === 'Qwen 4 Max' || t === '4 Max') {
                            el.click();
                            break;
                        }
                    }
                }""")
            time.sleep(1.5)
        else:
            print("Notice: Trigger Qwen3.7-Plus tidak terlihat.")
    except Exception as e:
        print(f"Notice UI model switch: {e}")

    print("👉 Mengetik prompt ke input chat...")
    textarea = page.locator("textarea, [contenteditable='true'], input[type='text']").first
    textarea.wait_for(state="visible", timeout=25000)
    textarea.click(force=True)
    time.sleep(0.5)
    try:
        textarea.fill(prompt)
    except Exception:
        page.evaluate("""(text) => {
            const el = document.querySelector('textarea, [contenteditable="true"]');
            if (el) {
                if (el.tagName === 'TEXTAREA') el.value = text;
                else el.innerText = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""", prompt)
    time.sleep(1)

    print("👉 Menekan tombol kirim / Enter...")
    textarea.press("Enter")
    time.sleep(0.5)
    page.keyboard.press("Enter")
    try:
        send_btns = page.locator("button[aria-label*='Kirim'], button[aria-label*='Send'], button[type='submit'], .send-button, .chat-input-send-button, button:has(svg)")
        for i in range(send_btns.count()):
            btn = send_btns.nth(i)
            if btn.is_visible():
                btn.click(force=True)
                break
    except Exception as e:
        print(f"Notice send button: {e}")

    # Fallback DOM JS click jika textarea masih berisi teks
    time.sleep(1.5)
    page.evaluate("""() => {
        const btn = document.querySelector('button[aria-label*="Kirim"], button[aria-label*="Send"], .send-button, .chat-input-send-button');
        if (btn) btn.click();
    }""")

    print("👉 Menunggu dan mengekstrak respon jawaban stream...")
    time.sleep(4)
    page.screenshot(path="debug_chat_sent.png")
    
    # Cetak cuplikan seluruh teks yang ada di halaman chat
    page_txt = page.evaluate("() => document.body.innerText")
    print(f"[DEBUG DOM AFTER SEND] Body sample (250 chars): {page_txt[:250].replace(chr(10), ' ')}")
    
    wait_for_answer_done(page, timeout_sec=timeout_sec, idle_sec=idle_sec)

    time.sleep(1)
    # Ambil screenshot jawaban lengkap beserta header model yang aktif di pojok kiri atas
    screenshot_file = "qwen_answer_screenshot.png"
    try:
        page.screenshot(path=screenshot_file)
        send_chat_screenshot(screenshot_file, "📸 [BUKTI LAYAR JAWABAN] Qwen 4 Max Engine Aktif")
    except Exception as e:
        print(f"Notice screenshot capture: {e}")

    answer = page.evaluate(JS_EXTRACTOR)
    if not answer or len(answer) < 5:
        # Fallback ekstraseluruh teks setelah prompt pertanyaan
        body_txt = page.evaluate("() => document.body.innerText")
        if prompt in body_txt:
            answer = body_txt.split(prompt, 1)[-1].strip()
            # Bersihkan footer disclaimer
            for stopword in ["AI-generated content may not be accurate", "Auto", "New Chat"]:
                if stopword in answer:
                    answer = answer.split(stopword)[0].strip()
            # Jangan pernah jadikan indikator "Thinking..." sebagai jawaban:
            # kalau Qwen masih mikir saat diekstrak, kembalikan '' saja.
            # Termasuk baris status fase thinking ("Synthesizing...") yang
            # singkat (< 200 karakter) — itu bukan jawaban.
            if re.match(r'^(thinking|berpikir|memikirkan|menalar|reasoning)[\s.…。]*$', answer, re.I) \
                    or re.match(r'^(thinking completed|berpikir selesai|pemikiran selesai|thinking done)[\s.…。]*$', answer, re.I) \
                    or re.match(r'^thought for .+$', answer, re.I) \
                    or re.match(r'^berpikir selama .+$', answer, re.I) \
                    or (re.match(r'^(synthesizing|analyzing)\b', answer, re.I) and len(answer) < 200):
                answer = ''
    return answer
