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

def generate_slider_trajectory(distance: float):
    traj = []
    traj.append((0.0, 0.0, random.uniform(140.0, 200.0)))
    steps = random.randint(25, 32)
    jitter = 1.8

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
        drift = -0.5 - p * 2.5
        y = drift + math.sin(p * math.pi * random.uniform(1.2, 2.2)) * jitter
        delay = random.uniform(20.0, 40.0)
        traj.append((round(x, 1), round(y, 1), round(delay, 1)))

    # Micro overshoot & pull-back halus
    overshoot = random.uniform(2.0, 4.0)
    traj.append((round(distance + overshoot, 1), round(y, 1), round(random.uniform(40.0, 60.0), 1)))
    traj.append((round(distance - random.uniform(0.2, 0.8), 1), round(y * 0.5, 1), round(random.uniform(30.0, 50.0), 1)))
    traj.append((round(distance, 1), 0.0, round(random.uniform(40.0, 60.0), 1)))
    return traj

def find_gap_with_cv(bg_path: str) -> float:
    img = cv2.imread(bg_path)
    if img is None:
        return 195.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    edges[:, :60] = 0
    
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if 25 <= w <= 80 and 25 <= h <= 80:
            candidates.append((x, y, w, h))
            
    if candidates:
        candidates.sort(key=lambda item: abs(item[2] - item[3]))
        target_x = candidates[0][0]
        print(f"🎯 OpenCV mendeteksi lubang puzzle di X={target_x} (w={candidates[0][2]}, h={candidates[0][3]})")
        return float(target_x)
        
    return 195.0

def wait_for_telegram_otp(timeout_sec: int = 180) -> str:
    send_telegram_msg(
        "🎉 [BAXIA PUZZLE LOOOOLOS! KODE OTP TERKIRIM!]\n\n"
        f"Tuan Ciro, puzzle berhasil dijebol dan Alibaba sudah mengirimkan kode baru ke {TARGET_EMAIL}!\n"
        "👉 Buka email, lalu BALAS pesan bot ini dengan 6 digit kodenya!"
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
                            send_telegram_msg(f"🎯 Menerima kode OTP: {clean_code}! Memasukkan ke web...")
                            return clean_code
        except Exception as e:
            pass
    return ""

def inspect_and_solve_baxia(page):
    print("🔍 Menginspeksi apakah Baxia Puzzle / #waf_nc_block muncul...")
    
    # Coba hingga 3 kali percobaan jika puzzle me-refresh gambar baru
    for attempt in range(1, 4):
        time.sleep(3)
        page.screenshot(path=f"attempt_{attempt}_screen.png")
        
        captcha_img = page.locator("#aliyunCaptcha-img, img.puzzle").first
        if captcha_img.count() == 0 or not captcha_img.is_visible():
            print("ℹ️ Gambar puzzle tidak terlihat, mungkin sudah lolos atau belum muncul.")
            break

        print(f"🚨 [PERCOBAAN {attempt}] BAXIA PUZZLE AKTIF! Membaca koordinat...")
        captcha_img.screenshot(path=f"puzzle_{attempt}.png")
        send_telegram_photo(f"puzzle_{attempt}.png", f"🧩 [PERCOBAAN {attempt}] Gambar Puzzle Background")
        
        detected_x = find_gap_with_cv(f"puzzle_{attempt}.png")
        box = captcha_img.bounding_box()
        img_real = cv2.imread(f"puzzle_{attempt}.png")
        
        # Jarak geser default
        distance = detected_x
        if box and img_real is not None:
            scale_ratio = box["width"] / img_real.shape[1]
            distance = detected_x * scale_ratio

        # Titik awal tombol slider biru (>>):
        # Dari visual screenshot, tombol biru posisinya ada di box["x"] + 25, box["y"] + box["height"] + 25
        start_x = box["x"] + 25.0
        start_y = box["y"] + box["height"] + 25.0
        
        print(f"⚡ Menggeser balok: start=({start_x}, {start_y}) sejauh {distance}px...")
        send_telegram_msg(f"⚡ [ATTEMPT {attempt}] Menggeser balok puzzle sejauh {distance:.1f}px...")
        
        traj = generate_slider_trajectory(distance)
        
        # Gerakkan kursor ke tombol slider secara bertahap (human approach)
        page.mouse.move(start_x - 10, start_y + 10)
        time.sleep(0.1)
        page.mouse.move(start_x, start_y)
        time.sleep(0.15)
        page.mouse.down()
        
        for pt_x, pt_y, delay in traj:
            page.mouse.move(start_x + pt_x, start_y + pt_y)
            time.sleep(delay / 1000.0)
            
        time.sleep(0.3)
        page.mouse.up()
        print("✅ Balok puzzle selesai digeser! Menunggu evaluasi Baxia...")
        time.sleep(4)
        
        page.screenshot(path=f"after_attempt_{attempt}.png")
        send_telegram_photo(f"after_attempt_{attempt}.png", f"📸 [HASIL ATTEMPT {attempt}] Kondisi layar setelah digeser")
        
        # Cek apakah popup sudah hilang / form berganti ke input OTP
        if not captcha_img.is_visible() or page.locator("input[placeholder*='kode' i], input[autocomplete='one-time-code']").count() > 0:
            print("🎉 BAXIA PUZZLE BERHASIL DITEMBUS!")
            return True
            
        print("🔄 Puzzle merefresh gambar baru, mencoba kembali...")
        
    return False

def main():
    send_telegram_msg(f"🚀 [QWEN-TANTANGAN] Loop Solver Puzzle + Auto OTP Receiver!\nTarget: {TARGET_EMAIL}")
    
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
            login_btn.click()
            time.sleep(3)

        email_input = page.locator("input[type='email'], input[placeholder*='email' i], input[placeholder*='surel' i]")
        if email_input.count() == 0:
            email_input = page.locator("input[type='text']")

        if email_input.count() > 0 and email_input.first.is_visible():
            email_input.first.fill(TARGET_EMAIL)
            print("✅ Email berhasil diisi!")
            time.sleep(1)

        submit_btn = None
        for txt in ["Lanjutkan", "Lanjut", "Kirim Kode", "Dapatkan Kode", "Send Code", "Next", "Continue"]:
            loc = page.get_by_role("button", name=txt)
            if loc.count() > 0 and loc.first.is_visible():
                submit_btn = loc.first
                break
            loc2 = page.locator(f"button:has-text('{txt}')")
            if loc2.count() > 0 and loc2.first.is_visible():
                submit_btn = loc2.first
                break

        if submit_btn:
            submit_btn.click()
            time.sleep(3)
        else:
            email_input.first.press("Enter")
            time.sleep(3)

        # INVENTARISASI & SOLVE BAXIA PUZZLE DALAM LOOP
        solved = inspect_and_solve_baxia(page)
        
        if solved:
            # TUNGGU OTP DARI TUAN CIRO
            otp = wait_for_telegram_otp(timeout_sec=180)
            if otp:
                print(f"👉 Memasukkan OTP {otp}...")
                code_inputs = page.locator("input[maxlength='1'], input[autocomplete='one-time-code']")
                if code_inputs.count() >= len(otp):
                    for idx, ch in enumerate(otp):
                        code_inputs.nth(idx).fill(ch)
                        time.sleep(0.1)
                else:
                    otp_box = page.locator("input[placeholder*='kode' i], input[placeholder*='code' i], input[type='number'], input[type='tel']")
                    if otp_box.count() > 0 and otp_box.first.is_visible():
                        otp_box.first.fill(otp)
                        
                time.sleep(1)
                page.keyboard.press("Enter")
                time.sleep(6)
                
                page.screenshot(path="final_result.png")
                send_telegram_photo("final_result.png", "🎉 [STATUS AKHIR] Berhasil submit kode OTP!")
                
                cookies = context.cookies()
                cookies_dict = {c['name']: c['value'] for c in cookies}
                send_telegram_msg(f"🍪 Total session cookies didapat: {len(cookies_dict)}")
        else:
            send_telegram_msg("⚠️ Baxia mendeteksi anomali atau puzzle belum berhasil ditembus. Cek screenshot terbaru.")

        browser.close()

if __name__ == "__main__":
    main()
