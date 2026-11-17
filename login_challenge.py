import os
import sys
import time
import json
import math
import random
import urllib.request
import urllib.parse
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TARGET_EMAIL = os.environ.get("TARGET_EMAIL", "tuanciroxtreme@gmail.com")

def send_telegram_msg(text: str):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print(f"[TG] {text}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[TG Error] {e}")

def send_telegram_photo(photo_path: str, caption: str = ""):
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
    except Exception as e:
        print(f"[TG Photo Error] {e}")

def wait_for_telegram_otp(timeout_sec: int = 180) -> str:
    """Mendengarkan balasan chat dari Tuan Ciro di Telegram berisi kode OTP."""
    send_telegram_msg(
        "⏳ [INPUT DIBUTUHKAN TUAN CIRO]\n\n"
        f"Alibaba sedang mengirim kode verifikasi ke email {TARGET_EMAIL}.\n"
        "👉 Buka email Tuan Ciro, lalu LANGSUNG BALAS CHAT INI dengan 6 digit angka kodenya!\n"
        f"(Bot akan menunggu sampai {timeout_sec} detik)"
    )
    
    start_time = time.time()
    last_update_id = 0
    # Ambil offset awal agar pesan lama tidak terbaca
    try:
        init_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset=-1"
        with urllib.request.urlopen(init_url, timeout=10) as r:
            data = json.loads(r.read().decode())
            if data.get("result"):
                last_update_id = data["result"][-1]["update_id"]
    except Exception:
        pass

    while time.time() - start_time < timeout_sec:
        time.sleep(3)
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=5"
            with urllib.request.urlopen(url, timeout=15) as r:
                res = json.loads(r.read().decode())
                for up in res.get("result", []):
                    last_update_id = up["update_id"]
                    msg = up.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id"))
                    text = msg.get("text", "").strip()
                    
                    if chat_id == str(TELEGRAM_CHAT_ID) and text:
                        # Bersihkan spasi atau tanda hubung
                        clean_code = "".join(filter(str.isalnum, text))
                        if len(clean_code) in [4, 6, 8]:
                            send_telegram_msg(f"🎯 Menerima kode OTP: {clean_code}! Memasukkan ke halaman Qwen...")
                            return clean_code
        except Exception as e:
            print(f"Polling error: {e}")

    send_telegram_msg("❌ Waktu habis! Tidak ada kode OTP diterima dalam batas waktu.")
    return ""

def generate_slider_trajectory(distance: float):
    traj = []
    traj.append((0.0, 0.0, random.uniform(120.0, 200.0)))
    steps = random.randint(14, 20)
    jitter = 2.5

    for i in range(steps):
        p = (i + 1) / steps
        if p <= 0.20:
            t = p / 0.20
            eased = 0.02 + 0.13 * (t ** 1.8)
        elif p <= 0.60:
            t = (p - 0.20) / 0.40
            eased = 0.15 + 0.60 * t
        elif p <= 0.85:
            t = (p - 0.60) / 0.25
            eased = 0.75 + 0.20 * t
        else:
            t = (p - 0.85) / 0.15
            eased = 0.95 + 0.05 * t

        x = distance * eased
        drift = -0.5 - p * 3.5
        y = drift + math.sin(p * math.pi * random.uniform(1.5, 3.0)) * jitter
        delay = random.uniform(20.0, 45.0)
        traj.append((round(x, 1), round(y, 1), round(delay, 1)))

    # Overshoot & micro adjustment
    overshoot = random.uniform(3.0, 5.5)
    traj.append((round(distance + overshoot, 1), round(y, 1), round(random.uniform(40.0, 70.0), 1)))
    traj.append((round(distance - random.uniform(0.5, 1.2), 1), round(y * 0.5, 1), round(random.uniform(30.0, 50.0), 1)))
    traj.append((round(distance, 1), 0.0, round(random.uniform(40.0, 60.0), 1)))
    return traj

def solve_slider_if_present(page):
    print("🔍 Memeriksa apakah Baxia Slider muncul...")
    time.sleep(2)
    slider_btn = None
    selectors = [
        ".baxia-dialog-content .btn_slide",
        "#nc_1_n1z",
        ".nc_iconfont.btn_slide",
        "span[id*='n1z']",
        ".slidetounlock",
        "div[class*='slider']",
        "div[class*='button']"
    ]
    
    for s in selectors:
        loc = page.locator(s)
        if loc.count() > 0 and loc.first.is_visible():
            slider_btn = loc.first
            print(f"🎯 Slider tombol terdeteksi via selector: {s}")
            break
            
    if not slider_btn:
        for frame in page.frames:
            for s in selectors:
                loc = frame.locator(s)
                if loc.count() > 0 and loc.first.is_visible():
                    slider_btn = loc.first
                    print(f"🎯 Slider tombol terdeteksi di iframe via selector: {s}")
                    break
            if slider_btn:
                break

    if slider_btn:
        print("⚡ Mengeksekusi SlideX Human Curve pada Baxia Slider...")
        box = slider_btn.bounding_box()
        if box:
            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2
            
            track_distance = 300.0
            trajectory = generate_slider_trajectory(track_distance)
            
            page.mouse.move(start_x, start_y)
            time.sleep(0.1)
            page.mouse.down()
            
            for pt_x, pt_y, delay in trajectory:
                page.mouse.move(start_x + pt_x, start_y + pt_y)
                time.sleep(delay / 1000.0)
                
            time.sleep(0.2)
            page.mouse.up()
            print("✅ Slider telah digeser!")
            time.sleep(3)
            return True
    return False

def main():
    send_telegram_msg(f"🚀 [QWEN-TANTANGAN] Memulai Misi Login Lengkap sampai Step Selesai!\nTarget: {TARGET_EMAIL}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="id-ID",
            timezone_id="Asia/Jakarta",
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)
        page = context.new_page()

        print("1. Membuka https://chat.qwen.ai/...")
        page.goto("https://chat.qwen.ai/", wait_until="networkidle", timeout=60000)
        time.sleep(2)

        # Cari tombol Masuk / Sign In
        print("2. Mencari tombol Masuk / Sign In...")
        login_btn = None
        for txt in ["Masuk", "Sign in", "Log in", "Login"]:
            loc = page.get_by_role("button", name=txt)
            if loc.count() > 0 and loc.first.is_visible():
                login_btn = loc.first
                break
            loc2 = page.locator(f"text='{txt}'")
            if loc2.count() > 0 and loc2.first.is_visible():
                login_btn = loc2.first
                break

        if login_btn:
            print("👉 Mengklik tombol login...")
            login_btn.click()
            time.sleep(3)

        # Cek form email
        print(f"3. Memasukkan email target {TARGET_EMAIL}...")
        email_input = page.locator("input[type='email'], input[placeholder*='email' i], input[placeholder*='surel' i]")
        if email_input.count() == 0:
            email_input = page.locator("input[type='text']")

        if email_input.count() > 0 and email_input.first.is_visible():
            email_input.first.fill(TARGET_EMAIL)
            print("✅ Email berhasil diisi!")
            time.sleep(1)

        # Klik tombol Kirim Kode / Lanjut / Verifikasi
        print("4. Mencari tombol Kirim Kode / Lanjutkan...")
        submit_btn = None
        for txt in ["Kirim Kode", "Dapatkan Kode", "Send Code", "Get Code", "Lanjut", "Selanjutnya", "Next", "Continue"]:
            loc = page.get_by_role("button", name=txt)
            if loc.count() > 0 and loc.first.is_visible():
                submit_btn = loc.first
                break
            loc2 = page.locator(f"button:has-text('{txt}'), div[role='button']:has-text('{txt}')")
            if loc2.count() > 0 and loc2.first.is_visible():
                submit_btn = loc2.first
                break

        if submit_btn:
            print(f"👉 Mengklik tombol: {submit_btn.inner_text()}...")
            submit_btn.click()
            time.sleep(3)
        else:
            email_input.first.press("Enter")
            time.sleep(3)

        # Cek dan selesaikan slider Baxia jika muncul
        solve_slider_if_present(page)

        page.screenshot(path="step4_otp_waiting.png")
        send_telegram_photo("step4_otp_waiting.png", "📸 Step 4: Menunggu Input Kode Verifikasi")

        # STEP 5: TUNGGU KODE OTP DARI TELEGRAM TUAN CIRO
        print("5. Menunggu input kode OTP dari Telegram Tuan Ciro...")
        otp_code = wait_for_telegram_otp(timeout_sec=180)
        
        if not otp_code:
            print("❌ Gagal login: OTP tidak diberikan.")
            browser.close()
            return

        print(f"👉 Mengisikan kode OTP {otp_code} ke web...")
        # Cek input OTP: bisa 6 input box terpisah, atau 1 input text
        code_inputs = page.locator("input[maxlength='1'], input[autocomplete='one-time-code']")
        if code_inputs.count() >= len(otp_code):
            for idx, ch in enumerate(otp_code):
                code_inputs.nth(idx).fill(ch)
                time.sleep(0.1)
        else:
            otp_box = page.locator("input[placeholder*='kode' i], input[placeholder*='code' i], input[type='number'], input[type='tel']")
            if otp_box.count() > 0 and otp_box.first.is_visible():
                otp_box.first.fill(otp_code)
            else:
                # Fallback ke active element atau input apapun setelah email
                inputs = page.locator("input")
                for i in range(inputs.count()):
                    inp = inputs.nth(i)
                    if inp.is_visible() and inp.input_value() != TARGET_EMAIL:
                        inp.fill(otp_code)
                        break

        time.sleep(1)
        
        # Klik tombol Masuk / Verifikasi / Selesai
        confirm_btn = None
        for txt in ["Masuk", "Verifikasi", "Konfirmasi", "Confirm", "Submit", "Verify", "Log in"]:
            loc = page.get_by_role("button", name=txt)
            if loc.count() > 0 and loc.first.is_visible():
                confirm_btn = loc.first
                break
            loc2 = page.locator(f"button:has-text('{txt}')")
            if loc2.count() > 0 and loc2.first.is_visible():
                confirm_btn = loc2.first
                break

        if confirm_btn:
            print(f"👉 Mengklik tombol konfirmasi: {confirm_btn.inner_text()}...")
            confirm_btn.click()
        else:
            page.keyboard.press("Enter")

        time.sleep(6)

        # STEP 6: VERIFIKASI LOGIN BERHASIL & AMBIL COOKIE
        print("6. Memeriksa status login & mengambil session cookies...")
        page.screenshot(path="step6_login_result.png")
        
        cookies = context.cookies()
        cookies_dict = {c['name']: c['value'] for c in cookies}
        
        # Tanda berhasil: ada token / session / cookie khusus qwen
        is_success = any(k in cookies_dict for k in ["token", "session", "b-user-id", "login_aliyunid_ticket", "sg_sub_c_id"]) or "chat" in page.url
        
        if is_success:
            caption = "🎉 [SUKSES LOGIN!] Tuan Ciro, login berhasil ditembus! Session aktif didapatkan!"
            send_telegram_photo("step6_login_result.png", caption)
            send_telegram_msg(f"🍪 Total Cookies Didapat: {len(cookies_dict)}\nJSON disimpan di session_qwen.json!")
            with open("session_qwen.json", "w") as f:
                json.dump(cookies_dict, f, indent=2)
        else:
            send_telegram_photo("step6_login_result.png", "⚠️ Step 6: Status setelah input OTP (periksa apakah ada error/dialog tambahan).")

        browser.close()

if __name__ == "__main__":
    main()
