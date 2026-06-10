"""
tiktok_session_manager.py
=========================
CLI untuk manage session TikTok via Cookie-Editor JSON.

Cara pakai:
  1. Login TikTok di browser biasa (Chrome/Firefox)
  2. Install ekstensi Cookie-Editor
  3. Export cookies → Copy (JSON format)
  4. Jalankan: python tiktok_session_manager.py
  5. Pilih menu 1 → Paste JSON cookies
  6. Session tersimpan di session/tt_session.json

Menu:
  1. Import cookies (paste JSON dari Cookie-Editor)
  2. Cek status session
  3. Hapus session
  4. Export session info
  5. Test session (buka browser & verifikasi)
  6. Exit
"""
import os
import sys
import json
import time
import asyncio
import threading
from datetime import datetime
from typing import List, Dict, Optional

from colorama import Fore, Style, init

init(autoreset=True)

# Import cookie injector TikTok
try:
    from tiktok_cookie_injector import (
        save_session,
        load_raw_cookies,
        has_valid_session,
        get_session_info,
        delete_session,
        SESSION_FILE,
        SESSION_DIR,
        REQUIRED_COOKIES,
        PREFERRED_COOKIES,
    )
except ImportError:
    print(Fore.RED + "❌ tiktok_cookie_injector.py tidak ditemukan!")
    sys.exit(1)


# ── HELPERS ───────────────────────────────────────────────────────────────

def print_banner():
    print(Fore.CYAN + "\n" + "=" * 70)
    print(Fore.CYAN + "  TIKTOK SESSION MANAGER")
    print(Fore.CYAN + "  Manage cookies login TikTok via Cookie-Editor JSON")
    print(Fore.CYAN + "=" * 70)


def print_instructions():
    print(Fore.YELLOW + """
📋 CARA LOGIN VIA COOKIE-EDITOR:

1. Buka browser Chrome/Firefox
2. Pergi ke https://www.tiktok.com dan login manual
3. Setelah login berhasil, install ekstensi:
   • Chrome : https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm
   • Firefox: https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/

4. Klik icon Cookie-Editor → klik "Export" → pilih "Export as JSON"
5. Semua cookies ter-copy ke clipboard
6. Kembali ke sini → pilih menu [1] → paste JSON → Enter 2x

💡 Tips:
   - Pastikan sudah login TikTok sebelum export
   - Cookie akan expired setelah beberapa hari/minggu
   - Jika scraper error "session expired", ulangi proses ini
   - Cookies yang diperlukan: sessionid (wajib), sessionid_ss (disarankan)
""")


def print_session_status(detailed: bool = False):
    """Print status session saat ini."""
    info = get_session_info()

    print(Fore.CYAN + "\n" + "─" * 50)
    print(Fore.CYAN + "📊 STATUS SESSION TIKTOK")
    print(Fore.CYAN + "─" * 50)

    if not info.get("valid"):
        print(Fore.RED + "  ❌ Session TIDAK VALID / belum ada")
        if info.get("error"):
            print(Fore.RED + f"  Error: {info['error']}")
        return

    print(Fore.GREEN + "  ✅ Session VALID")
    print(Fore.WHITE + f"  📁 File      : {info.get('session_file', '-')}")
    print(Fore.WHITE + f"  🍪 Total     : {info.get('total_cookies', 0)} cookies")

    if info.get("has_preferred"):
        print(Fore.GREEN + f"  ⭐ Preferred cookies: LENGKAP")
    else:
        missing = info.get("preferred_missing", [])
        print(Fore.YELLOW + f"  ⚠️  Preferred missing: {', '.join(missing)}")

    if detailed and info.get("cookie_names"):
        print(Fore.CYAN + "\n  📋 Cookie names:")
        for name in info["cookie_names"]:
            marker = "✅" if name in REQUIRED_COOKIES else ("⭐" if name in PREFERRED_COOKIES else "  ")
            print(f"     {marker} {name}")

    print(Fore.CYAN + "─" * 50)


# ── MENU 1: IMPORT COOKIES ────────────────────────────────────────────────

def import_cookies_from_clipboard():
    """
    Minta user paste JSON cookies dari Cookie-Editor.
    Support multi-line paste (end dengan baris kosong atau Ctrl+D).
    """
    print(Fore.CYAN + "\n" + "=" * 70)
    print(Fore.CYAN + "  IMPORT COOKIES DARI COOKIE-EDITOR")
    print(Fore.CYAN + "=" * 70)

    print_instructions()

    print(Fore.YELLOW + "📥 Paste JSON cookies di bawah ini.")
    print(Fore.YELLOW + "   Setelah paste, tekan ENTER 2x (baris kosong) untuk selesai:\n")

    lines = []
    try:
        while True:
            try:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            except EOFError:
                break
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n⚠️  Dibatalkan")
        return False

    raw_text = "\n".join(lines).strip()
    if not raw_text:
        print(Fore.RED + "❌ Tidak ada input")
        return False

    # Parse JSON
    try:
        cookies = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(Fore.RED + f"❌ JSON tidak valid: {e}")
        print(Fore.YELLOW + "   Pastikan format JSON benar dari Cookie-Editor")
        return False

    # Validasi format
    if not isinstance(cookies, list):
        print(Fore.RED + "❌ Format salah — harus berupa array/list cookies")
        return False

    if len(cookies) == 0:
        print(Fore.RED + "❌ Cookies kosong")
        return False

    # Cek cookies wajib
    names = {c.get("name", "") for c in cookies if isinstance(c, dict)}
    missing_required = REQUIRED_COOKIES - names

    if missing_required:
        print(Fore.RED + f"❌ Cookie wajib tidak ada: {', '.join(missing_required)}")
        print(Fore.YELLOW + "   Pastikan sudah login TikTok sebelum export cookies")
        return False

    # Filter hanya cookies TikTok
    tiktok_cookies = [
        c for c in cookies
        if isinstance(c, dict) and "tiktok.com" in str(c.get("domain", "")).lower()
    ]

    if not tiktok_cookies:
        print(Fore.YELLOW + "⚠️  Tidak ada cookie domain tiktok.com, pakai semua cookies...")
        tiktok_cookies = cookies

    # Minta username (opsional)
    username = input(Fore.WHITE + "\n👤 Username TikTok kamu (opsional, tekan Enter skip): ").strip()
    username = username.lstrip("@")

    # Simpan
    print(Fore.CYAN + f"\n💾 Menyimpan {len(tiktok_cookies)} cookies...")
    session_path = save_session(tiktok_cookies, username=username)

    print(Fore.GREEN + f"✅ Session tersimpan: {session_path}")
    print(Fore.GREEN + f"   Total cookies: {len(tiktok_cookies)}")

    # Tampilkan status
    print_session_status()

    return True


# ── MENU 2: CEK STATUS ────────────────────────────────────────────────────

def check_status():
    print_session_status(detailed=True)

    if has_valid_session():
        try:
            raw = load_raw_cookies()
            print(Fore.CYAN + "\n📋 Preview cookies (5 pertama):")
            for c in raw[:5]:
                name  = c.get("name", "")
                value = str(c.get("value", ""))[:20]
                exp   = c.get("expirationDate", "")
                if exp:
                    try:
                        exp_dt = datetime.fromtimestamp(float(exp)).strftime("%Y-%m-%d")
                        exp_str = f" (exp: {exp_dt})"
                    except Exception:
                        exp_str = ""
                else:
                    exp_str = ""
                print(f"   {name:<25} = {value}...{exp_str}")
        except Exception as e:
            print(Fore.RED + f"❌ Error baca cookies: {e}")


# ── MENU 3: HAPUS SESSION ─────────────────────────────────────────────────

def delete_session_interactive():
    print(Fore.CYAN + "\n⚠️  HAPUS SESSION TIKTOK")

    if not has_valid_session():
        print(Fore.YELLOW + "   Session belum ada / sudah tidak ada")
        return

    confirm = input(Fore.RED + "\n   Yakin hapus session? (ketik 'yes' untuk konfirmasi): ").strip().lower()
    if confirm != "yes":
        print(Fore.YELLOW + "   Dibatalkan")
        return

    if delete_session():
        print(Fore.GREEN + "✅ Session berhasil dihapus")
    else:
        print(Fore.RED + "❌ Gagal hapus session")


# ── MENU 4: EXPORT INFO ───────────────────────────────────────────────────

def export_session_info():
    """Export info session ke JSON untuk debugging."""
    info = get_session_info()
    if not info.get("valid"):
        print(Fore.RED + "❌ Tidak ada session valid untuk di-export")
        return

    output_file = os.path.join(SESSION_DIR, "tt_session_info.json")
    os.makedirs(SESSION_DIR, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    print(Fore.GREEN + f"✅ Session info di-export ke: {output_file}")


# ── MENU 5: TEST SESSION ─────────────────────────────────────────────────

def test_session_browser():
    """
    Test session dengan membuka browser Playwright dan navigasi ke TikTok.
    Cek apakah login berhasil atau tidak.
    """
    if not has_valid_session():
        print(Fore.RED + "❌ Session belum ada. Import dulu via menu [1]")
        return

    print(Fore.CYAN + "\n🧪 TEST SESSION — Membuka browser TikTok...")
    print(Fore.YELLOW + "   Browser akan terbuka sebentar untuk verifikasi")

    result = {"success": False, "username": "", "error": ""}

    def _test():
        try:
            from playwright.sync_api import sync_playwright
            from tiktok_cookie_injector import inject_cookies_sync

            profile_dir = os.path.join(os.getcwd(), "tiktok_chrome_real_profile")
            os.makedirs(profile_dir, exist_ok=True)

            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    profile_dir,
                    channel="chrome",
                    headless=False,
                    args=[
                        "--window-size=1280,800",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-notifications",
                    ],
                    viewport=None,
                    locale="id-ID",
                    timezone_id="Asia/Jakarta",
                )

                # Inject cookies
                n = inject_cookies_sync(context)
                print(Fore.GREEN + f"   🍪 {n} cookies diinject")

                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=30000)
                time.sleep(5)

                # Cek login
                cookies = context.cookies("https://www.tiktok.com")
                cookie_names = {c["name"] for c in cookies}

                if "sessionid" in cookie_names:
                    result["success"] = True
                    print(Fore.GREEN + "   ✅ Session valid — TikTok terbuka dengan login!")

                    # Coba ambil username dari page
                    try:
                        username_el = page.locator("[data-e2e='nav-profile']")
                        if username_el.count() > 0:
                            result["username"] = "logged_in"
                    except Exception:
                        pass
                else:
                    result["error"] = "sessionid tidak ditemukan di browser cookies"
                    print(Fore.RED + f"   ❌ {result['error']}")

                time.sleep(3)
                context.close()

        except Exception as e:
            result["error"] = str(e)
            print(Fore.RED + f"   ❌ Error: {e}")

    thread = threading.Thread(target=_test, daemon=True)
    thread.start()
    thread.join(timeout=60)

    if result["success"]:
        print(Fore.GREEN + "\n✅ TEST BERHASIL — Session TikTok valid!")
    else:
        print(Fore.RED + f"\n❌ TEST GAGAL: {result.get('error', 'Unknown error')}")
        print(Fore.YELLOW + "   Coba import ulang cookies")


# ── MENU 6: LOGIN BROWSER (untuk yang belum punya cookies) ───────────────

def open_login_browser():
    """Buka browser untuk login manual TikTok, lalu auto-save session."""
    print(Fore.CYAN + "\n🌐 BUKA BROWSER UNTUK LOGIN TIKTOK")
    print(Fore.YELLOW + "   Browser Chrome akan terbuka")
    print(Fore.YELLOW + "   Login manual di browser, lalu session akan otomatis tersimpan")
    print(Fore.YELLOW + "   (atau gunakan Cookie-Editor untuk export yang lebih reliable)")

    profile_dir = os.path.join(os.getcwd(), "tiktok_chrome_real_profile")
    os.makedirs(profile_dir, exist_ok=True)

    result = {"logged_in": False, "error": ""}

    def _browser_worker():
        try:
            from playwright.sync_api import sync_playwright

            stealth_script = """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
                try { delete navigator.__proto__.webdriver; } catch(e) {}
            """

            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    profile_dir,
                    channel="chrome",
                    headless=False,
                    args=[
                        "--window-size=1280,900",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-notifications",
                        "--start-maximized",
                    ],
                    viewport=None,
                    locale="id-ID",
                    timezone_id="Asia/Jakarta",
                    bypass_csp=True,
                )
                context.on("page", lambda p: p.add_init_script(stealth_script))

                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=30000)

                print(Fore.CYAN + "\n   Browser terbuka! Login manual di browser...")
                print(Fore.CYAN + "   Menunggu login (max 5 menit)...")

                max_wait   = 60  # 5 menit × 12 (tiap 5 detik)
                logged_in  = False

                for i in range(max_wait):
                    time.sleep(5)
                    cookies      = context.cookies("https://www.tiktok.com")
                    cookie_names = {c["name"] for c in cookies}

                    if "sessionid" in cookie_names:
                        logged_in = True
                        print(Fore.GREEN + "\n   ✅ Login terdeteksi!")

                        # Simpan ke session file
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
                        ]
                        save_session(tiktok_cookies, note="auto_saved_from_browser_login")
                        result["logged_in"] = True
                        print(Fore.GREEN + f"   💾 Session tersimpan: {SESSION_FILE}")
                        break

                    remaining = (max_wait - i - 1) * 5
                    if i % 6 == 0:
                        print(Fore.YELLOW + f"   ⏳ Menunggu login... {remaining}s tersisa", end="\r")

                if not logged_in:
                    print(Fore.RED + "\n   ❌ Timeout — login tidak terdeteksi")
                    result["error"] = "Timeout"

                time.sleep(5)
                context.close()

        except Exception as e:
            result["error"] = str(e)
            print(Fore.RED + f"\n   ❌ Error: {e}")

    thread = threading.Thread(target=_browser_worker, daemon=True)
    thread.start()
    thread.join(timeout=320)

    if result["logged_in"]:
        print(Fore.GREEN + "\n✅ LOGIN BERHASIL — Session tersimpan!")
        print_session_status()
    else:
        print(Fore.RED + f"\n❌ Login gagal: {result.get('error', 'Unknown')}")
        print(Fore.YELLOW + "   Coba gunakan Cookie-Editor (menu [1]) sebagai alternatif")


# ── MAIN CLI ──────────────────────────────────────────────────────────────

def main():
    print_banner()

    # Quick status di awal
    if has_valid_session():
        print(Fore.GREEN + "\n✅ Session aktif ditemukan")
    else:
        print(Fore.YELLOW + "\n⚠️  Belum ada session — Import cookies dulu (menu [1])")

    while True:
        print(Fore.CYAN + "\n" + "─" * 50)
        print(Fore.CYAN + "📋 MENU")
        print("  1. Import cookies (paste dari Cookie-Editor)")
        print("  2. Cek status session")
        print("  3. Hapus session")
        print("  4. Export session info (untuk debugging)")
        print("  5. Test session (buka browser & verifikasi)")
        print("  6. Login via browser (tanpa Cookie-Editor)")
        print("  7. Exit")
        print(Fore.CYAN + "─" * 50)

        choice = input(Fore.WHITE + "\nPilih [1-7]: ").strip()

        if choice == "1":
            import_cookies_from_clipboard()

        elif choice == "2":
            check_status()

        elif choice == "3":
            delete_session_interactive()

        elif choice == "4":
            export_session_info()

        elif choice == "5":
            test_session_browser()

        elif choice == "6":
            open_login_browser()

        elif choice == "7":
            print(Fore.CYAN + "\n👋 Bye!")
            break

        else:
            print(Fore.RED + "❌ Pilihan tidak valid [1-7]")


if __name__ == "__main__":
    main()