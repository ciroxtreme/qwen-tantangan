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
    const bubbles = document.querySelectorAll('.chat-message-list .markdown-body, [class*="chat-item-assistant"] .markdown-body, .markdown-body');
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
    sent = False
    try:
        send_btn = page.locator("button[aria-label*='Kirim'], button[aria-label*='Send'], button[type='submit'], .send-button, .chat-input-send-button").last
        if send_btn.is_visible(timeout=3000):
            send_btn.click(force=True)
            sent = True
            print("Tombol kirim tertekan!")
    except Exception as e:
        print(f"Notice send button: {e}")

    if not sent:
        textarea.press("Enter")
        print("Enter keyboard ditekan!")

    # Fallback DOM JS click jika textarea masih berisi teks
    time.sleep(1.5)
    page.evaluate("""() => {
        const btn = document.querySelector('button[aria-label*="Kirim"], button[aria-label*="Send"], .send-button, .chat-input-send-button');
        if (btn) btn.click();
    }""")

    print("👉 Menunggu dan mengekstrak respon jawaban stream...")
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
    return answer
