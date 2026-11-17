import os
import sys
import time
import json
import math
import random
import urllib.request
import urllib.parse
from playwright.sync_api import sync_playwright
import cv2
import numpy as np

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
    send_telegram_msg(
        "⏳ [KODE OTP TELAH TERKIRIM KE EMAIL!]\n\n"
        f"Tuan Ciro, Baxia Puzzle BERHASIL DITEMBUS! 🎉\n"
        f"Sekarang buka email {TARGET_EMAIL}, lalu BALAS CHAT INI dengan 6 digit kode OTP-nya!\n"
        f"(Bot standby {timeout_sec} detik)"
    )
    
    start_time = time.time()
    last_update_id = 0
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
                        clean_code = "".join(filter(str.isalnum, text))
                        if len(clean_code) in [4, 6, 8]:
                            send_telegram_msg(f"🎯 Menerima kode OTP: {clean_code}! Memasukkan ke form...")
                            return clean_code
        except Exception as e:
            print(f"Polling error: {e}")

    send_telegram_msg("❌ Waktu habis! Kode OTP tidak diterima.")
    return ""

def generate_slider_trajectory(distance: float):
    traj = []
    traj.append((0.0, 0.0, random.uniform(140.0, 220.0)))
    steps = random.randint(18, 25)
    jitter = 2.0

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
        drift = -0.5 - p * 3.0
        y = drift + math.sin(p * math.pi * random.uniform(1.2, 2.5)) * jitter
        delay = random.uniform(18.0, 38.0)
        traj.append((round(x, 1), round(y, 1), round(delay, 1)))

    # Micro overshoot & pull-back
    overshoot = random.uniform(2.5, 4.5)
    traj.append((round(distance + overshoot, 1), round(y, 1), round(random.uniform(40.0, 70.0), 1)))
    traj.append((round(distance - random.uniform(0.3, 1.0), 1), round(y * 0.5, 1), round(random.uniform(30.0, 50.0), 1)))
    traj.append((round(distance, 1), 0.0, round(random.uniform(40.0, 60.0), 1)))
    return traj

def find_gap_with_cv(bg_path: str) -> float:
    img = cv2.imread(bg_path)
    if img is None:
        return 200.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    # Mask out sisi kiri (posisi awal balok puzzle)
    edges[:, :60] = 0
    
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if 30 <= w <= 70 and 30 <= h <= 70:
            candidates.append((x, y, w, h))
            
    if candidates:
        # Ambil candidate yang paling mendekati bentuk kotak puzzle
        candidates.sort(key=lambda item: abs(item[2] - item[3]))
        target_x = candidates[0][0]
        print(f"🎯 OpenCV mendeteksi lubang puzzle di koordinat X={target_x} (w={candidates[0][2]}, h={candidates[0][3]})")
        return float(target_x)
        
    return 200.0

def solve_baxia_puzzle(page):
    print("🔍 Menunggu dan mendeteksi Baxia Puzzle Modal...")
    time.sleep(3)
    
    # Cek apakah ada popup Access Verification
    modal = page.locator("text='Access Verification', text='Drag to complete the puzzle', div[class*='baxia']")
    if modal.count() == 0 or not modal.first.is_visible():
        print("ℹ️ Tidak ada modal Baxia yang terlihat saat ini.")
        return False

    print("🚨 BAXIA PUZZLE TERDETEKSI! Memulai solver...")
    send_telegram_msg("⚔️ [BAXIA PUZZLE MENGHADANG!] Memulai Computer Vision Edge Matching & Trajectory Solver...")

    # Cari slider handle (tombol >>)
    slider_handle = page.locator(".nc_iconfont.btn_slide, div[class*='btn_slide'], div[class*='slider'] span, div[class*='slider'] div, div:has-text('>>')").last
    if not slider_handle.is_visible():
        slider_handle = page.locator("div[role='slider'], div[class*='handle']").first

    # Cari background puzzle image
    bg_elem = page.locator("img[class*='bg'], div[class*='bg'] img, canvas[class*='bg'], img[alt*='puzzle' i], img[src*='data:image']").first
    
    distance = 200.0
    if bg_elem.count() > 0 and bg_elem.is_visible():
        try:
            bg_elem.screenshot(path="puzzle_bg.png")
            send_telegram_photo("puzzle_bg.png", "🧩 [ANALISIS CV] Gambar Background Puzzle Terpotong")
            detected_x = find_gap_with_cv("puzzle_bg.png")
            # Skala rasio jika gambar di-downscale oleh CSS
            box = bg_elem.bounding_box()
            img_real = cv2.imread("puzzle_bg.png")
            if box and img_real is not None:
                scale_ratio = box["width"] / img_real.shape[1]
                distance = detected_x * scale_ratio
                print(f"📐 Scaled distance: {distance}px (ratio {scale_ratio:.2f})")
            else:
                distance = detected_x
        except Exception as e:
            print(f"CV detect error: {e}")
            distance = 195.0
    else:
        # Screenshot area modal untuk hitung perkiraan posisi lubang puzzle
        page.screenshot(path="modal_puzzle.png")
        distance = 195.0

    print(f"🎯 Target geser slider: {distance:.1f}px")
    
    # Ambil posisi kursor handle slider
    handle_box = slider_handle.bounding_box()
    if not handle_box:
        # Fallback cari tombol biru >>
        blue_btn = page.locator("div:has-text('>>'), span:has-text('>>')").last
        handle_box = blue_btn.bounding_box()

    if handle_box:
        start_x = handle_box["x"] + handle_box["width"] / 2
        start_y = handle_box["y"] + handle_box["height"] / 2
        
        trajectory = generate_slider_trajectory(distance)
        
        page.mouse.move(start_x, start_y)
        time.sleep(0.15)
        page.mouse.down()
        
        for pt_x, pt_y, delay in trajectory:
            page.mouse.move(start_x + pt_x, start_y + pt_y)
            time.sleep(delay / 1000.0)
            
        time.sleep(0.25)
        page.mouse.up()
        print("✅ Balok puzzle telah digeser ke target lubang!")
        time.sleep(4)
        
        page.screenshot(path="after_slider_solved.png")
        send_telegram_photo("after_slider_solved.png", "📸 Status setelah puzzle digeser")
        return True

    return False

def main():
    send_telegram_msg(f"🚀 [QWEN-TANTANGAN] Meluncurkan Full Automation + OpenCV Solver!\nTarget: {TARGET_EMAIL}")
    
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

        # Klik tombol Lanjutkan / Kirim Kode
        print("4. Mengklik tombol Lanjutkan...")
        submit_btn = None
        for txt in ["Lanjutkan", "Lanjut", "Kirim Kode", "Dapatkan Kode", "Send Code", "Next", "Continue"]:
            loc = page.get_by_role("button", name=txt)
            if loc.count() > 0 and loc.first.is_visible():
                submit_btn = loc.first
                break
            loc2 = page.locator(f"button:has-text('{txt}'), div[role='button']:has-text('{txt}')")
            if loc2.count() > 0 and loc2.first.is_visible():
                submit_btn = loc2.first
                break

        if submit_btn:
            submit_btn.click()
            time.sleep(3)
        else:
            email_input.first.press("Enter")
            time.sleep(3)

        # BAXIA PUZZLE SOLVER!
        solve_baxia_puzzle(page)

        # STEP 5: TUNGGU KODE OTP DARI TELEGRAM TUAN CIRO
        print("5. Menunggu input kode OTP dari Telegram Tuan Ciro...")
        otp_code = wait_for_telegram_otp(timeout_sec=180)
        
        if not otp_code:
            print("❌ Gagal login: OTP tidak diberikan.")
            browser.close()
            return

        print(f"👉 Mengisikan kode OTP {otp_code} ke web...")
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
                inputs = page.locator("input")
                for i in range(inputs.count()):
                    inp = inputs.nth(i)
                    if inp.is_visible() and inp.input_value() != TARGET_EMAIL:
                        inp.fill(otp_code)
                        break

        time.sleep(1)
        
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
            confirm_btn.click()
        else:
            page.keyboard.press("Enter")

        time.sleep(6)

        # STEP 6: VERIFIKASI LOGIN & AMBIL SESSION
        print("6. Memeriksa status login & mengambil session cookies...")
        page.screenshot(path="step6_login_result.png")
        
        cookies = context.cookies()
        cookies_dict = {c['name']: c['value'] for c in cookies}
        
        is_success = any(k in cookies_dict for k in ["token", "session", "b-user-id", "login_aliyunid_ticket", "sg_sub_c_id"]) or "chat" in page.url
        
        if is_success:
            caption = "🎉 [SUKSES LOGIN!] Tuan Ciro, login berhasil ditembus! Session aktif didapatkan!"
            send_telegram_photo("step6_login_result.png", caption)
            send_telegram_msg(f"🍪 Total Cookies Didapat: {len(cookies_dict)}\nJSON disimpan di session_qwen.json!")
            with open("session_qwen.json", "w") as f:
                json.dump(cookies_dict, f, indent=2)
        else:
            send_telegram_photo("step6_login_result.png", "⚠️ Step 6: Status setelah input OTP.")

        browser.close()

if __name__ == "__main__":
    main()
