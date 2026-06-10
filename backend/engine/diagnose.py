#!/usr/bin/env python3
"""
diagnose.py — Script diagnosa masalah TikTok Scraper
=====================================================
Jalankan di folder engine/:
    python diagnose.py

Akan cek:
  1. File engine yang dibutuhkan (ada/tidak)
  2. Session tt_session.json (valid/tidak)
  3. Import semua module engine
  4. Test scrape komentar sederhana (opsional)
"""

import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

REQUIRED_FILES = [
    "tiktok_scraper.py",
    "tiktok_profile_scraper.py",
    "tiktok_cookie_injector.py",
    "sentiment_analyzer_v2.py",
    "tiktok_slang_extension.py",
]

SESSION_FILE = os.path.join(HERE, "session", "tt_session.json")

print("=" * 60)
print("  TIKTOK SCRAPER — DIAGNOSA")
print("=" * 60)

# ── CEK FILE ──────────────────────────────────────────────────────
print("\n📁 FILE ENGINE:")
all_ok = True
for fname in REQUIRED_FILES:
    fp = os.path.join(HERE, fname)
    exists = os.path.isfile(fp)
    icon = "✅" if exists else "❌"
    size = os.path.getsize(fp) if exists else 0
    print(f"  {icon} {fname:<40} {'(' + str(size) + ' bytes)' if exists else 'TIDAK ADA!'}")
    if not exists:
        all_ok = False

# ── CEK SESSION ───────────────────────────────────────────────────
print("\n🍪 SESSION:")
if os.path.isfile(SESSION_FILE):
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            session = json.load(f)
        cookies = session.get("cookies", [])
        names = {c.get("name") for c in cookies}
        has_session_id = "sessionid" in names
        print(f"  {'✅' if has_session_id else '❌'} tt_session.json ada ({len(cookies)} cookies)")
        print(f"  {'✅' if has_session_id else '❌'} sessionid cookie: {'ADA' if has_session_id else 'TIDAK ADA'}")
        print(f"  📅 Disimpan: {session.get('saved_at', 'unknown')}")
        print(f"  👤 Username: {session.get('username', 'unknown')}")
        if not has_session_id:
            print("\n  ⚠️  MASALAH: Cookie 'sessionid' tidak ditemukan!")
            print("  💡 Solusi: Export ulang cookies dari browser setelah login TikTok")
            print("     Gunakan extension: Cookie-Editor (Chrome/Firefox)")
            print("     Pastikan sudah login di www.tiktok.com dulu")
    except Exception as e:
        print(f"  ❌ Gagal baca session: {e}")
else:
    print(f"  ❌ File tidak ada: {SESSION_FILE}")
    print("\n  💡 CARA BUAT SESSION:")
    print("  1. Install Chrome extension 'Cookie-Editor'")
    print("  2. Buka tiktok.com dan login")
    print("  3. Klik Cookie-Editor → Export → Export as JSON")
    print("  4. Copy hasilnya")
    print("  5. Paste di Settings → Cookies di UI scraper")
    print("     ATAU jalankan: python tiktok_session_manager.py")

# ── CEK IMPORT ───────────────────────────────────────────────────
print("\n📦 IMPORT CHECK:")

modules_to_check = [
    ("tiktok_cookie_injector", ["has_valid_session", "inject_cookies_sync", "get_session_info"]),
    ("tiktok_scraper", ["TikTokScraperV52"]),
    ("tiktok_profile_scraper", ["TikTokProfileScraper"]),
    ("sentiment_analyzer_v2", ["SentimentAnalyzerV2"]),
]

import_ok = True
for mod_name, attrs in modules_to_check:
    try:
        mod = __import__(mod_name)
        missing_attrs = [a for a in attrs if not hasattr(mod, a)]
        if missing_attrs:
            print(f"  ⚠️  {mod_name} → import OK tapi missing: {missing_attrs}")
            import_ok = False
        else:
            print(f"  ✅ {mod_name} → OK ({', '.join(attrs)})")
    except ImportError as e:
        print(f"  ❌ {mod_name} → GAGAL import: {e}")
        import_ok = False
    except Exception as e:
        print(f"  ⚠️  {mod_name} → Error: {e}")

# ── CEK SESSION VIA INJECTOR ─────────────────────────────────────
print("\n🔑 SESSION VIA INJECTOR:")
try:
    from tiktok_cookie_injector import has_valid_session, get_session_info
    valid = has_valid_session()
    info = get_session_info()
    print(f"  {'✅' if valid else '❌'} has_valid_session() = {valid}")
    if info:
        for k, v in info.items():
            print(f"     {k}: {v}")
except Exception as e:
    print(f"  ❌ Error: {e}")

# ── RINGKASAN ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  RINGKASAN MASALAH")
print("=" * 60)

if not all_ok:
    print("\n❌ MASALAH: Beberapa file engine tidak ditemukan!")
    print("   Pastikan semua file .py ada di folder engine/")
elif not os.path.isfile(SESSION_FILE):
    print("\n❌ MASALAH UTAMA: Session file tidak ada!")
    print("   → Buka UI Settings dan paste cookie JSON dari Cookie-Editor")
    print("   → Atau jalankan: python tiktok_session_manager.py")
elif not import_ok:
    print("\n❌ MASALAH: Import gagal — cek dependency yang kurang")
    print("   Jalankan: pip install playwright colorama python-dotenv")
    print("             playwright install chromium")
else:
    print("\n✅ Semua cek OK! Kalau masih gagal scrape:")
    print("   1. Session mungkin expired — export ulang cookies dari browser")
    print("   2. TikTok rate limit — tunggu 30-60 menit")
    print("   3. Video private atau komentar dinonaktifkan")
    print("   4. Coba set TIKTOK_HEADLESS=False di .env untuk debug visual")

print()

# ── OPTIONAL: TEST SCRAPE ──────────────────────────────────────────
test_url = input("\n🧪 Test scrape? Masukkan URL TikTok (Enter untuk skip): ").strip()
if test_url:
    print(f"\n⏳ Mencoba scrape: {test_url[:60]}...")
    print("   (Max 5 komentar, untuk test saja)\n")
    try:
        from tiktok_scraper import TikTokScraperV52
        with TikTokScraperV52() as scraper:
            result = scraper.scrape_post_comments(test_url, 5)
            cc = result.get("comments_count", 0)
            method = result.get("method", "?")
            if cc > 0:
                print(f"\n✅ BERHASIL! {cc} komentar via [{method}]")
                print("\n🏆 TOP 3 LIKED:")
                comments = sorted(result.get("comments", []), key=lambda c: c.get("like_count", 0), reverse=True)
                for i, c in enumerate(comments[:3], 1):
                    print(f"  #{i} @{c['username']} [{c.get('like_count', 0)} ❤] — {c['text'][:60]}")
            else:
                err = result.get("error", "Unknown")
                print(f"\n❌ Gagal: {err}")
                print("   Cek session cookies atau coba URL lain")
    except Exception as e:
        print(f"\n❌ Exception: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)