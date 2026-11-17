import time
import json
import re

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
            const md = lastItem.querySelector('.markdown-body, [class*="content"], div');
            if (md && md.innerText) {
                let txt = md.innerText.trim();
                return txt.replace(/^(Berpikir selesai|Thinking completed)\s*/i, '').trim();
            }
        }
        const allMd = document.querySelectorAll('.markdown-body');
        for (let i = allMd.length - 1; i >= 0; i--) {
            const el = allMd[i];
            const isUser = el.closest('[class*="user"]') !== null;
            if (!isUser) {
                let txt = (el.innerText || '').trim();
                if (txt && !txt.includes('How can I help') && !txt.includes('Ada yang bisa')) {
                    return txt.replace(/^(Berpikir selesai|Thinking completed)\s*/i, '').trim();
                }
            }
        }
        const userBubbles = document.querySelectorAll('[class*="chat-item-user"], [class*="message-user"]');
        if (userBubbles.length > 0) {
            const lastUser = userBubbles[userBubbles.length - 1];
            let nextEl = lastUser.nextElementSibling;
            while (nextEl) {
                const t = (nextEl.innerText || '').trim();
                if (t && !t.includes('AI-generated') && !t.includes('How can I help')) {
                    return t.replace(/^Berpikir selesai\s*/, '').trim();
                }
                nextEl = nextEl.nextElementSibling;
            }
        }
        return '';
    } catch(e) {
        return '';
    }
}'''

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
