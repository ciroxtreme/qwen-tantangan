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

JS_CHECK_STREAM_DONE = """() => {
    let hasStop = false;
    const buttons = document.querySelectorAll('button');
    for (const b of buttons) {
        const txt = (b.innerText || '').toLowerCase();
        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
        if (txt.includes('stop') || aria.includes('stop') || aria.includes('berhenti')) {
            hasStop = true;
            break;
        }
    }
    // Cari elemen respon assistant
    const targets = document.querySelectorAll('.chat-message-list .markdown-body, [class*="assistant"] .markdown-body, .markdown-body, [class*="message-content"], [class*="chat-item"]');
    let answerLen = 0;
    let snippet = "";

    if (targets.length > 0) {
        for (let i = targets.length - 1; i >= 0; i--) {
            const t = targets[i].innerText ? targets[i].innerText.trim() : "";
            if (t && !t.includes("Ada yang bisa saya bantu?") && !t.includes("How can I help you?") && !t.includes("Umpan balik ini")) {
                answerLen = t.length;
                snippet = t.substring(0, 80);
                break;
            }
        }
    }
    
    // Fallback deteksi teks di body selain header/sidebar
    if (answerLen === 0) {
        const bodyTxt = document.body.innerText || "";
        const parts = bodyTxt.split(/Tes live tahap|Halo Qwen|Jelaskan secara/i);
        if (parts.length > 1) {
            const afterPrompt = parts[parts.length - 1].trim();
            answerLen = afterPrompt.length;
            snippet = afterPrompt.substring(0, 80);
        }
    }

    return {
        hasStop: hasStop,
        answerLen: answerLen,
        snippet: snippet,
        isThinkingOnly: false
    };
}"""

JS_EXTRACTOR = r'''() => {
    try {
        const items = document.querySelectorAll('[class*="chat-item-assistant"], [class*="message-assistant"], [class*="assistant-message"]');
        if (items.length > 0) {
            const lastItem = items[items.length - 1];
            const mds = lastItem.querySelectorAll('.markdown-body');
            for (let i = mds.length - 1; i >= 0; i--) {
                const el = mds[i];
                if (!el.closest('[class*="thinking"], [class*="reasoning"], [class*="thought"]')) {
                    const t = (el.innerText || '').trim();
                    if (t && t !== 'Skip' && !t.includes('How can I help')) {
                        return t;
                    }
                }
            }
        }
        const allMd = document.querySelectorAll('.markdown-body');
        for (let i = allMd.length - 1; i >= 0; i--) {
            const el = allMd[i];
            const isUser = el.closest('[class*="user"]') !== null;
            const isThought = el.closest('[class*="thinking"], [class*="reasoning"], [class*="thought"]') !== null;
            if (!isUser && !isThought) {
                let txt = (el.innerText || '').trim();
                if (txt && txt !== 'Skip' && !txt.includes('How can I help') && !txt.includes('Ada yang bisa')) {
                    return txt.replace(/^(Berpikir selesai|Thinking completed)\s*/i, '').trim();
                }
            }
        }
        return '';
    } catch(e) {
        return '';
    }
}'''

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

def send_prompt_and_extract_answer(page, prompt: str, timeout_sec: int = 150) -> str:
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
    textarea = page.locator("textarea, [contenteditable='true']").first
    textarea.wait_for(state="visible", timeout=25000)
    textarea.click()
    time.sleep(0.5)
    textarea.fill(prompt)
    time.sleep(1)

    print("👉 Menekan tombol kirim / Enter...")
    textarea.press("Enter")
    time.sleep(1)
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
    
    start_t = time.time()
    prev_len = 0
    stable_count = 0

    while time.time() - start_t < timeout_sec:
        time.sleep(2)
        status = page.evaluate(JS_CHECK_STREAM_DONE)
        current_len = status.get("answerLen", 0)
        has_stop = status.get("hasStop", False)
        is_thinking = status.get("isThinkingOnly", False)
        elapsed = int(time.time() - start_t)

        if current_len > 0 and current_len != prev_len:
            print(f"[{elapsed}s] Streaming ({current_len} karakter)...")

        if current_len > 0 and not is_thinking:
            if current_len == prev_len:
                stable_count += 1
                if not has_stop and stable_count >= 2:
                    print(f"[{elapsed}s] 🚀 Respon selesai lengkap!")
                    break
                if stable_count >= 5:
                    print(f"[{elapsed}s] 🛡️ Respon stabil.")
                    break
            else:
                stable_count = 0

        prev_len = current_len

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
    return answer
