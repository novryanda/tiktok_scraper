"""
tiktok_api_server.py
====================
REST API wrapper untuk TikTok Scraper (Video Comments + Profile + Auth).

Sama seperti instagram_api_server.py tapi untuk TikTok:
  - Cookie session tersimpan di session/tt_session.json
  - Output disimpan ke output_tiktok/ dan output_tiktok_profiles/
  - Subprocess isolation: fresh browser per request
  - Cascade strategy per engine (CDP → DOM untuk komentar, Metadata → DOM → HTML untuk profil)

Run: python tiktok_api_server.py

Endpoints:
  AUTH:
    POST   /api/v1/auth/login          — Buka browser untuk login manual
    GET    /api/v1/auth/status         — Cek status login
    POST   /api/v1/auth/logout         — Hapus session
    GET    /api/v1/auth/session-info   — Info detail session cookies

  SCRAPE VIDEO:
    POST   /api/v1/scrape/video        — Scrape komentar single video
    POST   /api/v1/scrape/videos/batch — Batch scrape komentar

  SCRAPE PROFILE:
    POST   /api/v1/scrape/profile      — Scrape profil by username
    POST   /api/v1/scrape/profile/url  — Scrape profil by URL
    POST   /api/v1/scrape/profiles/batch      — Batch scrape profil (username)
    POST   /api/v1/scrape/profiles/batch/url  — Batch scrape profil (URL)

  ANALYTICS / GROWTH:
    GET    /api/v1/profiles                   — List semua profil ter-track
    GET    /api/v1/profiles/<username>        — Data profil + snapshot terakhir
    GET    /api/v1/profiles/<username>/history — History snapshots
    GET    /api/v1/profiles/<username>/growth  — Analisis pertumbuhan
    POST   /api/v1/profiles/<username>/track   — Manual tambah snapshot

  HEALTH:
    GET    /api/v1/health
"""
import os
import sys
import json
import time
import random
import re
import traceback
import threading
import asyncio
import subprocess
import tempfile
import shutil
from datetime import datetime, timedelta
from typing import Optional, List
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS
from colorama import Fore, init

app = Flask(__name__)
CORS(app)
init(autoreset=True)

from tiktok_search_deep_endpoints import tiktok_deep_search_router
app.register_blueprint(tiktok_deep_search_router)

# ── CONFIG ─────────────────────────────────────────────────────────────────
API_PORT   = int(os.getenv("TIKTOK_API_PORT", 5001))
API_HOST   = os.getenv("TIKTOK_API_HOST", "0.0.0.0")
DEBUG_MODE = os.getenv("DEBUG", "False").lower() == "true"

OUTPUT_VIDEO_DIR   = "output_tiktok"
OUTPUT_PROFILE_DIR = "output_tiktok_profiles"
TRACKING_FILE      = os.path.join(OUTPUT_PROFILE_DIR, "growth_tracking.json")

TIKTOK_CHROME_PROFILE = os.path.join(os.getcwd(), "tiktok_chrome_real_profile")

os.makedirs(OUTPUT_VIDEO_DIR,   exist_ok=True)
os.makedirs(OUTPUT_PROFILE_DIR, exist_ok=True)
os.makedirs(TIKTOK_CHROME_PROFILE, exist_ok=True)


# ── HELPERS ────────────────────────────────────────────────────────────────

def success_response(data: dict, message: str = "Success") -> dict:
    return {
        "success":   True,
        "message":   message,
        "timestamp": datetime.now().isoformat(),
        "data":      data,
    }


def error_response(message: str, status_code: int = 400, details: dict = None) -> tuple:
    resp = {
        "success":   False,
        "message":   message,
        "timestamp": datetime.now().isoformat(),
        "error":     details or {},
    }
    return jsonify(resp), status_code


def require_json_fields(*fields):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return error_response("Content-Type must be application/json", 415)
            data    = request.get_json()
            missing = [field for field in fields if field not in data or data[field] in (None, "")]
            if missing:
                return error_response(f"Missing required fields: {', '.join(missing)}", 400)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def clean_tiktok_url(url: str) -> str:
    """Bersihkan URL TikTok dari query string."""
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    # Pertahankan URL tapi hapus query string untuk URL non-shortlink
    if "vt.tiktok.com" not in url and "/t/" not in url:
        url = url.split("?")[0].rstrip("/")
    return url


def extract_username_from_url(url: str) -> Optional[str]:
    """Extract username dari URL TikTok."""
    patterns = [
        r'tiktok\.com/@([^/?&#\s]+)',
        r'tiktok\.com/@([^/?&#\s]+)/',
    ]
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            username = match.group(1).strip().lstrip("@").lower()
            # Filter bukan path khusus
            if username not in ("foryou", "following", "explore", "live", "upload"):
                return username
    return None


def save_json_output(data: dict, filename: str, output_dir: str) -> str:
    """Simpan dict ke output/<filename>. Return nama file."""
    os.makedirs(output_dir, exist_ok=True)
    fp = os.path.join(output_dir, filename)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return filename


def load_tracking_data() -> dict:
    """Load growth tracking JSON."""
    if not os.path.exists(TRACKING_FILE):
        return {}
    try:
        with open(TRACKING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_tracking_data(data: dict):
    """Save growth tracking JSON."""
    os.makedirs(OUTPUT_PROFILE_DIR, exist_ok=True)
    with open(TRACKING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# AUTH / LOGIN STATE
# ═══════════════════════════════════════════════════════════════════════════

_login_state = {
    "is_running":       False,
    "browser_opened_at": None,
    "login_detected":   False,
    "username":         None,
    "last_error":       None,
}
_state_lock = threading.Lock()


def update_login_state(**kwargs):
    with _state_lock:
        _login_state.update(kwargs)


def get_login_state():
    with _state_lock:
        return dict(_login_state)


def run_login_browser_async(timeout_minutes: int = 5, headless: bool = False):
    """Jalankan browser Playwright di background thread untuk login manual TikTok."""

    async def _login_worker():
        from playwright.async_api import async_playwright

        print(Fore.CYAN + "\n🌐 [Login Worker] Membuka browser Chrome untuk TikTok...")
        update_login_state(
            is_running=True,
            browser_opened_at=datetime.now().isoformat(),
            login_detected=False,
            last_error=None,
            username=None,
        )

        try:
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    TIKTOK_CHROME_PROFILE,
                    channel="chrome",
                    headless=headless,
                    args=[
                        "--start-maximized",
                        "--disable-notifications",
                        "--disable-blink-features=AutomationControlled",
                        "--lang=id-ID",
                    ],
                    viewport=None,
                    locale="id-ID",
                    timezone_id="Asia/Jakarta",
                    bypass_csp=True,
                )

                page = context.pages[0] if context.pages else await context.new_page()

                # Inject existing cookies kalau ada
                try:
                    from tiktok_cookie_injector import has_valid_session, inject_cookies_async
                    if has_valid_session():
                        n = await inject_cookies_async(context)
                        print(Fore.GREEN + f"   🍪 {n} cookies diinject dari session")
                except Exception as ce:
                    print(Fore.YELLOW + f"   ⚠️  Cookie inject skip: {ce}")

                await page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)

                # Cek apakah sudah login
                cookies      = await context.cookies("https://www.tiktok.com")
                cookie_names = {c["name"] for c in cookies}

                if "sessionid" in cookie_names:
                    print(Fore.GREEN + "\n✅ [Login Worker] Sudah login sebelumnya!")
                    await _save_cookies_from_context(context, cookies)
                    update_login_state(login_detected=True)
                    await asyncio.sleep(3)
                    await context.close()
                    return

                print(Fore.YELLOW + "\n⚠️  [Login Worker] Menunggu login manual...")

                max_wait = timeout_minutes * 12
                logged_in = False

                for i in range(max_wait):
                    await asyncio.sleep(5)
                    current_url  = page.url
                    cookies      = await context.cookies("https://www.tiktok.com")
                    cookie_names = {c["name"] for c in cookies}

                    print(f"   [{i+1}/{max_wait}] {current_url[:60]}", end="\r")

                    if "sessionid" in cookie_names:
                        logged_in = True
                        print(Fore.GREEN + f"\n\n✅ [Login Worker] Login berhasil!")

                        # Coba ambil username
                        try:
                            url_parts = current_url.replace("https://www.tiktok.com/@", "").split("/")
                            if url_parts and url_parts[0] and "@" not in url_parts[0]:
                                update_login_state(username=url_parts[0])
                        except Exception:
                            pass
                        break

                if not logged_in:
                    print(Fore.RED + "\n\n❌ [Login Worker] Timeout")
                    update_login_state(last_error="Timeout: user tidak login dalam waktu yang ditentukan")
                    await context.close()
                    return

                print(Fore.YELLOW + "\n⏳ [Login Worker] Menyimpan session (8 detik)...")
                await asyncio.sleep(8)

                # Simpan cookies ke session file
                cookies = await context.cookies("https://www.tiktok.com")
                await _save_cookies_from_context(context, cookies)
                update_login_state(login_detected=True)
                print(Fore.GREEN + "✅ [Login Worker] Session tersimpan!")
                await context.close()

        except Exception as e:
            print(Fore.RED + f"\n❌ [Login Worker] Error: {e}")
            update_login_state(last_error=str(e))
            traceback.print_exc()
        finally:
            update_login_state(is_running=False)

    async def _save_cookies_from_context(context, cookies):
        try:
            from tiktok_cookie_injector import save_session
            tiktok_cookies = [
                {
                    "name":           c["name"],
                    "value":          c["value"],
                    "domain":         c.get("domain", ".tiktok.com"),
                    "path":           c.get("path", "/"),
                    "httpOnly":       c.get("httpOnly", False),
                    "secure":         c.get("secure", True),
                    "sameSite":       c.get("sameSite", "Lax"),
                    "expirationDate": c.get("expires", -1),
                }
                for c in cookies
                if "tiktok.com" in c.get("domain", "")
            ]
            save_session(tiktok_cookies, note="auto_saved_from_api_login")
            print(Fore.GREEN + f"   💾 {len(tiktok_cookies)} cookies tersimpan ke session/tt_session.json")
        except Exception as se:
            print(Fore.YELLOW + f"   ⚠️  Gagal simpan session: {se}")

    def _thread_target():
        asyncio.run(_login_worker())

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    return thread


# ═══════════════════════════════════════════════════════════════════════════
# SUBPROCESS HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def run_video_scraper_subprocess(url: str, max_comments: int) -> dict:
    """Jalankan TikTok video scraper sebagai subprocess (fresh browser per request)."""

    script = f"""
import sys
sys.path.insert(0, r'{os.getcwd()}')

from tiktok_scraper_v52 import TikTokScraperV52
import json

with TikTokScraperV52() as scraper:
    result = scraper.scrape_post_comments("{url}", {max_comments})
    print(json.dumps(result, ensure_ascii=False, default=str))
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(script)
        script_path = f.name

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"]       = "1"

        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=os.getcwd(),
            encoding="utf-8",
            env=env,
        )

        if result.returncode != 0:
            stderr = result.stderr[-2000:] if result.stderr else ""
            raise Exception(f"Video scraper error:\n{stderr}")

        lines = result.stdout.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    return json.loads(line)
                except Exception:
                    continue
        raise Exception("No valid JSON output from video scraper")

    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


def run_profile_scraper_subprocess(username: str, source_url: str = None) -> dict:
    """Jalankan TikTok profile scraper sebagai subprocess (fresh browser per request)."""

    source_url_literal = json.dumps(source_url) if source_url else "None"

    script = f"""
import sys
sys.path.insert(0, r'{os.getcwd()}')

from tiktok_profile_scraper import TikTokProfileScraper
import json

with TikTokProfileScraper() as scraper:
    result = scraper.scrape_profile("{username}")
    if {source_url is not None}:
        if result.get("data"):
            result["data"]["source_url"] = {source_url_literal}
        result["source_url"] = {source_url_literal}
    print(json.dumps(result, ensure_ascii=False, default=str))
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(script)
        script_path = f.name

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"]       = "1"

        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=os.getcwd(),
            encoding="utf-8",
            env=env,
        )

        if result.returncode != 0:
            stderr = result.stderr[-2000:] if result.stderr else ""
            raise Exception(f"Profile scraper error:\n{stderr}")

        lines = result.stdout.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    return json.loads(line)
                except Exception:
                    continue
        raise Exception("No valid JSON output from profile scraper")

    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


def save_profile_to_tracking(profile_result: dict):
    """Simpan hasil scrape profil ke growth_tracking.json."""
    try:
        data      = profile_result.get("data", {}) or {}
        username  = data.get("username") or profile_result.get("username", "")
        if not username:
            return

        tracking  = load_tracking_data()
        scraped_at = data.get("scraped_at", datetime.now().isoformat())

        if username not in tracking:
            tracking[username] = {
                "username":      username,
                "first_tracked": scraped_at,
                "history":       [],
            }

        snapshot = {
            "scraped_at":   scraped_at,
            "followers":    data.get("followers", 0),
            "following":    data.get("following", 0),
            "total_likes":  data.get("total_likes", 0),
            "total_videos": data.get("total_videos", 0),
        }

        # Hindari duplikasi pada hari yang sama
        today = scraped_at[:10]
        history = tracking[username].get("history", [])
        existing_today = [h for h in history if h.get("scraped_at", "")[:10] == today]
        if existing_today:
            # Update entry hari ini
            for h in history:
                if h.get("scraped_at", "")[:10] == today:
                    h.update(snapshot)
                    break
        else:
            tracking[username]["history"].append(snapshot)

        tracking[username]["last_tracked"] = scraped_at
        save_tracking_data(tracking)
        print(Fore.GREEN + f"   💾 Tracking updated: @{username}")
    except Exception as e:
        print(Fore.YELLOW + f"   ⚠️  Tracking save warning: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS — AUTH
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/v1/auth/login", methods=["POST"])
def trigger_login():
    data            = request.get_json() or {}
    timeout_minutes = data.get("timeout_minutes", 5)
    headless        = data.get("headless", False)

    state = get_login_state()
    if state["is_running"]:
        return error_response(
            "Browser login sedang berjalan. Cek status dengan GET /api/v1/auth/status",
            409,
            {"browser_opened_at": state["browser_opened_at"]},
        )

    run_login_browser_async(timeout_minutes=timeout_minutes, headless=headless)
    time.sleep(2)

    return jsonify(success_response({
        "browser_started":    True,
        "headless":           headless,
        "timeout_minutes":    timeout_minutes,
        "profile_path":       TIKTOK_CHROME_PROFILE,
        "session_file":       "session/tt_session.json",
        "alternative":        "Gunakan tiktok_session_manager.py untuk import cookies dari Cookie-Editor",
        "instructions": [
            "Browser Chrome akan terbuka",
            "Login manual ke TikTok",
            "Selesaikan verifikasi jika diminta",
            "Tunggu halaman beranda muncul",
            "Cek status dengan GET /api/v1/auth/status",
        ],
    }, f"Browser login dibuka. Timeout: {timeout_minutes} menit"))


@app.route("/api/v1/auth/status", methods=["GET"])
def check_login_status():
    state = get_login_state()

    # Cek session file
    try:
        from tiktok_cookie_injector import has_valid_session, get_session_info
        session_valid = has_valid_session()
        session_info  = get_session_info()
    except Exception:
        session_valid = False
        session_info  = {}

    # Cek profile dir
    profile_valid = os.path.exists(TIKTOK_CHROME_PROFILE) and bool(os.listdir(TIKTOK_CHROME_PROFILE))

    response_data = {
        "is_running":         state["is_running"],
        "login_detected":     state["login_detected"],
        "username":           state["username"],
        "browser_opened_at":  state["browser_opened_at"],
        "last_error":         state["last_error"],
        "session_file_valid": session_valid,
        "session_info":       session_info,
        "profile_dir_exists": profile_valid,
        "profile_path":       TIKTOK_CHROME_PROFILE,
        "is_logged_in":       session_valid or (state["login_detected"] and profile_valid),
    }

    if session_valid:
        msg = "Session valid — siap scraping"
    elif state["login_detected"]:
        msg = "Login via browser terdeteksi"
    elif state["last_error"]:
        msg = f"Error: {state['last_error']}"
    else:
        msg = "Belum login"

    return jsonify(success_response(response_data, msg))


@app.route("/api/v1/auth/session-info", methods=["GET"])
def get_session_detail():
    try:
        from tiktok_cookie_injector import get_session_info, has_valid_session
        info = get_session_info()
        return jsonify(success_response(info, "Session info retrieved"))
    except Exception as e:
        return error_response(f"Error: {str(e)}", 500)


@app.route("/api/v1/auth/logout", methods=["POST"])
def logout():
    data       = request.get_json() or {}
    hard_reset = data.get("hard_reset", False)

    state = get_login_state()
    if state["is_running"]:
        return error_response("Browser sedang berjalan. Tidak bisa logout saat ini.", 409)

    try:
        from tiktok_cookie_injector import delete_session, SESSION_FILE
        deleted_session = delete_session()

        if hard_reset:
            # Hapus juga Chrome profile
            if os.path.exists(TIKTOK_CHROME_PROFILE):
                shutil.rmtree(TIKTOK_CHROME_PROFILE)
                os.makedirs(TIKTOK_CHROME_PROFILE, exist_ok=True)
            update_login_state(login_detected=False, username=None, last_error=None, browser_opened_at=None)
            return jsonify(success_response({
                "session_deleted":  deleted_session,
                "profile_reset":    True,
                "profile_path":     TIKTOK_CHROME_PROFILE,
            }, "Hard reset berhasil. Login baru diperlukan."))
        else:
            update_login_state(login_detected=False, username=None)
            return jsonify(success_response({
                "session_deleted": deleted_session,
                "session_file":    SESSION_FILE,
            }, "Logout berhasil. Session dihapus."))

    except Exception as e:
        return error_response(f"Logout failed: {str(e)}", 500)


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS — SCRAPE VIDEO
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/v1/scrape/video", methods=["POST"])
@require_json_fields("url")
def scrape_single_video():
    data         = request.get_json()
    url          = clean_tiktok_url(data["url"])
    max_comments = data.get("max_comments", 100)

    print(Fore.CYAN + f"\n🎵 Scraping video: {url}")
    print(Fore.CYAN + f"   Max comments: {max_comments}")
    print(Fore.YELLOW + "   ⏳ Estimasi waktu ~60-120 detik...")

    try:
        t_start = time.time()
        result  = run_video_scraper_subprocess(url, max_comments)
        t_elapsed = time.time() - t_start

        result["_meta"] = {
            "elapsed_seconds":      round(t_elapsed, 2),
            "requested_max":        max_comments,
            "url_cleaned":          url,
            "comments_per_second":  round(
                result.get("comments_count", 0) / t_elapsed, 2
            ) if t_elapsed > 0 else 0,
        }

        filename = f"api_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_json_output(result, filename, OUTPUT_VIDEO_DIR)
        result["_meta"]["saved_file"] = filename

        msg = f"Scraped {result.get('comments_count', 0)} comments via [{result.get('method', '?')}]"
        return jsonify(success_response(result, msg))

    except Exception as e:
        traceback.print_exc()
        return error_response(f"Scrape failed: {str(e)}", 500, {"traceback": traceback.format_exc()})


@app.route("/api/v1/scrape/videos/batch", methods=["POST"])
@require_json_fields("urls")
def scrape_batch_videos():
    data          = request.get_json()
    urls          = [clean_tiktok_url(u) for u in data["urls"]]
    max_comments  = data.get("max_comments", 100)
    delay_between = data.get("delay_between", 15)

    if not isinstance(urls, list) or len(urls) == 0:
        return error_response("'urls' harus berupa array non-kosong", 400)

    results  = []
    t_total  = time.time()

    for i, url in enumerate(urls):
        print(Fore.CYAN + f"\n[{i+1}/{len(urls)}] {url[:60]}")
        try:
            r = run_video_scraper_subprocess(url, max_comments)
            results.append({"url": url, "success": True, "data": r})
        except Exception as e:
            results.append({"url": url, "success": False, "error": str(e)})

        if i < len(urls) - 1:
            delay = delay_between + random.randint(5, 15)
            print(Fore.YELLOW + f"   ⏳ Jeda {delay}s...")
            time.sleep(delay)

    summary = {
        "total":           len(urls),
        "success":         sum(1 for r in results if r["success"]),
        "failed":          sum(1 for r in results if not r["success"]),
        "elapsed_seconds": round(time.time() - t_total, 2),
        "results":         results,
    }

    filename = f"api_batch_videos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_json_output(summary, filename, OUTPUT_VIDEO_DIR)
    summary["saved_file"] = filename

    return jsonify(success_response(
        summary,
        f"Batch complete: {summary['success']}/{summary['total']} success",
    ))


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS — SCRAPE PROFILE
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/v1/scrape/profile", methods=["POST"])
@require_json_fields("username")
def scrape_single_profile():
    data          = request.get_json()
    username      = data["username"].strip().lstrip("@").lower()
    save_tracking = data.get("save_tracking", True)
    return _do_scrape_profile(username, save_tracking)


@app.route("/api/v1/scrape/profile/url", methods=["POST"])
@require_json_fields("url")
def scrape_profile_by_url():
    data          = request.get_json()
    url           = data["url"].strip()
    save_tracking = data.get("save_tracking", True)

    username = extract_username_from_url(url)
    if not username:
        return error_response(
            f"Tidak bisa extract username dari URL: {url}. "
            "Format: https://www.tiktok.com/@username",
            400,
        )

    print(Fore.CYAN + f"\n🔗 URL: {url}")
    print(Fore.CYAN + f"👤 Extracted username: @{username}")

    return _do_scrape_profile(username, save_tracking, source_url=url)


def _do_scrape_profile(username: str, save_tracking: bool, source_url: str = None):
    """Jalankan subprocess untuk scrape profil TikTok."""
    print(Fore.CYAN + f"\n🌐 [Subprocess] Scraping TikTok profile: @{username}")
    print(Fore.YELLOW + "   ⏳ Estimasi ~20-40 detik...")

    try:
        t_start   = time.time()
        result    = run_profile_scraper_subprocess(username, source_url)
        t_elapsed = time.time() - t_start

        result["_meta"] = {
            "elapsed_seconds": round(t_elapsed, 2),
            "mode":            "subprocess_fresh",
            "scraped_at":      datetime.now().isoformat(),
        }
        if source_url:
            result["_meta"]["source_url"] = source_url

        filename = f"api_profile_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_json_output(result, filename, OUTPUT_PROFILE_DIR)
        result["_meta"]["saved_file"] = filename

        # Simpan ke growth tracking
        if save_tracking and result.get("success"):
            save_profile_to_tracking(result)
            result["_tracking_saved"] = True

        msg = f"Profile @{username} scraped in {round(t_elapsed, 1)}s"
        if source_url:
            msg += " from URL"

        return jsonify(success_response(result, msg))

    except Exception as e:
        traceback.print_exc()
        return error_response(f"Profile scrape failed: {str(e)}", 500, {"traceback": traceback.format_exc()})


@app.route("/api/v1/scrape/profiles/batch", methods=["POST"])
@require_json_fields("usernames")
def scrape_batch_profiles():
    data          = request.get_json()
    usernames     = data["usernames"]
    delay_between = data.get("delay_between", 12)
    save_tracking = data.get("save_tracking", True)

    if not isinstance(usernames, list) or len(usernames) == 0:
        return error_response("'usernames' harus berupa array non-kosong", 400)

    results = []
    t_total = time.time()

    for i, username in enumerate(usernames):
        username = username.strip().lstrip("@").lower()
        print(Fore.CYAN + f"\n[{i+1}/{len(usernames)}] @{username}")
        try:
            r = run_profile_scraper_subprocess(username)
            if save_tracking and r.get("success"):
                save_profile_to_tracking(r)
            results.append({"username": username, "success": True, "data": r})
        except Exception as e:
            results.append({"username": username, "success": False, "error": str(e)})

        if i < len(usernames) - 1:
            delay = delay_between + random.randint(3, 8)
            print(Fore.YELLOW + f"   ⏳ Jeda {delay}s...")
            time.sleep(delay)

    summary = {
        "total":           len(usernames),
        "success":         sum(1 for r in results if r["success"]),
        "failed":          sum(1 for r in results if not r["success"]),
        "elapsed_seconds": round(time.time() - t_total, 2),
        "results":         results,
    }

    filename = f"api_batch_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_json_output(summary, filename, OUTPUT_PROFILE_DIR)
    summary["saved_file"] = filename

    return jsonify(success_response(
        summary,
        f"Batch profiles: {summary['success']}/{summary['total']} success",
    ))


@app.route("/api/v1/scrape/profiles/batch/url", methods=["POST"])
@require_json_fields("urls")
def scrape_batch_profiles_by_url():
    data          = request.get_json()
    urls          = data["urls"]
    delay_between = data.get("delay_between", 12)
    save_tracking = data.get("save_tracking", True)

    if not isinstance(urls, list) or len(urls) == 0:
        return error_response("'urls' harus berupa array non-kosong", 400)

    # Extract username dari setiap URL
    username_url_pairs = []
    for url in urls:
        username = extract_username_from_url(url)
        if not username:
            return error_response(f"Tidak bisa extract username dari URL: {url}", 400)
        username_url_pairs.append((username, url))

    results = []
    t_total = time.time()

    for i, (username, url) in enumerate(username_url_pairs):
        print(Fore.CYAN + f"\n[{i+1}/{len(username_url_pairs)}] @{username}")
        try:
            r = run_profile_scraper_subprocess(username, url)
            if save_tracking and r.get("success"):
                save_profile_to_tracking(r)
            results.append({"username": username, "url": url, "success": True, "data": r})
        except Exception as e:
            results.append({"username": username, "url": url, "success": False, "error": str(e)})

        if i < len(username_url_pairs) - 1:
            delay = delay_between + random.randint(3, 8)
            print(Fore.YELLOW + f"   ⏳ Jeda {delay}s...")
            time.sleep(delay)

    summary = {
        "total":           len(username_url_pairs),
        "success":         sum(1 for r in results if r["success"]),
        "failed":          sum(1 for r in results if not r["success"]),
        "elapsed_seconds": round(time.time() - t_total, 2),
        "results":         results,
    }

    filename = f"api_batch_profiles_url_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_json_output(summary, filename, OUTPUT_PROFILE_DIR)
    summary["saved_file"] = filename

    return jsonify(success_response(
        summary,
        f"Batch profiles by URL: {summary['success']}/{summary['total']} success",
    ))


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS — ANALYTICS / GROWTH
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/v1/profiles", methods=["GET"])
def list_tracked_profiles():
    tracking = load_tracking_data()
    users    = []
    for username, data in tracking.items():
        history = data.get("history", [])
        latest  = history[-1] if history else {}
        users.append({
            "username":        username,
            "data_points":     len(history),
            "first_tracked":   data.get("first_tracked", ""),
            "last_tracked":    data.get("last_tracked", ""),
            "current_followers": latest.get("followers", 0),
            "current_likes":   latest.get("total_likes", 0),
            "current_videos":  latest.get("total_videos", 0),
        })
    users.sort(key=lambda x: x["last_tracked"], reverse=True)
    return jsonify(success_response({"count": len(users), "users": users}))


@app.route("/api/v1/profiles/<username>", methods=["GET"])
def get_profile(username):
    username = username.strip().lstrip("@").lower()
    tracking = load_tracking_data()

    if username not in tracking:
        return error_response(f"Tidak ada data untuk @{username}", 404)

    data    = tracking[username]
    history = data.get("history", [])
    latest  = history[-1] if history else {}

    return jsonify(success_response({
        "username":          username,
        "data_points":       len(history),
        "first_tracked":     data.get("first_tracked", ""),
        "last_tracked":      data.get("last_tracked", ""),
        "latest_snapshot":   latest,
    }))


@app.route("/api/v1/profiles/<username>/history", methods=["GET"])
def get_profile_history(username):
    username = username.strip().lstrip("@").lower()
    limit    = request.args.get("limit", 50, type=int)
    tracking = load_tracking_data()

    if username not in tracking:
        return error_response(f"Tidak ada data untuk @{username}", 404)

    history = tracking[username].get("history", [])
    history_sorted = sorted(history, key=lambda x: x.get("scraped_at", ""), reverse=True)
    history_limited = history_sorted[:limit]

    return jsonify(success_response({
        "username":       username,
        "total_points":   len(history),
        "returned":       len(history_limited),
        "snapshots":      history_limited,
    }))


@app.route("/api/v1/profiles/<username>/growth", methods=["GET"])
def get_growth_analysis(username):
    username = username.strip().lstrip("@").lower()
    days     = request.args.get("days", 30, type=int)
    tracking = load_tracking_data()

    if username not in tracking:
        return error_response(f"Tidak ada data untuk @{username}", 404)

    history = tracking[username].get("history", [])
    if len(history) < 2:
        return error_response(
            f"Hanya ada {len(history)} data point untuk @{username}. Perlu minimal 2.",
            400,
        )

    # Filter berdasarkan range hari
    cutoff  = datetime.now() - timedelta(days=days)
    filtered = [
        h for h in history
        if datetime.fromisoformat(h["scraped_at"]) >= cutoff
    ]

    if len(filtered) < 2:
        filtered = history  # Pakai semua kalau tidak cukup

    filtered.sort(key=lambda x: x["scraped_at"])
    first = filtered[0]
    last  = filtered[-1]

    first_dt  = datetime.fromisoformat(first["scraped_at"])
    last_dt   = datetime.fromisoformat(last["scraped_at"])
    days_span = (last_dt - first_dt).days or 1

    def calc(field):
        start = first.get(field, 0)
        end   = last.get(field, 0)
        growth = end - start
        pct    = round((growth / start * 100), 2) if start > 0 else 0.0
        daily  = round(growth / days_span, 2)
        return {"start": start, "end": end, "growth": growth, "growth_pct": pct, "avg_per_day": daily}

    analysis = {
        "username":    username,
        "analyzed_at": datetime.now().isoformat(),
        "period": {
            "start_date":  first_dt.isoformat(),
            "end_date":    last_dt.isoformat(),
            "days":        days_span,
            "data_points": len(filtered),
        },
        "followers": calc("followers"),
        "following": calc("following"),
        "likes":     calc("total_likes"),
        "videos":    calc("total_videos"),
        "history":   filtered,
    }

    return jsonify(success_response(analysis, f"Growth analysis @{username} ({days_span} days)"))


@app.route("/api/v1/profiles/<username>/track", methods=["POST"])
def manual_track_profile(username):
    """Manual insert snapshot (untuk backfill data historis)."""
    username = username.strip().lstrip("@").lower()
    data     = request.get_json() or {}

    followers    = data.get("followers", 0)
    following    = data.get("following", 0)
    total_likes  = data.get("total_likes", 0)
    total_videos = data.get("total_videos", 0)
    scraped_at   = data.get("scraped_at", datetime.now().isoformat())

    if not followers and not total_likes:
        return error_response("Minimal 'followers' atau 'total_likes' harus diisi", 400)

    tracking = load_tracking_data()

    if username not in tracking:
        tracking[username] = {
            "username":      username,
            "first_tracked": scraped_at,
            "history":       [],
        }

    snapshot = {
        "scraped_at":   scraped_at,
        "followers":    followers,
        "following":    following,
        "total_likes":  total_likes,
        "total_videos": total_videos,
    }

    tracking[username]["history"].append(snapshot)
    tracking[username]["last_tracked"] = scraped_at
    save_tracking_data(tracking)

    return jsonify(success_response({
        "username":         username,
        "snapshot_added":   snapshot,
        "total_data_points": len(tracking[username]["history"]),
    }, f"Manual snapshot added for @{username}"))


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS — HEALTH
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/v1/health", methods=["GET"])
def health_check():
    login_state = get_login_state()

    try:
        from tiktok_cookie_injector import has_valid_session, get_session_info
        session_valid = has_valid_session()
        session_info  = get_session_info()
    except Exception:
        session_valid = False
        session_info  = {}

    tracking = load_tracking_data()
    profile_count = len(tracking)

    total_videos_scraped = 0
    try:
        files = os.listdir(OUTPUT_VIDEO_DIR)
        total_videos_scraped = sum(1 for f in files if f.endswith(".json"))
    except Exception:
        pass

    status = {
        "api":                  "running",
        "platform":             "tiktok",
        "session_valid":        session_valid,
        "session_info":         session_info,
        "chrome_profile_path":  TIKTOK_CHROME_PROFILE,
        "chrome_profile_exists": os.path.exists(TIKTOK_CHROME_PROFILE) and bool(os.listdir(TIKTOK_CHROME_PROFILE)),
        "output_video_dir":     os.path.abspath(OUTPUT_VIDEO_DIR),
        "output_profile_dir":   os.path.abspath(OUTPUT_PROFILE_DIR),
        "video_scraper_mode":   "subprocess (fresh per request)",
        "profile_scraper_mode": "subprocess (fresh per request)",
        "tracked_profiles":     profile_count,
        "video_files_saved":    total_videos_scraped,
        "login_state": {
            "is_running":     login_state["is_running"],
            "login_detected": login_state["login_detected"],
            "username":       login_state["username"],
        },
        "timestamp": datetime.now().isoformat(),
    }
    return jsonify(success_response(status, "TikTok API is healthy"))


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(Fore.CYAN + "=" * 60)
    print(Fore.CYAN + "  TIKTOK SCRAPER API SERVER")
    print(Fore.CYAN + "  Video Comments + Profile + Growth Tracking")
    print(Fore.CYAN + f"  Listening on http://{API_HOST}:{API_PORT}")
    print(Fore.CYAN + "=" * 60)

    # Cek session
    try:
        from tiktok_cookie_injector import has_valid_session
        if has_valid_session():
            print(Fore.GREEN + "\n✅ Session TikTok valid — siap scraping!")
        else:
            print(Fore.YELLOW + "\n⚠️  Session belum ada.")
            print(Fore.YELLOW + "   Gunakan: python tiktok_session_manager.py")
            print(Fore.YELLOW + "   Atau    : POST /api/v1/auth/login")
    except Exception:
        print(Fore.YELLOW + "\n⚠️  tiktok_cookie_injector tidak ditemukan")

    print(Fore.YELLOW + "\n⚡ Server ready!\n")

    try:
        app.run(
            host=API_HOST,
            port=API_PORT,
            debug=DEBUG_MODE,
            threaded=False,
            use_reloader=False,
        )
    finally:
        print(Fore.YELLOW + "\n🧹 Server shutting down...")