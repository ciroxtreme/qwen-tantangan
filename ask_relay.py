import os
import sys
import time
import json
import uuid
import math
import random
import urllib.request
import urllib.parse
from camoufox.sync_api import Camoufox

PROMPT = sys.argv[1] if len(sys.argv) > 1 else "Halo Qwen, tes respon 1 kata: READY"
SESSION_FILE = "session_qwen.json"

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
    const bubbles = document.querySelectorAll('.chat-message-list .markdown-body, [class*="chat-item-assistant"] .markdown-body, .markdown-body');
    let answerLen = 0;
    let snippet = "";
    let isThinkingOnly = false;

    if (bubbles.length > 0) {
        for (let i = bubbles.length - 1; i >= 0; i--) {
            const t = bubbles[i].innerText.trim();
            if (t && !t.includes("Ada yang bisa saya bantu?") && !t.includes("Umpan balik ini")) {
                answerLen = t.length;
                snippet = t.substring(0, 80);
                if (!t.includes("Berpikir selesai") && (t.includes("berpikir") || t.includes("thinking") || t.includes("Analyze") || t.includes("Assessing"))) {
                    isThinkingOnly = true;
                }
                break;
            }
        }
    }
    return {
        hasStop: hasStop,
        answerLen: answerLen,
        snippet: snippet,
        isThinkingOnly: isThinkingOnly
    };
}"""

JS_EXTRACTOR = """() => {
    const bubbles = document.querySelectorAll('.chat-message-list .markdown-body, [class*="chat-item-assistant"] .markdown-body, [class*="message-assistant"] .markdown-body, .markdown-body');
    if (bubbles.length > 0) {
        for (let i = bubbles.length - 1; i >= 0; i--) {
            let t = bubbles[i].innerText.trim();
            if (t && !t.includes("Ada yang bisa saya bantu?") && !t.includes("Umpan balik ini") && t.length > 0) {
                if (t.startsWith("Berpikir selesai")) {
                    t = t.replace(/^Berpikir selesai\\s*/, '').trim();
                }
                return t;
            }
        }
    }
    return "";
}"""

def main():
    print(f"🚀 Memulai Qwen Relay Camoufox...")
    print(f"Prompt: {PROMPT}")
    
    # Ambil sesi jika ada
    cookies_to_load = []
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE) as f:
                c_data = json.load(f)
                if isinstance(c_data, dict):
                    for k, v in c_data.items():
                        cookies_to_load.append({
                            "name": k,
                            "value": str(v),
                            "domain": ".qwen.ai",
                            "path": "/"
                        })
                elif isinstance(c_data, list):
                    cookies_to_load = c_data
            print(f"🍪 Berhasil memuat {len(cookies_to_load)} cookies dari {SESSION_FILE}")
        except Exception as e:
            print(f"Warning load cookies: {e}")

    with Camoufox(
        headless=True,
        os="linux",
        i_know_what_im_doing=True
    ) as browser:
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        if cookies_to_load:
            context.add_cookies(cookies_to_load)

        page = context.new_page()

        # Intercept route untuk force rewrite model ke qwen4-max
        def handle_route(route):
            req = route.request
            if "/api/v2/chat/completions" in req.url and req.method == "POST":
                try:
                    post_data = req.post_data
                    if post_data:
                        data = json.loads(post_data)
                        print(f"🎯 Intercepted completion! Rewriting to qwen4-max...")
                        data["model"] = "qwen4-max"
                        if "messages" in data and isinstance(data["messages"], list):
                            for msg in data["messages"]:
                                if isinstance(msg, dict) and "models" in msg:
                                    msg["models"] = ["qwen4-max"]
                        route.continue_(post_data=json.dumps(data))
                        return
                except Exception as ex:
                    print(f"Rewrite warning: {ex}")
            route.continue_()

        page.route("**/api/v2/chat/completions*", handle_route)

        print("1. Meluncur ke chat.qwen.ai...")
        page.goto("https://chat.qwen.ai/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)
        page.evaluate(JS_DISMISS_ALL_POPUPS)

        # Cek apakah sesi aktif
        body_sample = page.evaluate("() => document.body.innerText.substring(0, 150)")
        print(f"Header snippet: {body_sample.replace(chr(10), ' ')}")

        print(f"2. Memasukkan pertanyaan ({len(PROMPT)} karakter)...")
        textarea = page.locator("textarea, [contenteditable='true']").first
        textarea.wait_for(state="visible", timeout=20000)
        textarea.fill(PROMPT)
        time.sleep(0.5)

        print("3. Mengirim pesan...")
        try:
            send_btn = page.locator("button[aria-label*='Kirim'], button[aria-label*='Send'], button[type='submit'], .send-button, .chat-input-send-button").last
            if send_btn.is_visible(timeout=2000):
                send_btn.click(force=True)
            else:
                page.keyboard.press("Enter")
        except Exception:
            page.keyboard.press("Enter")

        print("4. Memantau respon streaming...")
        start_t = time.time()
        max_wait = 120
        prev_len = 0
        stable_count = 0

        while time.time() - start_t < max_wait:
            time.sleep(1.5)
            status = page.evaluate(JS_CHECK_STREAM_DONE)
            current_len = status.get("answerLen", 0)
            has_stop = status.get("hasStop", False)
            is_thinking = status.get("isThinkingOnly", False)
            elapsed = int(time.time() - start_t)
            snippet = status.get("snippet", "")

            if current_len > 0 and current_len != prev_len:
                print(f"[{elapsed}s] Streaming ({current_len} chars): {snippet[:40]}...")

            if current_len > 0 and not is_thinking:
                if current_len == prev_len:
                    stable_count += 1
                    if not has_stop and stable_count >= 2:
                        print(f"[{elapsed}s] 🚀 Selesai instan ({current_len} chars)!", flush=True)
                        break
                    if stable_count >= 4:
                        print(f"[{elapsed}s] 🛡️ Fallback stabil ({current_len} chars).", flush=True)
                        break
                else:
                    stable_count = 0

            prev_len = current_len

        print("\n" + "="*40 + " QWEN FINAL ANSWER " + "="*40 + "\n")
        answer = page.evaluate(JS_EXTRACTOR)
        if not answer:
            answer = page.evaluate("() => { const el = document.querySelector('.markdown-body'); return el ? el.innerText : ''; }")
        print(answer)
        print("\n" + "="*95 + "\n")

        # Update session cookies jika ada perubahan
        new_cookies = context.cookies()
        if new_cookies:
            cookies_dict = {c['name']: c['value'] for c in new_cookies}
            with open(SESSION_FILE, "w") as f:
                json.dump(cookies_dict, f, indent=2)
            print(f"🍪 Sesi diperbarui ke {SESSION_FILE} ({len(cookies_dict)} cookies)")

if __name__ == "__main__":
    main()
