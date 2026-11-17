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

def inspect_and_solve_baxia_multiround(page, max_rounds: int = 4):
    print(f"🔍 Memulai Multi-Round Solver Baxia (Maksimal {max_rounds} Ronde)...")
    
    for r in range(1, max_rounds + 1):
        time.sleep(3)
        captcha_img = page.locator("#aliyunCaptcha-img, img.puzzle").first
        
        # Cek apakah popup sudah hilang / form berganti ke input kode verifikasi
        if captcha_img.count() == 0 or not captcha_img.is_visible():
            print(f"🎉 POPUP PUZZLE HILANG DI RONDE {r}! VERIFIKASI LOLOS!")
            page.screenshot(path="verified_screen.png")
            send_telegram_photo("verified_screen.png", "🎉 [CENTANG HIJAU LOLOS!] Baxia Puzzle Berhasil Ditaklukkan!")
            return True

        print(f"⚔️ [RONDE {r}/{max_rounds}] Menghajar Puzzle...")
        captcha_img.screenshot(path=f"puzzle_round_{r}.png")
        send_telegram_photo(f"puzzle_round_{r}.png", f"🧩 [RONDE {r}] Gambar Puzzle Aktif")
        
        detected_x = find_gap_with_cv(f"puzzle_round_{r}.png")
        box = captcha_img.bounding_box()
        img_real = cv2.imread(f"puzzle_round_{r}.png")
        
        target_left = detected_x
        if box and img_real is not None:
            scale_ratio = box["width"] / img_real.shape[1]
            target_left = (detected_x * scale_ratio) - 2.0
            
        mouse_distance = solve_mouse_travel(target_left)
        print(f"📐 Target visual: {target_left:.1f}px -> RUMUS KUADRATIK MOUSE D: {mouse_distance:.1f}px")
        send_telegram_msg(f"🦊 [RONDE {r}] Gap={target_left:.1f}px -> Geser={mouse_distance:.1f}px")

        # Titik awal tombol handle (presisi 35px di bawah kiri gambar)
        start_x = box["x"] + 25.0
        start_y = box["y"] + box["height"] + 35.0

        # Tarik balok dengan kurva kinetik
        page.mouse.move(start_x, start_y)
        time.sleep(0.2)
        page.mouse.down()
        time.sleep(0.2)
        
        traj = generate_human_whip_trajectory(mouse_distance)
        for pt_x, pt_y, delay in traj:
            page.mouse.move(start_x + pt_x, start_y + pt_y)
            time.sleep(delay / 1000.0)
            
        time.sleep(0.4)
        page.mouse.up()
        print(f"✅ Ronde {r} selesai ditarik! Menunggu evaluasi respon...")
        time.sleep(4)
        
        page.screenshot(path=f"after_round_{r}.png")
        send_telegram_photo(f"after_round_{r}.png", f"📸 [HASIL RONDE {r}] Kondisi Layar Setelah Ditarik")

    # Cek akhir
    time.sleep(2)
    captcha_final = page.locator("#aliyunCaptcha-img, img.puzzle").first
    return captcha_final.count() == 0 or not captcha_final.is_visible()

def main():
    send_telegram_msg(f"🦊 [MULTI-ROUND SOLVER] Menyerang Balok Puzzle Tanpa Ampun!\nTarget: {TARGET_EMAIL}")
    
    with Camoufox(
        headless=False,
        os="linux",
        i_know_what_im_doing=True
    ) as browser:
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        print("1. Meluncur langsung ke URL Auth Qwen...")
        page.goto("https://chat.qwen.ai/auth?mode=signin", wait_until="load", timeout=60000)
        
        print("⏳ Menunggu form selesai render...")
        page.wait_for_selector("input", timeout=25000)
        time.sleep(2)

        email_loc = page.locator("input[placeholder*='email' i], input[type='email'], input[placeholder*='surel' i], input").first
        email_loc.click()
        time.sleep(0.5)
        
        print(f"👉 Mengetik email: {TARGET_EMAIL}...")
        email_loc.type(TARGET_EMAIL, delay=45)
        time.sleep(1)

        submit_btn = page.locator("button:has-text('Continue'), button:has-text('Lanjutkan'), button[type='submit']").first
        if submit_btn.is_visible():
            print("👉 Mengklik Continue...")
            submit_btn.click()
            time.sleep(4)
        else:
            page.keyboard.press("Enter")
            time.sleep(4)

        # EKSEKUSI MULTI-ROUND SOLVER
        solved = inspect_and_solve_baxia_multiround(page, max_rounds=4)
        
        if solved:
            send_telegram_msg(
                "📬 [BAXIA RESMI DILUMPUHKAN!]\n\n"
                "Semua ronde puzzle telah dilalui dan popup tertutup sempurna!\n"
                "Kode OTP baru sedang meluncur ke Gmail Tuan Ciro. Silakan periksa inbox sekarang! 🎉"
            )
        else:
            send_telegram_msg("⚠️ Ronde maksimal tercapai. Silakan periksa foto ronde terakhir di atas.")

        time.sleep(5)

if __name__ == "__main__":
    main()
