import os
import sys
import time
import json
import math
import random
import urllib.request
import urllib.parse
from camoufox.sync_api import Camoufox
import cv2
import numpy as np

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TARGET_EMAIL = os.environ.get("TARGET_EMAIL", "tuanciroxtreme@gmail.com")
PROXY_URL = os.environ.get("WEBSHARE_ROTATING_PROXY")

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

def solve_mouse_travel(target_left: float, A=0.0769, B=0.003552) -> float:
    disc = A * A + 4 * B * target_left
    D = (-A + math.sqrt(disc)) / (2 * B)
    return D + random.uniform(1.0, 2.5)

def generate_human_whip_trajectory(distance: float):
    traj = []
    traj.append((0.0, 0.0, random.uniform(140.0, 200.0)))
    steps = random.randint(24, 30)

    for i in range(steps):
        p = (i + 1) / steps
        if p <= 0.30:
            eased = 0.10 * ((p / 0.30) ** 2)
        elif p <= 0.75:
            eased = 0.10 + 0.70 * ((p - 0.30) / 0.45)
        elif p <= 0.92:
            eased = 0.80 + 0.15 * math.sin(((p - 0.75) / 0.17) * (math.pi / 2))
        else:
            eased = 0.95 + 0.05 * ((p - 0.92) / 0.08)

        x = distance * eased
        drift = -0.5 - p * 3.2
        y = drift + math.sin(p * math.pi * 2.0) * random.uniform(1.2, 2.2)
        delay = random.uniform(18.0, 34.0)
        traj.append((round(x, 1), round(y, 1), round(delay, 1)))

    overshoot = random.uniform(2.0, 3.5)
    traj.append((round(distance + overshoot, 1), round(y, 1), round(random.uniform(40.0, 60.0), 1)))
    traj.append((round(distance, 1), 0.0, round(random.uniform(40.0, 70.0), 1)))
    return traj

def find_gap_with_cv(bg_path: str) -> float:
    img = cv2.imread(bg_path)
    if img is None:
        return 210.0
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
        
    return 210.0

def inspect_and_solve_baxia(page):
    print("🔍 Menginspeksi apakah Baxia Puzzle / #waf_nc_block muncul...")
    
    for _ in range(6):
        time.sleep(2)
        captcha_img = page.locator("#aliyunCaptcha-img, img.puzzle").first
        if captcha_img.count() > 0 and captcha_img.is_visible():
            break
            
    captcha_img = page.locator("#aliyunCaptcha-img, img.puzzle").first
    if captcha_img.count() == 0 or not captcha_img.is_visible():
        page.screenshot(path="screen_no_puzzle.png")
        send_telegram_photo("screen_no_puzzle.png", "📸 [BUKTI LAYAR] Status setelah tombol submit ditekan")
        print("ℹ️ Tidak ada elemen puzzle gambar yang aktif.")
        return False

    print("🚨 BAXIA PUZZLE AKTIF! Menggunakan Camoufox + Quadratic Model...")
    captcha_img.screenshot(path="puzzle_detected.png")
    send_telegram_photo("puzzle_detected.png", "🧩 [CAMOUFOX] Background Puzzle Terdeteksi")
    
    detected_x = find_gap_with_cv("puzzle_detected.png")
    box = captcha_img.bounding_box()
    img_real = cv2.imread("puzzle_detected.png")
    
    target_left = detected_x
    if box and img_real is not None:
        scale_ratio = box["width"] / img_real.shape[1]
        target_left = (detected_x * scale_ratio) - 2.0
        
    mouse_distance = solve_mouse_travel(target_left)
    print(f"📐 Target visual: {target_left:.1f}px -> RUMUS KUADRATIK MOUSE D: {mouse_distance:.1f}px")
    send_telegram_msg(f"🦊 [CAMOUFOX STEALTH] Gap={target_left:.1f}px -> D={mouse_distance:.1f}px")

    start_x = box["x"] + 25.0
    start_y = box["y"] + box["height"] + 25.0
    
    traj = generate_human_whip_trajectory(mouse_distance)
    
    page.mouse.move(start_x, start_y)
    time.sleep(0.2)
    page.mouse.down()
    
    for pt_x, pt_y, delay in traj:
        page.mouse.move(start_x + pt_x, start_y + pt_y)
        time.sleep(delay / 1000.0)
        
    time.sleep(0.35)
    page.mouse.up()
    print("✅ Balok puzzle selesai digeser via Camoufox C++ Engine!")
    time.sleep(4)
    
    page.screenshot(path="screen_after_slide.png")
    send_telegram_photo("screen_after_slide.png", "📸 [BUKTI GESER] Kondisi layar setelah balok dipasang")
    return True

def main():
    send_telegram_msg(f"🦊 [CAMOUFOX C++ STEALTH] Memulai Pertarungan Anti-Baxia di Virtual Display!\nTarget: {TARGET_EMAIL}")
    
    proxy_config = None
    if PROXY_URL:
        p = urllib.parse.urlparse(PROXY_URL)
        proxy_config = {
            "server": f"{p.scheme}://{p.hostname}:{p.port}",
            "username": p.username,
            "password": p.password
        }

    with Camoufox(
        headless=False,
        os="linux",
        proxy=proxy_config,
        geoip=True,
        i_know_what_im_doing=True
    ) as browser:
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        def handle_response(response):
            if "-verify" in response.url or "captcha" in response.url:
                try:
                    text = response.text()
                    if "T001" in text:
                        print("🔥 RESPONSE DETECTED: T001 (PASS)!")
                        send_telegram_msg("🎉 [BAXIA T001 PASS!] CAMOUFOX BERHASIL MENEMBUS BAXIA ALIBABA!")
                    elif "F015" in text:
                        print("⚠️ RESPONSE: F015")
                    elif "F001" in text:
                        print("⚠️ RESPONSE: F001")
                except Exception:
                    pass

        page.on("response", handle_response)

        print("1. Membuka https://chat.qwen.ai/...")
        page.goto("https://chat.qwen.ai/", wait_until="networkidle", timeout=60000)
        time.sleep(3)

        # Cari tombol Masuk / Sign In
        login_btn = None
        for txt in ["Masuk", "Sign in", "Log in", "Login"]:
            loc = page.get_by_role("button", name=txt)
            if loc.count() > 0 and loc.first.is_visible():
                login_btn = loc.first
                break
            loc2 = page.locator(f"button:has-text('{txt}'), a:has-text('{txt}')")
            if loc2.count() > 0 and loc2.first.is_visible():
                login_btn = loc2.first
                break

        if login_btn:
            print("👉 Mengklik tombol login...")
            login_btn.click()
            time.sleep(4)

        # Cari input email dengan aman
        email_loc = page.locator("input[placeholder*='email' i], input[type='email'], input[placeholder*='surel' i]")
        if email_loc.count() > 0 and email_loc.first.is_visible():
            print(f"👉 Mengisikan email target {TARGET_EMAIL}...")
            email_input = email_loc.first
            email_input.click()
            time.sleep(0.5)
            # Ketik satu per satu
            email_input.type(TARGET_EMAIL, delay=40)
            time.sleep(1)
            
            page.screenshot(path="camoufox_email_typed.png")
            send_telegram_photo("camoufox_email_typed.png", "📸 [STEP 2] Email sudah terketik di form")

            # Cari tombol Continue / Lanjutkan
            submit_btn = page.locator("button:has-text('Continue'), button:has-text('Lanjutkan'), button[type='submit']").first
            if submit_btn.is_visible():
                print("👉 Mengklik tombol Continue...")
                submit_btn.click()
                time.sleep(4)
            else:
                page.keyboard.press("Enter")
                time.sleep(4)

            # CEK & GESER BAXIA PUZZLE
            solved = inspect_and_solve_baxia(page)
            if solved:
                send_telegram_msg("📬 Balok puzzle telah digeser! Cek screenshot bukti geser di atas.")
            else:
                send_telegram_msg("⚠️ Puzzle tidak muncul atau form tidak berpindah. Cek screenshot bukti layar.")
        else:
            print("⚠️ Input email tidak terlihat di layar modal!")
            page.screenshot(path="no_email_input.png")
            send_telegram_photo("no_email_input.png", "📸 [ERROR] Input email tidak ditemukan di modal")

        time.sleep(5)

if __name__ == "__main__":
    main()
