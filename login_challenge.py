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
    # Cek iframe atau elemen slider baxia / nc-container
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
            
    # Cek di dalam iframe jika ada
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
            
            # Estimasi jarak geser slider Alibaba (standar track ~280-320px)
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
    send_telegram_msg(f"🚀 [QWEN-TANTANGAN] Memulai misi login otonom target: {TARGET_EMAIL}...")
    
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
        # Cloak Playwright
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)
        page = context.new_page()

        print("1. Membuka https://chat.qwen.ai/...")
        page.goto("https://chat.qwen.ai/", wait_until="networkidle", timeout=60000)
        time.sleep(2)
        
        page.screenshot(path="step1_home.png")
        send_telegram_photo("step1_home.png", "📸 Step 1: Beranda Qwen terbuka")

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
        else:
            print("⚠️ Tombol login tidak ditemukan langsung, cek dialog...")

        page.screenshot(path="step2_login_modal.png")
        send_telegram_photo("step2_login_modal.png", "📸 Step 2: Modal Login Terbuka")

        # Cek form email
        print(f"3. Memasukkan email target {TARGET_EMAIL}...")
        email_input = page.locator("input[type='email'], input[placeholder*='email' i], input[placeholder*='surel' i]")
        if email_input.count() == 0:
            # Cari input text umum
            email_input = page.locator("input[type='text']")

        if email_input.count() > 0 and email_input.first.is_visible():
            email_input.first.fill(TARGET_EMAIL)
            print("✅ Email berhasil diisi!")
            time.sleep(1)
        else:
            print("⚠️ Input email belum terlihat!")

        page.screenshot(path="step3_email_filled.png")
        send_telegram_photo("step3_email_filled.png", f"📸 Step 3: Input email {TARGET_EMAIL}")

        # Klik tombol Kirim Kode / Lanjut / Verifikasi
        print("4. Mencari tombol Kirim Kode / Selanjutnya...")
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
            # Fallback tekan Enter
            print("👉 Menekan Enter pada input email...")
            email_input.first.press("Enter")
            time.sleep(3)

        # Cek apakah memicu Baxia Slider!
        solve_slider_if_present(page)

        page.screenshot(path="step4_after_submit.png")
        send_telegram_photo("step4_after_submit.png", "📸 Step 4: Kondisi setelah submit (menunggu OTP / slider)")

        send_telegram_msg("🏁 Tahap awal selesai! Silakan cek foto screenshot yang dikirim ke Telegram untuk melihat respon sistem Qwen/Baxia.")
        browser.close()

if __name__ == "__main__":
    main()
