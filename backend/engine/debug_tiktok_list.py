# ============================================================
# DEBUG TIKTOK FOLLOWER/FOLLOWING LIST
# ============================================================
# Tujuan: cari tahu KENAPA modal followers/following tidak terdeteksi
#   1. Rekam SEMUA request yang berbau user/list/follower/following
#   2. Dump struktur DOM modal (role, class, data-e2e) yang benar
#   3. Tangkap response JSON pertama biar tau field-nya
#
# CARA PAKAI:
#   cd C:\Users\USER\tiktok-scraper-ui\backend\engine
#   python debug_tiktok_list.py
#
# Lalu di browser yang terbuka:
#   → Tunggu profil ke-load
#   → KLIK SENDIRI tab "Pengikut" (atau "Mengikuti")
#   → Scroll modalnya sedikit
#   → Balik ke terminal, tekan ENTER
#
# Output: debug_list_report.json + print di terminal.
# Kirim isi file itu ke Claude.
# ============================================================

import os
import re
import json
import time
from datetime import datetime

from dotenv import load_dotenv
from colorama import Fore, init
from playwright.sync_api import sync_playwright

from tiktok_cookie_injector import inject_cookies_sync, has_valid_session

init(autoreset=True)
load_dotenv()

_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
PERSISTENT_PROFILE = os.path.join(_FILE_DIR, "tiktok_cookie_profile_persistent")
REPORT_FILE = os.path.join(_FILE_DIR, "debug_list_report.json")

USERNAME = input("Username / URL target [gibran_rakabuming]: ").strip() or "gibran_rakabuming"
m = re.search(r'@([^/?&#\s]+)', USERNAME)
if m:
    USERNAME = m.group(1)
USERNAME = USERNAME.lstrip("@").lower()

report = {
    "username": USERNAME,
    "checked_at": datetime.now().isoformat(),
    "list_requests": [],      # request yang berbau list/follower/following
    "list_responses": [],     # ringkasan response JSON-nya
    "modal_dom": None,        # struktur DOM modal saat dibuka
}

captured_requests = []   # (url, status, content_type)
captured_responses = []  # objek Response untuk dibaca nanti


def main():
    with sync_playwright() as p:
        os.makedirs(PERSISTENT_PROFILE, exist_ok=True)
        print(Fore.CYAN + "🌐 Membuka browser (non-headless, full)...")

        context = p.chromium.launch_persistent_context(
            PERSISTENT_PROFILE,
            channel="chrome",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-notifications",
                "--start-maximized",
            ],
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            locale="id-ID",
            timezone_id="Asia/Jakarta",
            bypass_csp=True,
        )

        if has_valid_session():
            try:
                n = inject_cookies_sync(context)
                print(Fore.GREEN + f"🍪 Inject {n} cookies")
            except Exception as e:
                print(Fore.YELLOW + f"⚠️  Inject cookie gagal: {e}")

        page = context.pages[0] if context.pages else context.new_page()

        # ── REKAM SEMUA request & response yang relevan ──
        KEYWORDS = ["user/list", "follower", "following", "/api/user/"]

        def on_request(req):
            url = req.url
            if any(k in url for k in KEYWORDS):
                captured_requests.append(url)
                print(Fore.MAGENTA + f"   📤 REQ: {url[:160]}")

        def on_response(resp):
            url = resp.url
            if any(k in url for k in KEYWORDS):
                captured_responses.append(resp)
                print(Fore.CYAN + f"   📥 RES [{resp.status}]: {url[:160]}")

        page.on("request", on_request)
        page.on("response", on_response)

        # buka profil
        url = f"https://www.tiktok.com/@{USERNAME}"
        print(Fore.YELLOW + f"\n🌍 Buka: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(Fore.YELLOW + f"⚠️  goto warning: {e}")

        print(Fore.GREEN + "\n" + "=" * 60)
        print(Fore.GREEN + "  👉 SEKARANG DI BROWSER:")
        print(Fore.GREEN + "     1. Tunggu profil ke-load penuh")
        print(Fore.GREEN + "     2. KLIK tab 'Pengikut' (Followers)")
        print(Fore.GREEN + "     3. Scroll daftar di modal sedikit")
        print(Fore.GREEN + "     4. Balik ke sini, tekan ENTER")
        print(Fore.GREEN + "=" * 60)
        input(Fore.WHITE + "\n[ENTER setelah modal followers terbuka & di-scroll] ")

        # ── DUMP STRUKTUR DOM MODAL ──
        print(Fore.CYAN + "\n🔍 Menganalisa DOM modal...")
        modal_dom = page.evaluate(r"""() => {
            // cari kandidat modal: role=dialog, atau div besar yang overlay
            const report = { candidates: [], scrollables: [] };

            // 1. semua elemen dengan role=dialog
            document.querySelectorAll("[role='dialog']").forEach(el => {
                report.candidates.push({
                    tag: el.tagName,
                    role: el.getAttribute('role'),
                    class: el.className,
                    dataE2e: el.getAttribute('data-e2e'),
                    childCount: el.children.length,
                });
            });

            // 2. semua elemen yg punya data-e2e mengandung 'follow' atau 'user-list'
            document.querySelectorAll("[data-e2e]").forEach(el => {
                const de = el.getAttribute('data-e2e') || '';
                if (de.includes('follow') || de.includes('user') || de.includes('list')) {
                    report.candidates.push({
                        tag: el.tagName,
                        dataE2e: de,
                        class: (el.className || '').toString().slice(0, 80),
                        visible: el.offsetParent !== null,
                    });
                }
            });

            // 3. elemen scrollable (kandidat container daftar)
            document.querySelectorAll('div').forEach(el => {
                if (el.scrollHeight > el.clientHeight + 40 && el.clientHeight > 150) {
                    report.scrollables.push({
                        class: (el.className || '').toString().slice(0, 80),
                        dataE2e: el.getAttribute('data-e2e'),
                        scrollH: el.scrollHeight,
                        clientH: el.clientHeight,
                    });
                }
            });

            // 4. contoh link username di dalam modal (a[href^='/@'])
            const userLinks = [];
            document.querySelectorAll("a[href^='/@']").forEach(a => {
                if (userLinks.length < 8) {
                    userLinks.push({
                        href: a.getAttribute('href'),
                        dataE2e: a.getAttribute('data-e2e'),
                        text: (a.textContent || '').trim().slice(0, 30),
                    });
                }
            });
            report.userLinks = userLinks;

            return report;
        }""")
        report["modal_dom"] = modal_dom

        print(Fore.GREEN + f"   Kandidat modal/elemen: {len(modal_dom.get('candidates', []))}")
        print(Fore.GREEN + f"   Elemen scrollable: {len(modal_dom.get('scrollables', []))}")
        print(Fore.GREEN + f"   Link user (a[href^='/@']): {len(modal_dom.get('userLinks', []))}")

        # ── BACA RESPONSE JSON yang tertangkap ──
        print(Fore.CYAN + "\n🔍 Membaca response yang tertangkap...")
        for resp in captured_responses:
            entry = {"url": resp.url, "status": resp.status}
            try:
                data = resp.json()
                # ringkas: ambil top-level keys + cek userList
                entry["top_keys"] = list(data.keys())[:20]
                ul = data.get("userList") or data.get("userInfoList") or data.get("followers") or []
                entry["user_list_len"] = len(ul) if isinstance(ul, list) else "bukan list"
                if isinstance(ul, list) and ul:
                    sample = ul[0]
                    entry["sample_item_keys"] = list(sample.keys())[:20]
                    u = sample.get("user") or sample.get("userInfo") or {}
                    entry["sample_uniqueId"] = u.get("uniqueId")
                entry["statusCode"] = data.get("statusCode")
                entry["status_msg"] = data.get("status_msg") or data.get("statusMsg")
            except Exception as e:
                entry["parse_error"] = str(e)
                try:
                    entry["body_preview"] = resp.text()[:300]
                except Exception:
                    pass
            report["list_responses"].append(entry)

        report["list_requests"] = list(dict.fromkeys(captured_requests))  # dedup

        # ── SIMPAN ──
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(Fore.GREEN + "\n" + "=" * 60)
        print(Fore.GREEN + f"✅ Report disimpan: {REPORT_FILE}")
        print(Fore.GREEN + "=" * 60)
        print(Fore.YELLOW + "\n── RINGKASAN ──")
        print(Fore.YELLOW + f"Request list tertangkap : {len(report['list_requests'])}")
        print(Fore.YELLOW + f"Response list tertangkap: {len(report['list_responses'])}")
        if report["list_requests"]:
            print(Fore.CYAN + "\nContoh URL request:")
            for u in report["list_requests"][:5]:
                print("   " + u[:170])
        if report["list_responses"]:
            print(Fore.CYAN + "\nRingkasan response:")
            for r in report["list_responses"][:5]:
                print("   " + json.dumps(r, ensure_ascii=False)[:200])

        input(Fore.WHITE + "\n[ENTER untuk menutup browser] ")
        context.close()


if __name__ == "__main__":
    main()