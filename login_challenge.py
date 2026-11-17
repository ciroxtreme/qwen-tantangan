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
    traj.append((0.0, 0.0, random.uniform(140.0, 220.0)))
    steps = random.randint(20, 28)
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
        delay = random.uniform(18.0, 36.0)
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
        return 195.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    # Mask sisi kiri
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

def inspect_and_solve_baxia(page):
    print("🔍 Menginspeksi apakah Baxia Puzzle / #waf_nc_block muncul...")
    time.sleep(3)
    
    # Ambil screenshot kondisi saat ini
    page.screenshot(path="screen_current.png")
    send_telegram_photo("screen_current.png", "📸 [KONDISI LAYAR] Tepat setelah tombol Lanjutkan diklik")

    # Cek apakah ada div#waf_nc_block atau elemen aliyunCaptcha
    waf_block = page.locator("#waf_nc_block, #aliyunCaptcha-img, img.puzzle, div[class*='baxia']")
    has_waf = waf_block.count() > 0 and waf_block.first.is_visible()
    
    if not has_waf:
        print("ℹ️ Belum mendeteksi elemen #waf_nc_block secara visual langsung.")
        return False

    print("🚨 BAXIA PUZZLE TERKONFIRMASI! Mengekstrak gambar puzzle...")
    send_telegram_msg("🧩 [BAXIA PUZZLE TERLIHAT!] Memulai pemotongan gambar & kalkulasi SlideX...")

    captcha_img = page.locator("#aliyunCaptcha-img, img.puzzle").first
    if captcha_img.count() > 0:
        captcha_img.screenshot(path="puzzle_cut.png")
        send_telegram_photo("puzzle_cut.png", "🧩 [OPENCV INPUT] Background Puzzle Asli")
        
        detected_x = find_gap_with_cv("puzzle_cut.png")
        box = captcha_img.bounding_box()
        img_real = cv2.imread("puzzle_cut.png")
        distance = detected_x
        if box and img_real is not None:
            scale_ratio = box["width"] / img_real.shape[1]
            distance = detected_x * scale_ratio
            print(f"📐 Target geser: {distance:.1f}px (rasio {scale_ratio:.2f})")
    else:
        distance = 195.0

    # Cari tombol geser (slider button)
    slider_btn = page.locator("#aliyunCaptcha-btn, .nc_iconfont.btn_slide, div#waf_nc_block div[class*='btn'], div[class*='slider'] span, div:has-text('>>')").last
    btn_box = slider_btn.bounding_box()
    
    if not btn_box:
        # Coba tombol biru bawah
        slider_btn = page.locator("div#waf_nc_block div[role='slider']").first
        btn_box = slider_btn.bounding_box()

    if btn_box:
        start_x = btn_box["x"] + btn_box["width"] / 2
        start_y = btn_box["y"] + btn_box["height"] / 2
        
        print(f"⚡ MENGGESER BALOK PUZZLE: dari ({start_x:.1f}, {start_y:.1f}) sejauh {distance:.1f}px...")
        traj = generate_slider_trajectory(distance)
        
        page.mouse.move(start_x, start_y)
        time.sleep(0.15)
        page.mouse.down()
        for pt_x, pt_y, delay in traj:
            page.mouse.move(start_x + pt_x, start_y + pt_y)
            time.sleep(delay / 1000.0)
        time.sleep(0.2)
        page.mouse.up()
        
        print("✅ Balok puzzle selesai digeser! Menunggu respon verifikasi...")
        time.sleep(4)
        
        page.screenshot(path="screen_after_slide.png")
        send_telegram_photo("screen_after_slide.png", "📸 [HASIL GESER] Kondisi layar setelah puzzle digeser")
        return True

    return False

def main():
    send_telegram_msg(f"🚀 [QWEN-TANTANGAN] Investigasi & Eksekusi Puzzle Baxia!\nTarget: {TARGET_EMAIL}")
    
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

        # Klik tombol Lanjutkan
        print("4. Mengklik tombol Lanjutkan...")
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

        # INVENTARISASI & SELESAIKAN BAXIA PUZZLE
        puzzle_solved = inspect_and_solve_baxia(page)
        
        # Kirim update status ke Telegram Tuan Ciro
        if puzzle_solved:
            send_telegram_msg(
                "📬 [BAXIA PUZZLE SELESAI DIGESER!]\n\n"
                "Silakan cek inbox Gmail Tuan Ciro (termasuk folder Spam/Promotions).\n"
                "Email verifikasi Qwen yang baru seharusnya sudah terkirim sekarang!"
            )
        else:
            send_telegram_msg("⚠️ Puzzle tidak muncul atau tidak terdeteksi pada run ini. Silakan periksa foto screenshot.")

        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    main()
