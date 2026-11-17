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
from chat_engine import send_prompt_and_extract_answer

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TARGET_EMAIL = os.environ.get("TARGET_EMAIL", "tuanciroxtreme@gmail.com")
PROMPT_ASK = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.environ.get("PROMPT_ASK", "")

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
    
    # Gunakan adaptive thresholding & histogram equalization untuk mengatasi foto terang/silau
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced_gray = clahe.apply(gray)
    
    # Multi-threshold Canny edge detection
    edges1 = cv2.Canny(enhanced_gray, 50, 150)
    edges2 = cv2.Canny(gray, 100, 200)
    edges = cv2.bitwise_or(edges1, edges2)
    edges[:, :65] = 0  # Potong bagian slider piece kiri
    
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        # Lubang puzzle Baxia standar memiliki rasio aspek persegi ~1:1 dengan ukuran 30-70px
        if 25 <= w <= 85 and 25 <= h <= 85:
            aspect = float(w) / h
            if 0.7 <= aspect <= 1.4:
                # Nilai skor berdasarkan kemiripan ke ukuran standar lubang (~45px)
                score = abs(w - 45) + abs(h - 45) + abs(w - h) * 2
                candidates.append((x, y, w, h, score))
            
    if candidates:
        candidates.sort(key=lambda item: item[4])
        target_x = candidates[0][0]
        print(f"🎯 OpenCV Enhanced CLAHE mendeteksi lubang puzzle di X={target_x} (w={candidates[0][2]}, h={candidates[0][3]})")
        return float(target_x)
        
    return 210.0

def wait_for_telegram_otp(timeout_sec: int = 180) -> str:
    send_telegram_msg(
        "⏳ [INPUT KODE OTP DIMULAI!]\n\n"
        "Balas chat bot Telegram ini SEKARANG dengan 6 digit kode OTP yang baru saja masuk ke Gmail Tuan Ciro!"
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
        time.sleep(2.5)
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update_id + 1}"
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read().decode())
                for item in data.get("result", []):
                    last_update_id = item["update_id"]
                    msg = item.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id"))
                    text = msg.get("text", "").strip()
                    
                    if chat_id == str(TELEGRAM_CHAT_ID) and text:
                        cleaned = "".join([c for c in text if c.isdigit()])
                        if len(cleaned) == 6:
                            send_telegram_msg(f"✅ OTP Diterima: {cleaned}. Memasukkan ke Qwen...")
                            return cleaned
        except Exception:
            pass

    send_telegram_msg("❌ Timeout menunggu OTP dari Telegram (180 detik).")
    return ""

def inspect_and_solve_baxia_multiround(page, max_rounds: int = 4):
    for r in range(1, max_rounds + 1):
        print(f"\n🔍 [RONDE {r}] Memeriksa status CAPTCHA / Baxia...")
        time.sleep(3)
        
        captcha_img = page.locator("#aliyunCaptcha-img, img.puzzle").first
        if captcha_img.count() == 0 or not captcha_img.is_visible():
            print(f"🎉 Tidak ada CAPTCHA yang terdeteksi di Ronde {r}. Lolos!")
            return True

        print(f"🧩 Ronde {r}: Baxia puzzle terdeteksi. Mengambil screenshot puzzle...")
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

        start_x = box["x"] + 25.0
        start_y = box["y"] + box["height"] + 35.0

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

    time.sleep(2)
    captcha_final = page.locator("#aliyunCaptcha-img, img.puzzle").first
    return captcha_final.count() == 0 or not captcha_final.is_visible()

def main():
    send_telegram_msg(f"🦊 [TAHAP 1/5] Inisialisasi Stealth Browser Camoufox...\nTarget: {TARGET_EMAIL}")
    
    with Camoufox(
        headless=False,
        os="linux",
        i_know_what_im_doing=True
    ) as browser:
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        
        # 1. Coba gunakan sesi tersimpan jika ada
        if os.path.exists("session_qwen.json"):
            try:
                with open("session_qwen.json") as f_s:
                    saved_c = json.load(f_s)
                    c_list = []
                    if isinstance(saved_c, dict):
                        for k, v in saved_c.items():
                            c_list.append({"name": k, "value": str(v), "domain": ".qwen.ai", "path": "/"})
                    elif isinstance(saved_c, list):
                        c_list = saved_c
                    context.add_cookies(c_list)
                    print(f"🍪 [INIT] Memuat {len(c_list)} cookies sesi dari session_qwen.json")
            except Exception as e:
                print(f"Warning init cookies: {e}")

        page = context.new_page()

        # Cek apakah sesi aktif langsung ke chat tanpa login ulang
        if os.path.exists("session_qwen.json"):
            print("🚀 Memeriksa status login langsung di chat.qwen.ai...")
            page.goto("https://chat.qwen.ai/", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            body_txt = page.evaluate("() => document.body.innerText")
            if not (("Masuk" in body_txt and "Daftar" in body_txt) or "Login" in body_txt):
                print("🎉 [AUTO-LOGIN PERSISTEN] Sesi aktif! Langsung mengeksekusi chat!")
                if PROMPT_ASK:
                    answer = send_prompt_and_extract_answer(page, PROMPT_ASK)
                    print("\n" + "="*40 + " QWEN FINAL ANSWER " + "="*40 + "\n")
                    print(answer)
                    print("\n" + "="*95 + "\n")
                    if answer:
                        send_telegram_msg(f"✨ [JAWABAN QWEN 4 MAX]:\n\n{answer}")
                return

        send_telegram_msg("🌐 [TAHAP 2/5] Membuka halaman login Qwen & mengisi email..."); print("1. Meluncur langsung ke URL Auth Qwen...")
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
            send_telegram_msg("🧩 [TAHAP 3/5] Puzzle Baxia sukses ditembus! Form OTP terbuka.\nMenunggu balasan kode OTP Tuan Ciro di chat ini...")
            
            # STANDBY MENERIMA OTP DARI TELEGRAM TUAN CIRO
            otp = wait_for_telegram_otp(timeout_sec=180)
            if otp:
                send_telegram_msg(f"⌨️ [TAHAP 4/5] Memasukkan OTP {otp} dan submit verifikasi..."); print(f"👉 Memasukkan OTP {otp} ke form...")
                time.sleep(2)
                
                code_inputs = page.locator("input[maxlength='1'], input[autocomplete='one-time-code']")
                if code_inputs.count() >= len(otp):
                    for idx, ch in enumerate(otp):
                        code_inputs.nth(idx).fill(ch)
                        time.sleep(0.1)
                else:
                    otp_box = page.locator("input[placeholder*='code' i], input[placeholder*='kode' i], input[type='number'], input[type='tel'], input").first
                    otp_box.fill(otp)

                time.sleep(1)
                page.keyboard.press("Enter")
                time.sleep(6)
                
                page.screenshot(path="final_logged_in.png")
                send_telegram_photo("final_logged_in.png", "🎉🎉 [SUKSES BESAR!!] STATUS BERHASIL LOGIN DI QWEN!!")
                
                # Ekspor cookies lengkap persisten
                cookies = context.cookies()
                send_telegram_msg(f"🍪 [VICTORY!] Berhasil merebut {len(cookies)} Session Cookies lengkap!")
                with open("session_qwen.json", "w") as f:
                    json.dump(cookies, f, indent=2)
                try:
                    import subprocess
                    subprocess.run(["gh", "secret", "set", "QWEN_SESSION_JSON", "--repo", "ciroxtreme/qwen-tantangan", "--body", json.dumps(cookies)], check=False)
                except Exception as e:
                    print(f"Notice sync secret: {e}")

                # Eksekusi prompt pertanyaan langsung
                if PROMPT_ASK:
                    send_telegram_msg(f"🧠 [QWEN RELAY] Mengirimkan pertanyaan ke Qwen 4 Max...")
                    answer = send_prompt_and_extract_answer(page, PROMPT_ASK)
                    print("\n" + "="*40 + " QWEN FINAL ANSWER " + "="*40 + "\n")
                    print(answer)
                    print("\n" + "="*95 + "\n")
                    if answer:
                        send_telegram_msg(f"✨ [JAWABAN QWEN 4 MAX]:\n\n{answer}")
        else:
            send_telegram_msg("⚠️ Belum berhasil melewati ronde puzzle.")

        time.sleep(5)

if __name__ == "__main__":
    main()
