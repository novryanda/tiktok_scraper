"""
tiktok_warmup.py
================
Modul warmup anti-bot terpusat untuk semua scraper TikTok.
Dipakai oleh: TikTokScraperV58, TikTokProfileScraper, TikTokCheckpointMixin,
              TikTokSearchScraper.

Filosofi:
  - Warm-up HARUS terasa seperti manusia: delay acak panjang, scroll lambat,
    mouse movement, jeda membaca, kadang hover elemen, scroll balik ke atas.
  - JANGAN scroll terus menerus cepat — itu pola bot yang paling mudah dideteksi.
  - Setelah warm-up baru redirect ke URL target.
  - Inter-request cooling juga pakai pola yang sama.

Cara pakai:
    from tiktok_warmup import TikTokWarmupMixin
    class TikTokScraperV58(TikTokWarmupMixin, TikTokCheckpointMixin):
        ...
    # Lalu panggil:
    self.warmup_natural(label="pre-scrape")
    # Sebelum goto target:
    self.page.goto(url, ...)
"""

import time
import random
import os
from typing import Optional
from colorama import Fore


# ── CONFIG via ENV ───────────────────────────────────────────────────────────
_WARMUP_SECONDS_MIN = int(os.getenv("TIKTOK_WARMUP_MIN", "25"))
_WARMUP_SECONDS_MAX = int(os.getenv("TIKTOK_WARMUP_MAX", "45"))
_SKIP_WARMUP        = os.getenv("TIKTOK_SKIP_WARMUP", "False").lower() == "true"

# Halaman yang dikunjungi selama warmup (acak subset)
_WARMUP_PAGES = [
    "https://www.tiktok.com/",
    "https://www.tiktok.com/foryou",
    "https://www.tiktok.com/explore",
    "https://www.tiktok.com/trending",
]

# Trending hashtag Indonesia — agar halaman terasa natural
_WARMUP_SEARCH_TERMS = [
    "trending", "viral", "fyp", "comedy", "music",
    "dance", "food", "travel", "jakarta", "indonesia",
]


class TikTokWarmupMixin:
    """
    Mixin yang memberikan metode warmup anti-bot untuk semua kelas scraper TikTok.
    Kelas yang memakai mixin ini HARUS punya `self.page` (Playwright Page).
    """

    # Flag: sudah warmup belum dalam sesi ini
    _warmup_done: bool = False

    # ════════════════════════════════════════════════════════════
    # CORE: natural warmup — buka FYP, scroll pelan, mouse natural
    # ════════════════════════════════════════════════════════════

    def warmup_natural(
        self,
        label: str = "warmup",
        force: bool = False,
    ) -> bool:
        """
        Lakukan warmup natural di homepage TikTok sebelum navigasi ke target.

        Args:
            label:  label untuk logging (e.g. "pre-scrape", "pre-search")
            force:  True = paksa warmup meski sudah pernah dilakukan

        Returns:
            True jika warmup dilakukan, False jika di-skip.
        """
        if _SKIP_WARMUP and not force:
            print(Fore.CYAN + f"   ⏭️  [{label}] Warmup di-skip (TIKTOK_SKIP_WARMUP=True)")
            return False

        if self._warmup_done and not force:
            print(Fore.CYAN + f"   ⏭️  [{label}] Warmup di-skip (sudah dilakukan sesi ini)")
            return False

        if not getattr(self, "page", None):
            print(Fore.YELLOW + f"   ⚠️  [{label}] Warmup: self.page belum tersedia")
            return False

        warmup_secs = random.randint(_WARMUP_SECONDS_MIN, _WARMUP_SECONDS_MAX)

        print(Fore.YELLOW + "\n" + "═" * 68)
        print(Fore.YELLOW + f"  🌡️  WARMUP [{label}] — {warmup_secs}s natural browsing TikTok")
        print(Fore.YELLOW + "═" * 68)

        try:
            # ── 1. Buka halaman awal (acak antara FYP atau homepage) ──
            start_page = random.choice(_WARMUP_PAGES[:2])
            print(Fore.CYAN + f"   🌍 Buka: {start_page}")
            try:
                self.page.goto(start_page, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                # Fallback kalau domcontentloaded timeout
                try:
                    self.page.goto("https://www.tiktok.com/", wait_until="commit", timeout=15000)
                except Exception:
                    pass

            # ── 2. Jeda awal — "membaca" konten ──
            _human_pause(3.5, 6.0, label="initial read")

            # ── 3. Cek captcha sebelum mulai scroll ──
            if hasattr(self, "_detect_captcha") and self._detect_captcha():
                print(Fore.RED + "   🛑 CAPTCHA saat warmup!")
                if hasattr(self, "_wait_for_captcha_solve"):
                    self._wait_for_captcha_solve()
                elif hasattr(self, "_wait_captcha"):
                    self._wait_captcha()

            # ── 4. Tutup popup jika ada ──
            if hasattr(self, "_close_popups"):
                self._close_popups()

            # ── 5. Scroll natural sampai waktu habis ──
            deadline = time.time() + warmup_secs - 8  # sisakan 8s untuk fase akhir
            scroll_count = 0
            last_mouse_move = 0.0

            while time.time() < deadline:
                scroll_count += 1
                _natural_scroll(self.page, scroll_count)

                # Sesekali gerakkan mouse
                if time.time() - last_mouse_move > random.uniform(4, 9):
                    _natural_mouse_move(self.page)
                    last_mouse_move = time.time()

                # Sesekali "baca" — pause lebih panjang
                if scroll_count % random.randint(3, 6) == 0:
                    _human_pause(2.5, 5.5, label="reading pause")
                else:
                    _human_pause(1.8, 3.8, label="scroll pause")

                # Sesekali scroll BALIK ke atas (manusia scroll ke atas juga)
                if scroll_count % random.randint(7, 12) == 0:
                    _scroll_back_up(self.page)
                    _human_pause(1.5, 3.0, label="scroll up pause")

            # ── 6. Fase akhir: navigasi ke halaman explore / trending ──
            _warmup_explore_phase(self.page)

            print(Fore.GREEN + f"   ✅ Warmup [{label}] selesai ({scroll_count} scroll, {warmup_secs}s)")

        except Exception as e:
            print(Fore.YELLOW + f"   ⚠️  Warmup [{label}] partial error (lanjut tetap): {e}")

        self._warmup_done = True
        return True

    # ════════════════════════════════════════════════════════════
    # COOLING: browsing natural antara scrape satu URL ke URL lain
    # ════════════════════════════════════════════════════════════

    def cooling_browse(
        self,
        min_secs: int = 15,
        max_secs: int = 35,
        label: str = "cooling",
    ):
        """
        Browsing natural FYP antara dua scrape (inter-video / inter-profile cooling).
        Lebih pendek dari warmup, tapi tetap natural.
        """
        if not getattr(self, "page", None):
            time.sleep(random.uniform(min_secs, max_secs))
            return

        secs = random.randint(min_secs, max_secs)
        print(Fore.YELLOW + f"\n   😴 [{label}] Cooling {secs}s — natural FYP browsing...")

        try:
            try:
                self.page.goto(
                    random.choice(_WARMUP_PAGES[:2]),
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
            except Exception:
                pass

            deadline = time.time() + secs
            scroll_count = 0

            while time.time() < deadline:
                scroll_count += 1
                _natural_scroll(self.page, scroll_count)

                if scroll_count % random.randint(4, 7) == 0:
                    _natural_mouse_move(self.page)

                if scroll_count % random.randint(5, 9) == 0:
                    _scroll_back_up(self.page)
                    _human_pause(1.0, 2.5, label="up")

                _human_pause(1.5, 3.5, label="cooling scroll")

        except Exception as e:
            print(Fore.YELLOW + f"   ⚠️  Cooling error (sleep fallback): {e}")
            time.sleep(secs)

    # ════════════════════════════════════════════════════════════
    # PRE-NAV PAUSE: jeda singkat sebelum goto() URL target
    # ════════════════════════════════════════════════════════════

    def pre_nav_pause(self, label: str = "pre-nav"):
        """
        Jeda 3–8 detik sebelum navigasi ke URL target.
        Meniru manusia yang 'memutuskan' mau buka halaman setelah scrolling.
        """
        wait = random.uniform(3.0, 8.0)
        print(Fore.CYAN + f"   ⏳ [{label}] Pre-nav pause {wait:.1f}s...")
        time.sleep(wait)
        # Gerak mouse kecil sebelum klik
        if getattr(self, "page", None):
            try:
                _natural_mouse_move(self.page, subtle=True)
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — fungsi internal (tidak bergantung pada instance)
# ════════════════════════════════════════════════════════════════════════════

def _human_pause(min_s: float, max_s: float, label: str = ""):
    """Sleep dengan durasi acak, meniru manusia membaca/berpikir."""
    t = random.uniform(min_s, max_s)
    if label:
        pass  # tidak print tiap pause agar log tidak spam
    time.sleep(t)


def _natural_scroll(page, scroll_count: int):
    """
    Scroll dengan karakteristik manusia:
    - Jarak scroll bervariasi (pendek, sedang, sekali-kali panjang)
    - Kadang scroll dua kali kecil, bukan satu kali besar
    - Kecepatan scroll tidak konstan
    """
    try:
        # Pilih pola scroll
        roll = random.random()

        if roll < 0.50:
            # Scroll sedang — paling umum
            dist = random.randint(250, 450)
            page.evaluate(f"window.scrollBy({{top: {dist}, behavior: 'smooth'}})")

        elif roll < 0.75:
            # Scroll kecil × 2 — meniru finger scroll
            d1 = random.randint(80, 160)
            d2 = random.randint(80, 180)
            page.evaluate(f"window.scrollBy({{top: {d1}, behavior: 'smooth'}})")
            time.sleep(random.uniform(0.3, 0.7))
            page.evaluate(f"window.scrollBy({{top: {d2}, behavior: 'smooth'}})")

        elif roll < 0.88:
            # Scroll panjang — "melewati konten yang tidak menarik"
            dist = random.randint(500, 750)
            page.evaluate(f"window.scrollBy({{top: {dist}, behavior: 'smooth'}})")

        else:
            # Micro scroll — hampir tidak gerak (pause sambil lihat konten)
            dist = random.randint(30, 80)
            page.evaluate(f"window.scrollBy({{top: {dist}, behavior: 'smooth'}})")

    except Exception:
        pass


def _scroll_back_up(page):
    """Scroll balik ke atas sedikit — manusia melakukan ini."""
    try:
        dist = random.randint(100, 350)
        page.evaluate(f"window.scrollBy({{top: -{dist}, behavior: 'smooth'}})")
    except Exception:
        pass


def _natural_mouse_move(page, subtle: bool = False):
    """
    Gerakkan mouse secara natural.
    subtle=True → gerakan kecil (persiapan klik).
    subtle=False → gerakan acak lebih besar.
    """
    try:
        if subtle:
            # Gerakan kecil di sekitar tengah layar
            x = random.randint(600, 900)
            y = random.randint(300, 600)
        else:
            x = random.randint(200, 1500)
            y = random.randint(150, 750)
        page.mouse.move(x, y)
        # Sesekali gerak lagi ke posisi lain
        if random.random() < 0.4:
            time.sleep(random.uniform(0.2, 0.5))
            x2 = x + random.randint(-120, 120)
            y2 = y + random.randint(-80, 80)
            page.mouse.move(max(0, x2), max(0, y2))
    except Exception:
        pass


def _warmup_explore_phase(page):
    """
    Fase akhir warmup: navigasi singkat ke /explore atau hover elemen,
    meniru user yang 'selesai browsing FYP dan mau cari sesuatu'.
    """
    try:
        # 50% chance buka halaman explore
        if random.random() < 0.5:
            try:
                page.goto(
                    "https://www.tiktok.com/explore",
                    wait_until="domcontentloaded",
                    timeout=10000,
                )
                time.sleep(random.uniform(2.0, 4.0))
                # Scroll sekali di explore
                _natural_scroll(page, 1)
                time.sleep(random.uniform(1.5, 3.0))
            except Exception:
                pass
        else:
            # Hanya mouse move + micro scroll
            _natural_mouse_move(page)
            time.sleep(random.uniform(1.5, 3.5))
            _natural_scroll(page, 99)
            time.sleep(random.uniform(1.0, 2.5))
    except Exception:
        pass