import os
import sys
import time
import json
import math
import random
import urllib.request
import urllib.parse
import urllib.error
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import cv2
import numpy as np
from chat_engine import send_prompt_and_extract_answer

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TARGET_EMAIL = os.environ.get("TARGET_EMAIL", "tuanciroxtreme@gmail.com")
PROMPT_ASK = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.environ.get("PROMPT_ASK", "")

# Telegram mentok 4096 karakter/pesan — jawaban panjang yang dikirim utuh
# ditolak API ("message is too long") dan hilang begitu saja, padahal run-nya
# sukses. Jadi teks panjang dipecah jadi beberapa pesan berurutan.
TG_MSG_LIMIT = 4000

def split_telegram_text(text: str, limit: int = TG_MSG_LIMIT):
    """Pecah teks panjang jadi beberapa potong <= limit, diusahakan putus di
    batas paragraf/baris/spasi supaya kata tidak terbelah."""
    if len(text) <= limit:
        return [text]
    chunks = []
    rest = text
    while len(rest) > limit:
        cut = limit
        # Cari titik putus terbaik di 300 karakter terakhir sebelum batas
        window = rest[max(0, limit - 300):limit]
        for sep in ("\n\n", "\n", " "):
            idx = window.rfind(sep)
            if idx >= 0:
                cut = max(0, limit - 300) + idx + len(sep)
                break
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return chunks

def _send_one_chunk(url, payload, chunk_no, total):
    """Kirim 1 chunk; kalau Telegram balas 429, tunggu retry_after-nya lalu coba lagi (max 3x)."""
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
            urllib.request.urlopen(req, timeout=10)
            return True
        except urllib.error.HTTPError as e:
            wait = 2.0
            try:
                body = json.loads(e.read().decode("utf-8", "ignore"))
                wait = float(body.get("parameters", {}).get("retry_after", 2))
            except Exception:
                pass
            print(f"[TG] chunk {chunk_no}/{total}: 429 (coba {attempt}/3), tunggu {wait}s lalu retry")
            time.sleep(wait)
        except Exception as e:
            print(f"[TG Error] chunk {chunk_no}/{total}: {e}")
            return False
    print(f"[TG Error] chunk {chunk_no}/{total}: gagal setelah 3x retry (429)")
    return False

def send_telegram_msg(text: str):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print(f"[TG] {text}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = split_telegram_text(text)
    for i, chunk in enumerate(chunks):
        payload = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk
        }).encode("utf-8")
        _send_one_chunk(url, payload, i + 1, len(chunks))
        if len(chunks) > 1 and i < len(chunks) - 1:
            time.sleep(2.0)
    if len(chunks) > 1:
        print(f"[TG] Jawaban panjang dipecah jadi {len(chunks)} pesan (total {len(text)} karakter)")

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

SESSION_FILE = "session_qwen.json"
SESSION_PREV_FILE = "session_qwen.prev.json"
LOGGED_OUT_LINES = {"Log in", "Sign up", "Masuk", "Daftar"}
LOGGED_OUT_PHRASES = ("Log in to unlock", "Confirm your age to continue")

def detect_logged_out(page, context):
    """Deteksi logout dengan audit cookie teliti, cek API auth jika tersedia,
    dan tidak mudah false-positive."""
    cookies = context.cookies()
    cookie_info = []
    has_auth_cookie = False
    for c in cookies:
        name = c.get("name", "")
        exp = c.get("expires", -1)
        exp_str = f"{((exp - time.time()) / 86400):.1f} hari" if exp > 0 else "session"
        if name in ("refresh_token", "token", "acw_tc", "login_aliyunid_ticket", "baxia_token"):
            cookie_info.append(f"{name}({exp_str})")
        if name in ("refresh_token", "token", "login_aliyunid_ticket") and c.get("value"):
            has_auth_cookie = True

    if cookie_info:
        print(f"🔍 [AUDIT COOKIES] {', '.join(cookie_info)}")

    # Bukti keras: Cek API auth endpoint Qwen
    try:
        api_check_js = "async () => { const res = await fetch('/api/v1/user/info', { method: 'GET', credentials: 'include' }); return { status: res.status, ok: res.ok }; }"
        api_res = page.evaluate(api_check_js)
        status = api_res.get("status")
        if status in (401, 403):
            return True, f"API auth mengembalikan status HTTP {status} (Unauthorized)"
        elif status == 200:
            return False, ""
    except Exception:
        pass

    try:
        body_txt = page.evaluate("() => document.body.innerText") or ""
    except Exception:
        body_txt = ""

    # Catatan: Frasa seperti 'Log in to unlock' dan tombol 'Log in' sering muncul di banner/footer
    # bahkan saat sesi masih aktif atau sedang memproses. JANGAN anggap logout jika auth cookie masih ada!
    if not has_auth_cookie:
        for phrase in LOGGED_OUT_PHRASES:
            if phrase in body_txt:
                return True, f"auth cookie nihil & teks '{phrase}' terlihat di halaman"
        lines = {ln.strip() for ln in body_txt.splitlines()}
        hit = LOGGED_OUT_LINES & lines
        if hit:
            return True, f"auth cookie nihil & tombol {sorted(hit)} terlihat"

    return False, ""

def save_session(context):
    """Simpan storage_state Playwright resmi.
    PENTING: GitHub Actions Secret memiliki batas ukuran 64KB (65536 bytes).
    Jika storage_state lengkap (karena cache localStorage) melebihi 48KB,
    kita pangkas atau simpan list cookies murni agar lolos HTTP 422 secret limit."""
    try:
        if os.path.exists(SESSION_FILE) and os.path.getsize(SESSION_FILE) > 0:
            try:
                import shutil
                shutil.copy2(SESSION_FILE, SESSION_PREV_FILE)
            except Exception:
                pass

        # Ambil state dictionary dari Playwright
        state = context.storage_state()
        state_str = json.dumps(state)

        # Cek ukuran file state
        if len(state_str.encode('utf-8')) > 48000:
            print(f"⚠️ [SIZE GUARD] Storage state terlalu besar ({len(state_str)} bytes). Menyimpan cookies saja agar lolos limit 64KB GitHub Secret.")
            with open(SESSION_FILE, "w") as f:
                json.dump(context.cookies(), f)
        else:
            with open(SESSION_FILE, "w") as f:
                f.write(state_str)

        cookies = context.cookies()
        rt = next((c for c in cookies if c.get("name") == "refresh_token"), None)
        if rt and rt.get("expires", -1) > 0:
            days = (rt["expires"] - time.time()) / 86400
            print(f"💾 [SESSION] Berhasil disimpan ({len(cookies)} cookies, {os.path.getsize(SESSION_FILE)} bytes). refresh_token: {days:.1f} hari lagi.")
        else:
            print(f"💾 [SESSION] Berhasil disimpan ({len(cookies)} cookies, {os.path.getsize(SESSION_FILE)} bytes).")
    except Exception as e:
        print(f"⚠️ Gagal save storage_state, fallback ke cookies: {e}")
        try:
            with open(SESSION_FILE, "w") as f:
                json.dump(context.cookies(), f)
        except Exception as e2:
            print(f"❌ Error save fallback cookies: {e2}")

def drop_session():
    """JANGAN langsung hapus file sesi agar secret tidak putus permanen.
    Cukup catat warning."""
    print("⚠️ [SESSION DROP GUARD] Menolak hapus disk session agar rantai secret tidak putus.")

def fail_run(reason: str):
    print(f"❌ {reason}")
    send_telegram_msg(f"❌ [QWEN GAGAL] {reason}")
    sys.exit(1)


def main():
    send_telegram_msg(f"🚀 [TAHAP 1/5] Inisialisasi Playwright Stealth via WARP...\nTarget: {TARGET_EMAIL}")
    
    proxy_cfg = None
    webshare_proxy = os.getenv("WEBSHARE_ROTATING_PROXY", "").strip()
    if webshare_proxy:
        if "@" in webshare_proxy:
            # format: http://user:pass@host:port
            auth_part, host_part = webshare_proxy.split("://")[1].split("@")
            user, pwd = auth_part.split(":")
            proto = webshare_proxy.split("://")[0]
            proxy_cfg = {
                "server": f"{proto}://{host_part}",
                "username": user,
                "password": pwd
            }
        else:
            proxy_cfg = {"server": webshare_proxy}
        print(f"✅ Menggunakan Webshare Proxy dari Secret: {proxy_cfg['server']} (Auth: Yes)")
    else:
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(("127.0.0.1", 40000))
            s.close()
            proxy_cfg = {"server": "socks5://127.0.0.1:40000"}
            print("✅ Cloudflare WARP proxy terdeteksi di port 40000")
        except Exception:
            pass

    with Stealth().use_sync(sync_playwright()) as p:
        browser_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,900"
        ]
        launch_kwargs = {"headless": True, "args": browser_args}
        if proxy_cfg:
            launch_kwargs["proxy"] = proxy_cfg

        browser = p.chromium.launch(**launch_kwargs)

        ctx_kwargs = {
            "viewport": {"width": 1280, "height": 900},
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        }

        # Coba muat storage_state (atau fallback ke .prev.json)
        for cand_file in (SESSION_FILE, SESSION_PREV_FILE):
            if os.path.exists(cand_file) and os.path.getsize(cand_file) > 0:
                try:
                    with open(cand_file) as f_test:
                        test_data = json.load(f_test)
                    if isinstance(test_data, dict) and ("cookies" in test_data or "origins" in test_data):
                        ctx_kwargs["storage_state"] = cand_file
                        print(f"📦 [STORAGE_STATE] Context diinisialisasi dari: {cand_file}")
                        break
                except Exception as e:
                    print(f"Warning baca {cand_file}: {e}")

        context = browser.new_context(**ctx_kwargs)

        # Fallback jika session file lama berformat list cookies biasa
        if not ctx_kwargs.get("storage_state") and os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE) as f_s:
                    saved_c = json.load(f_s)
                    c_list = []
                    if isinstance(saved_c, list):
                        c_list = saved_c
                    elif isinstance(saved_c, dict) and "cookies" not in saved_c:
                        for k, v in saved_c.items():
                            c_list.append({"name": k, "value": str(v), "domain": ".qwen.ai", "path": "/"})
                    if c_list:
                        context.add_cookies(c_list)
                        print(f"🍪 [LEGACY COOKIES] Memuat {len(c_list)} cookies sesi dari session_qwen.json")
            except Exception as e:
                print(f"Warning init fallback cookies: {e}")

        page = context.new_page()

        # Cek apakah sesi aktif langsung ke chat tanpa login ulang
        if os.path.exists(SESSION_FILE):
            print("🚀 Memeriksa status login langsung di chat.qwen.ai...")
            page.goto("https://chat.qwen.ai/", wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(3)
            is_logged_out, why = detect_logged_out(page, context)

            if not is_logged_out:
                print("🎉 [AUTO-LOGIN PERSISTEN] Sesi aktif! Menyimpan cookie terbaru (Keep-Alive)...")
                save_session(context)

                if PROMPT_ASK:
                    answer = send_prompt_and_extract_answer(page, PROMPT_ASK)
                    # Simpan token SEGERA setelah chat, sebelum evaluasi/drop apa pun
                    save_session(context)
                    print("\n" + "="*40 + " QWEN FINAL ANSWER " + "="*40 + "\n")
                    print(answer)
                    print("\n" + "="*95 + "\n")
                    is_logged_out, why = detect_logged_out(page, context)
                    if is_logged_out:
                        fail_run(f"Sesi ter-logout saat chat ({why}). Butuh refresh/login ulang.")
                    if not answer:
                        fail_run("Jawaban Qwen kosong.")
                    send_telegram_msg(f"✨ [JAWABAN QWEN 4 MAX]:\n\n{answer}")
                return
            else:
                print(f"⚠️ [SESI KEDALUWARSA / LOGOUT] {why}. Mengaktifkan flow re-login & kirim notifikasi ke Telegram...")
                send_telegram_msg(f"⚠️ [QWEN ALERT] Sesi cookie Qwen kedaluwarsa atau ter-logout ({why}). Memulai prosedur re-login interaktif via email...")
                drop_session()

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
        else:
            print("👉 Menekan Enter pada input email...")
            email_loc.press("Enter")
        time.sleep(5)

        # Ambil screenshot kondisi form setelah submit email
        page.screenshot(path="after_email_submit.png")
        send_telegram_photo("after_email_submit.png", "📸 [BUKTI SUBMIT EMAIL] Status halaman setelah memasukkan email")

        # Cek apakah captcha muncul atau langsung form OTP
        captcha_img = page.locator("#aliyunCaptcha-img, img.puzzle").first
        if captcha_img.is_visible():
            print("🧩 Captcha Baxia muncul, menjalankan solver...")
            solved = inspect_and_solve_baxia_multiround(page, max_rounds=4)
        else:
            print("Notice: Tidak ada captcha yang muncul.")
            solved = True

        # Validasi ketat: Form OTP benar-benar harus terlihat sebelum minta OTP ke user
        time.sleep(3)
        page.screenshot(path="auth_current_view.png")
        otp_visible = False
        try:
            otp_locator = page.locator("input[maxlength='1'], input[autocomplete='one-time-code'], input[placeholder*='code' i], input[placeholder*='kode' i]")
            if otp_locator.first.is_visible(timeout=5000):
                otp_visible = True
        except Exception:
            pass

        if not otp_visible:
            # Kirim screenshot jika form OTP belum terbuka agar jelas statusnya
            send_telegram_photo("auth_current_view.png", "⚠️ [PERHATIAN] Form OTP belum terbuka di Qwen. Memeriksa status tombol...")
            # Coba klik submit sekali lagi via JS jika tombol Continue belum terpicu
            page.evaluate('''() => {
                const btns = document.querySelectorAll("button");
                for (const b of btns) {
                    const txt = (b.innerText || "").toLowerCase();
                    if (txt.includes("continue") || txt.includes("lanjutkan") || txt.includes("next")) {
                        b.click();
                        break;
                    }
                }
            }''')
            time.sleep(5)
            page.screenshot(path="auth_current_view.png")
            try:
                if page.locator("input[maxlength='1'], input[autocomplete='one-time-code']").first.is_visible(timeout=5000):
                    otp_visible = True
            except Exception:
                pass

        if solved and otp_visible:
            send_telegram_photo("auth_current_view.png", "🧩 [TAHAP 3/5] Form OTP resmi terbuka & email kode terkirim!")
            # STANDBY MENERIMA OTP DARI TELEGRAM TUAN CIRO
            otp = wait_for_telegram_otp(timeout_sec=180)
        else:
            send_telegram_photo("auth_current_view.png", "❌ [GAGAL] Form OTP belum berhasil terpicu dari Qwen. Screenshot terlampir di atas.")
            otp = ""

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
            
            is_logged_out, why = detect_logged_out(page, context)
            if is_logged_out:
                fail_run(f"Login OTP belum berhasil ({why}).")
            save_session(context)
            send_telegram_msg("🍪 [VICTORY!] Login berhasil, sesi baru disimpan.")

            # Eksekusi prompt pertanyaan langsung
            if PROMPT_ASK:
                send_telegram_msg(f"🧠 [QWEN RELAY] Mengirimkan pertanyaan ke Qwen 4 Max...")
                answer = send_prompt_and_extract_answer(page, PROMPT_ASK)
                # Simpan token SEGERA setelah chat
                save_session(context)
                print("\n" + "="*40 + " QWEN FINAL ANSWER " + "="*40 + "\n")
                print(answer)
                print("\n" + "="*95 + "\n")
                if not answer:
                    fail_run("Jawaban Qwen kosong setelah login ulang.")
                send_telegram_msg(f"✨ [JAWABAN QWEN 4 MAX]:\n\n{answer}")
        else:
            fail_run("Belum berhasil login: OTP tidak diterima atau form OTP tidak muncul.")

        time.sleep(5)

if __name__ == "__main__":
    main()
