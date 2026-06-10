# ============================================================
# TIKTOK SCRAPER V5.8 — ANTI-CAPTCHA (Manual Solve)
# ============================================================
# Added:
#   ✅ Deteksi CAPTCHA di setiap tahap
#   ✅ Jika CAPTCHA muncul, minta user solve di browser (headful)
#   ✅ Default HEADLESS=False agar user bisa interaksi
#   ✅ Random delay lebih panjang untuk hindari pola
#
# FIX (metadata views/likes):
#   ✅ _parse_metadata baca statsV2 (string) sbg fallback dari stats
#   ✅ _extract_metadata lebih tahan: UNIVERSAL_DATA -> SIGI_STATE + retry
#   ✅ _fetch_meta_via_api: fallback metadata via API item detail
#   ✅ _resolve_metadata: gabung SSR + API (dipakai post & checkpoint)
# ============================================================

import os
import re
import json
import time
import random
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from collections import Counter

from dotenv import load_dotenv
from colorama import Fore, init
from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeout

from sentiment_analyzer_v2 import SentimentAnalyzerV2
from tiktok_slang_extension import patch_analyzer_for_tiktok
from tiktok_cookie_injector import inject_cookies_sync, has_valid_session
from tiktok_scraper_checkpoint import TikTokCheckpointMixin

init(autoreset=True)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ── CONFIG ────────────────────────────────────────────────────
# Default headless = False agar user bisa solve CAPTCHA
HEADLESS               = os.getenv("TIKTOK_HEADLESS", "False").lower() == "true"
# Residential proxy: auth via Playwright proxy= (bukan --proxy-server Chrome).
# TIKTOK_PROXY_SERVER wajib; USER/PASS untuk provider ber-auth.
# TIKTOK_PROXY_SESSION = sticky session ID (IP tetap sepanjang scrape).
#   Kosong → auto-generate sekali per browser launch. Bisa pakai {session} di USER.
# TIKTOK_PROXY legacy: fallback server URL jika PROXY_SERVER belum diset.
PROXY_SERVER           = os.getenv("TIKTOK_PROXY_SERVER", "") or os.getenv("TIKTOK_PROXY", "")
PROXY_USER             = os.getenv("TIKTOK_PROXY_USER", "")
PROXY_PASS             = os.getenv("TIKTOK_PROXY_PASS", "")
PROXY_SESSION          = os.getenv("TIKTOK_PROXY_SESSION", "")
MAX_COMMENTS           = int(os.getenv("TIKTOK_MAX_COMMENTS", 100))
DELAY_BETWEEN_REQUESTS = int(os.getenv("TIKTOK_DELAY_BETWEEN_REQUESTS", 5))
SENTIMENT_MODE         = os.getenv("SENTIMENT_MODE", "rule_only")

TIKTOK_CHROME_PROFILE = os.path.join(os.getcwd(), "tiktok_chrome_real_profile")
OUTPUT_DIR            = "output_tiktok"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Tambahan delay untuk menghindari CAPTCHA
EXTRA_DELAY_BEFORE_NAV = random.uniform(3, 6)
EXTRA_DELAY_AFTER_NAV  = random.uniform(4, 8)


class TikTokScraperV58(TikTokCheckpointMixin):
    """
    TikTok Scraper V5.8 – dengan manual CAPTCHA solve
    """

    BATCH_COOLDOWN_MIN = int(os.getenv("TIKTOK_BATCH_COOLDOWN_MIN", "60"))
    BATCH_COOLDOWN_MAX = int(os.getenv("TIKTOK_BATCH_COOLDOWN_MAX", "120"))

    def __init__(self, sentiment_mode: str = SENTIMENT_MODE):
        print(Fore.CYAN + f"\n🧠 Initializing Sentiment Analyzer (mode: {sentiment_mode})...")
        self.sentiment = SentimentAnalyzerV2(mode=sentiment_mode, verbose=True)

        print(Fore.CYAN + "🔧 Patching analyzer with TikTok slang...")
        patch_analyzer_for_tiktok(self.sentiment)

        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

        self._last_scrape_time: float = 0.0
        self._min_gap_seconds: int = 60
        self._block_images_enabled: bool = False

        self._warmup_done: bool = False
        self._scrape_count: int = 0

        if has_valid_session():
            print(Fore.GREEN + "🍪 Mode: Cookie injection dari tt_session.json")
            self._use_cookie_mode = True
        elif os.path.exists(TIKTOK_CHROME_PROFILE) and os.listdir(TIKTOK_CHROME_PROFILE):
            print(Fore.GREEN + f"✅ Mode: Chrome profile ({TIKTOK_CHROME_PROFILE})")
            self._use_cookie_mode = False
        else:
            raise RuntimeError(
                "Tidak ada session TikTok yang valid. "
                "Tambahkan cookies via tt_session.json atau jalankan tiktok_login_helper.py"
            )

        print(Fore.GREEN + "✅ TikTok Scraper V5.8 siap")

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def _build_proxy_config(self) -> Optional[Dict[str, str]]:
        """Proxy Playwright dengan auth; satu session sticky per browser launch."""
        if not PROXY_SERVER:
            return None
        cfg: Dict[str, str] = {"server": PROXY_SERVER}
        if PROXY_USER:
            username = PROXY_USER
            if "{session}" in PROXY_USER:
                session = PROXY_SESSION or f"sticky_{int(time.time())}_{random.randint(1000, 9999)}"
                username = PROXY_USER.replace("{session}", session)
            cfg["username"] = username
        if PROXY_PASS:
            cfg["password"] = PROXY_PASS
        print(Fore.CYAN + f"   🌐 Proxy: {PROXY_SERVER} (sticky session, satu IP per scrape)")
        return cfg

    # ── BROWSER SETUP (sama seperti V5.7, tapi tambah headful hint) ──
    def _build_context(self):
        self.playwright = sync_playwright().start()
        proxy_config = self._build_proxy_config()

        args = [
            "--window-size=1920,1080",
            "--window-position=0,0",
            "--disable-blink-features=AutomationControlled",
            "--disable-notifications",
            "--mute-audio",
            "--disable-infobars",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=IsolateOrigins,site-per-process,AutomationControlled",
            "--exclude-switches=enable-automation",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--no-pings",
            "--password-store=basic",
            "--use-mock-keychain",
            "--metrics-recording-only",
        ]
        args = [a for a in args if a]

        # Docker/root: Chrome butuh --no-sandbox agar tidak crash
        if os.getenv("CHROME_NO_SANDBOX", "False").lower() == "true":
            args += ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]

        stealth_script = """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {name: 'PDF Viewer', filename: 'internal-pdf-viewer'},
                    {name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer'},
                    {name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer'},
                ]
            });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['id-ID', 'id', 'en-US', 'en']});
            Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            try { delete Object.getPrototypeOf(navigator).webdriver; } catch(e) {}
            try { delete navigator.__proto__.webdriver; } catch(e) {}
            Object.defineProperty(screen, 'width', {get: () => 1920});
            Object.defineProperty(screen, 'height', {get: () => 1080});
            Object.defineProperty(screen, 'availWidth', {get: () => 1920});
            Object.defineProperty(screen, 'availHeight', {get: () => 1040});
            Object.defineProperty(screen, 'colorDepth', {get: () => 24});
            Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : originalQuery(parameters)
            );
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel(R) Iris(R) Xe Graphics';
                return getParameter.call(this, parameter);
            };
            if (!navigator.connection) {
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({downlink: 10, effectiveType: '4g', rtt: 50, saveData: false})
                });
            }
        """

        if self._use_cookie_mode:
            persistent_profile = os.path.join(os.getcwd(), "tiktok_cookie_profile_persistent")
            os.makedirs(persistent_profile, exist_ok=True)
            print(Fore.CYAN + f"   🍪 Cookie mode: persistent profile → {os.path.basename(persistent_profile)}")

            context = self.playwright.chromium.launch_persistent_context(
                persistent_profile,
                headless=HEADLESS,
                slow_mo=random.randint(120, 280),
                args=args,
                proxy=proxy_config,
                no_viewport=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                locale="id-ID",
                timezone_id="Asia/Jakarta",
                bypass_csp=True,
                java_script_enabled=True,
            )
        else:
            context = self.playwright.chromium.launch_persistent_context(
                TIKTOK_CHROME_PROFILE,
                channel="chrome",
                headless=HEADLESS,
                slow_mo=random.randint(120, 280),
                args=args,
                proxy=proxy_config,
                no_viewport=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                locale="id-ID",
                timezone_id="Asia/Jakarta",
                bypass_csp=True,
                java_script_enabled=True,
            )

        context.on("page", lambda page: page.add_init_script(stealth_script))

        if self._use_cookie_mode:
            try:
                n = inject_cookies_sync(context)
                print(Fore.GREEN + f"🍪 Berhasil inject {n} cookies dari tt_session.json")
            except Exception as e:
                raise RuntimeError(f"Gagal inject cookies TikTok: {e}")

        return context

    def _is_logged_in(self) -> bool:
        try:
            login_button_selectors = [
                "[data-e2e='top-login-button']",
                "button:has-text('Log in')",
                "button:has-text('Log masuk')",
                "a:has-text('Log in')",
                "a:has-text('Log masuk')",
            ]
            for sel in login_button_selectors:
                try:
                    loc = self.page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible(timeout=1500):
                        return False
                except:
                    pass
            try:
                if self.page.locator("[data-e2e='nav-profile']").count() > 0:
                    return True
            except:
                pass
            cookies = self.context.cookies("https://www.tiktok.com")
            for c in cookies:
                if c.get("name") in ("sessionid", "sessionid_ss") and c.get("value"):
                    return True
            return False
        except Exception as e:
            print(Fore.YELLOW + f"   ⚠️  Login check error: {e}")
            return False

    # ── CAPTCHA DETECTION & MANUAL SOLVE ─────────────────────────
    def _detect_captcha(self) -> bool:
        try:
            result = self.page.evaluate("""() => {
                const captchaSelectors = [
                    '[id*="captcha"]', '[class*="captcha"]', '[id*="verify"]',
                    '.tt-verify', '#captcha-verify-container', '#captcha_container',
                    '[class*="secsdk-captcha"]', '[class*="cap-flex"]',
                    'div[role="dialog"] img[src*="captcha"]',
                ];
                const bodyText = document.body ? document.body.innerText : '';
                const textTriggers = [
                    'Tarik penggeser', 'sesuai dengan puzzle', 'Drag the slider',
                    'fit the puzzle', 'Geser untuk', 'Verifikasi', 'verification required',
                    'Memverifikasi', 'Verifying',
                ];
                for (const sel of captchaSelectors) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 50 && rect.height > 50) return {found: true, selector: sel};
                    }
                }
                for (const t of textTriggers) {
                    if (bodyText.includes(t)) return {found: true, selector: 'text:' + t};
                }
                return {found: false};
            }""")
            return bool(result and result.get("found"))
        except Exception:
            return False

    def _wait_for_captcha_solve(self, timeout_seconds: int = 180) -> bool:
        """Minta user menyelesaikan CAPTCHA secara manual di browser."""
        prev_blocking = self._block_images_enabled
        self._block_images_enabled = False
        print(Fore.RED + "\n" + "=" * 70)
        print(Fore.RED + "🛑 CAPTCHA TERDETEKSI!")
        print(Fore.RED + "=" * 70)
        print(Fore.YELLOW + "TikTok meminta verifikasi. Selesaikan CAPTCHA di browser yang terbuka.")
        print(Fore.YELLOW + f"Anda punya waktu {timeout_seconds} detik. Scraping akan dilanjutkan otomatis setelah selesai.\n")

        deadline = time.time() + timeout_seconds
        last_check = 0
        while time.time() < deadline:
            if not self._detect_captcha():
                print(Fore.GREEN + "\n✅ CAPTCHA teratasi! Melanjutkan...")
                time.sleep(2)
                self._block_images_enabled = prev_blocking
                return True
            if time.time() - last_check > 10:
                remaining = int(deadline - time.time())
                print(Fore.YELLOW + f"   ⏳ Masih menunggu CAPTCHA... ({remaining} detik tersisa)")
                last_check = time.time()
            time.sleep(2)
        print(Fore.RED + "\n❌ Timeout CAPTCHA. Batalkan scraping.")
        self._block_images_enabled = prev_blocking
        return False

    def _enforce_rate_limit(self):
        if self._last_scrape_time <= 0:
            return
        elapsed = time.time() - self._last_scrape_time
        if elapsed < self._min_gap_seconds:
            wait = self._min_gap_seconds - elapsed
            print(Fore.YELLOW + f"\n⏱️  Rate-limit guard: tunggu {wait:.0f}s sebelum scrape berikutnya...")
            time.sleep(wait)

    def initialize_browser(self):
        if self.context:
            return
        print(Fore.CYAN + "\n🌐 Membuka browser TikTok (mode: headful jika tidak headless)...")
        self.context = self._build_context()
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self._block_images_enabled = False

        captcha_safe_patterns = [
            "captcha", "verify", "secsdk", "tiktokcdn-us.com", "/aweme/",
            "rmsec", "tiktokv.com/captcha", "byteoversea.com", "/captcha-sdk",
            "favicon", "/icon",
        ]

        def block_heavy_resources(route):
            try:
                resource_type = route.request.resource_type
                url = route.request.url.lower()
                for pat in captcha_safe_patterns:
                    if pat in url:
                        route.continue_()
                        return
                if resource_type == "font":
                    route.continue_()
                    return
                if not self._block_images_enabled:
                    route.continue_()
                    return
                if resource_type in ["image", "media"]:
                    route.abort()
                else:
                    route.continue_()
            except Exception:
                try:
                    route.continue_()
                except:
                    pass

        self.page.route("**/*", block_heavy_resources)

        print(Fore.CYAN + "   ☕ Warming up — buka homepage TikTok dulu...")
        self.page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(5, 8))
        self._close_popups()

        if "login" in self.page.url:
            self.close()
            raise RuntimeError("Redirect ke login page — session expired.")
        if not self._is_logged_in():
            self.close()
            raise RuntimeError("Browser terbuka tapi belum login ke TikTok.")
        print(Fore.GREEN + "✅ Browser TikTok siap (LOGGED IN ✓)")

    # ── WARMUP & COOLING (sama seperti V5.7) ──
    def _warm_up_session(self):
        if self._warmup_done:
            print(Fore.CYAN + "   ⏭️  Warm-up di-skip (sudah dilakukan sebelumnya)")
            return
        skip = os.getenv("TIKTOK_SKIP_WARMUP", "False").lower() == "true"
        if skip:
            print(Fore.CYAN + "   ⏭️  Warm-up di-skip (TIKTOK_SKIP_WARMUP=True)")
            self._warmup_done = True
            return
        warm_up_time = int(os.getenv("TIKTOK_WARMUP_SECONDS", "30"))
        print(Fore.YELLOW + "\n" + "=" * 70)
        print(Fore.YELLOW + f"🔥 WARM-UP SESSION ({warm_up_time}s) — natural browsing (sekali saja)")
        print(Fore.YELLOW + "=" * 70)
        try:
            self.page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded", timeout=15000)
        except:
            self.page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(random.uniform(4, 7))
        scroll_count = 0
        deadline = time.time() + warm_up_time - 5
        while time.time() < deadline:
            scroll_amount = random.randint(200, 450)
            self.page.evaluate(f"window.scrollBy(0, {scroll_amount});")
            scroll_count += 1
            if scroll_count % 4 == 0:
                try:
                    self.page.mouse.move(random.randint(400, 1100), random.randint(200, 600))
                except:
                    pass
            time.sleep(random.uniform(2.5, 4.5))
        print(Fore.GREEN + f"   ✅ Warm-up selesai ({scroll_count} scrolls)")
        time.sleep(random.uniform(2, 4))
        self._warmup_done = True

    def _inter_video_cooling(self):
        if self._scrape_count == 0:
            return
        cooldown = random.uniform(self.BATCH_COOLDOWN_MIN, self.BATCH_COOLDOWN_MAX)
        print(Fore.YELLOW + "\n" + "=" * 70)
        print(Fore.YELLOW + f"😴 INTER-VIDEO COOLING ({cooldown:.0f}s) — browse FYP natural...")
        print(Fore.YELLOW + "=" * 70)
        try:
            self.page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(3, 5))
        except:
            time.sleep(cooldown)
            return
        scroll_count = 0
        deadline = time.time() + cooldown - 5
        while time.time() < deadline:
            scroll_amount = random.randint(300, 700)
            try:
                self.page.evaluate(f"window.scrollBy(0, {scroll_amount});")
            except:
                break
            scroll_count += 1
            if scroll_count % 5 == 0:
                try:
                    self.page.mouse.move(random.randint(300, 1200), random.randint(200, 700))
                except:
                    pass
            if scroll_count % 8 == 0:
                time.sleep(random.uniform(4, 9))
            else:
                time.sleep(random.uniform(1.5, 3.5))
        remaining = max(0, deadline + 5 - time.time())
        if remaining > 0:
            time.sleep(remaining)
        print(Fore.GREEN + f"   ✅ Cooling selesai")

    def _close_popups(self):
        popup_selectors = [
            "div[role='dialog'] button:has-text('Not now')",
            "div[role='dialog'] button:has-text('Decline')",
            "div[role='dialog'] button:has-text('Close')",
            "div[role='dialog'] button:has-text('Cancel')",
            "div[role='dialog'] button:has-text('Accept all')",
            "button[aria-label='Close']",
        ]
        for selector in popup_selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    self.page.locator(selector).first.click(timeout=2000)
                    time.sleep(0.8)
            except:
                pass

    def close(self):
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
        except:
            pass

    # ── URL PARSER, CAPTION, METADATA ───────────────────────────
    @staticmethod
    def _parse_url(url: str) -> Dict:
        result = {"username": "", "video_id": "", "url": url}
        m = re.search(r"tiktok\.com/@([\w\.\-]+)/video/(\d+)", url)
        if m:
            result["username"] = m.group(1)
            result["video_id"] = m.group(2)
            return result
        if "vt.tiktok.com" in url or "/t/" in url:
            result["is_shortlink"] = True
        return result

    def _resolve_shortlink(self, url: str) -> str:
        try:
            self.page.goto(url, wait_until="domcontentloaded")
            time.sleep(random.uniform(4, 6))
            return self.page.url
        except Exception as e:
            print(Fore.RED + f"   ❌ Resolve shortlink gagal: {e}")
            return url

    def _extract_caption_multi_strategy(self) -> str:
        caption = ""
        try:
            meta = self._extract_metadata()
            data = meta.get("data", {}) or {}
            caption = (data.get("desc", "") or data.get("description", "") or data.get("title", "") or "")
            if caption:
                print(Fore.CYAN + f"   ✅ Caption dari metadata ({meta.get('source')})")
                return caption.strip()
        except:
            pass
        try:
            caption = self.page.evaluate("""() => {
                const sel = '[data-e2e="video-desc"], [data-e2e="browse-video-desc"], [class*="DivVideoDescription"]';
                const el = document.querySelector(sel);
                return el ? el.textContent.trim() : '';
            }""")
            if caption:
                print(Fore.CYAN + "   ✅ Caption dari DOM")
                return caption.strip()
        except:
            pass
        try:
            caption = self.page.evaluate("""() => {
                const meta = document.querySelector('meta[property="og:description"]');
                return meta ? meta.content : '';
            }""")
            if caption:
                print(Fore.CYAN + "   ✅ Caption dari meta tags")
                return caption.strip()
        except:
            pass
        print(Fore.YELLOW + "   ⚠️  Caption tidak ditemukan")
        return ""

    def _extract_metadata(self) -> Dict:
        """Ambil metadata video dari SSR.
        Coba __UNIVERSAL_DATA_FOR_REHYDRATION__ dulu, lalu SIGI_STATE (format lama),
        dengan retry kecil kalau halaman belum sempat ter-hidrasi."""
        for _attempt in range(2):
            try:
                res = self.page.evaluate("""() => {
                    // 1) Format baru: __UNIVERSAL_DATA_FOR_REHYDRATION__
                    const u = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                    if (u) {
                        try {
                            const parsed = JSON.parse(u.textContent);
                            const scope = (parsed && parsed.__DEFAULT_SCOPE__) || {};
                            const vd = scope['webapp.video-detail'] || {};
                            const cands = [vd.itemInfo && vd.itemInfo.itemStruct, vd.itemStruct];
                            for (const c of cands) { if (c && c.id) return {source:'universal_data', data:c}; }
                        } catch(e) {}
                    }
                    // 2) Format lama: SIGI_STATE -> ItemModule
                    const sigi = document.getElementById('SIGI_STATE');
                    if (sigi) {
                        try {
                            const parsed = JSON.parse(sigi.textContent);
                            const im = parsed.ItemModule || {};
                            const keys = Object.keys(im);
                            if (keys.length) return {source:'sigi_state', data: im[keys[0]]};
                        } catch(e) {}
                    }
                    return {source:'none', data:{}};
                }""")
                if res and (res.get("data") or {}).get("id"):
                    return res
            except Exception:
                pass
            time.sleep(1.5)
        return {"source": "none", "data": {}}

    def _parse_metadata(self, meta_raw: Dict) -> Dict:
        default = {
            "video_id": "", "username": "", "author_id": "", "description": "",
            "play_count": 0, "digg_count": 0, "share_count": 0, "comment_count": 0,
            "collect_count": 0, "repost_count": 0, "download_count": 0,
            "duration": 0, "create_time": 0, "music_title": "", "hashtags": [],
        }
        data = meta_raw.get("data", {}) or {}
        if not data:
            return default
        default["video_id"] = str(data.get("id", "") or data.get("aweme_id", ""))

        # author bisa dict (UNIVERSAL_DATA) atau string (SIGI_STATE)
        author = data.get("author", {})
        if isinstance(author, str):
            default["username"] = author
        else:
            author = author or {}
            default["username"] = author.get("uniqueId", "") or author.get("unique_id", "")

        default["description"] = (data.get("desc", "") or "")[:1000]

        # TikTok kadang menaruh angka asli di statsV2 (nilai STRING),
        # sementara stats.playCount dll = 0 → baca keduanya.
        stats   = data.get("stats", {}) or {}
        statsv2 = data.get("statsV2", {}) or {}

        def _num(key):
            v = stats.get(key, 0)
            if not v:
                v = statsv2.get(key, 0)
            try:
                return int(v or 0)
            except (ValueError, TypeError):
                return 0

        default["play_count"]    = _num("playCount")
        default["digg_count"]    = _num("diggCount")
        default["share_count"]   = _num("shareCount")
        default["comment_count"] = _num("commentCount")
        default["collect_count"] = _num("collectCount")
        default["duration"]    = (data.get("video", {}) or {}).get("duration", 0)
        default["music_title"] = (data.get("music", {}) or {}).get("title", "")
        return default

    def _fetch_meta_via_api(self, video_id: str) -> Dict:
        """Fallback metadata via API item detail (kalau SSR kosong).
        Catatan: endpoint ini bisa berubah-ubah; kalau gagal akan return kosong
        dan kita tetap pakai apa pun yang berhasil didapat dari SSR."""
        if not video_id:
            return {"source": "none", "data": {}}
        try:
            result = self.page.evaluate(f"""async () => {{
                const url = `/api/item/detail/?itemId={video_id}&aid=1988`;
                const resp = await fetch(url, {{credentials: 'include'}});
                const text = await resp.text();
                try {{ return JSON.parse(text); }} catch(e) {{ return null; }}
            }}""")
            if result:
                item = (result.get("itemInfo") or {}).get("itemStruct") or {}
                if item.get("id"):
                    return {"source": "api_item_detail", "data": item}
        except Exception as e:
            print(Fore.YELLOW + f"   ⚠️  Meta API fallback error: {e}")
        return {"source": "none", "data": {}}

    def _resolve_metadata(self, parsed: Dict) -> Dict:
        """Resolusi metadata lengkap: baca SSR → kalau stats masih 0 → coba API.
        Dipakai BERSAMA oleh scrape_post_comments & checkpoint."""
        meta = self._parse_metadata(self._extract_metadata())
        vid = meta.get("video_id") or (parsed or {}).get("video_id", "")

        # Cek khusus play_count & digg_count — comment_count bisa ada walau views/likes = 0 (partial SSR TikTok)
        stats_kosong = not (meta.get("play_count") or meta.get("digg_count"))
        if vid and stats_kosong:
            print(Fore.YELLOW + "   ℹ️  Views/likes SSR kosong — coba ambil via API item detail...")
            api_meta = self._parse_metadata(self._fetch_meta_via_api(vid))
            for k in ("play_count", "digg_count", "share_count", "comment_count",
                      "collect_count", "duration", "music_title", "description", "username"):
                if not meta.get(k) and api_meta.get(k):
                    meta[k] = api_meta[k]
            if not meta.get("video_id"):
                meta["video_id"] = api_meta.get("video_id") or vid

        if not meta.get("video_id"):
            meta["video_id"] = vid
        if not meta.get("username"):
            meta["username"] = (parsed or {}).get("username", "")
        return meta

    # ── TRIGGER COMMENT PANEL ───────────────────────────────────
    def _trigger_comment_panel(self) -> bool:
        print(Fore.CYAN + "   💬 Trigger comment panel...")
        if self._detect_captcha():
            print(Fore.YELLOW + "      ⚠️  CAPTCHA sebelum trigger")
            if not self._wait_for_captcha_solve():
                return False
        comment_btn_selectors = [
            "[data-e2e='comment-icon']",
            "button[aria-label*='omment']",
            "button[aria-label*='Komentar']",
            "[data-e2e='browse-video-comment']",
        ]
        clicked = False
        for sel in comment_btn_selectors:
            try:
                loc = self.page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible(timeout=1500):
                    loc.first.click(timeout=3000)
                    print(Fore.CYAN + f"      ✓ Clicked: {sel}")
                    clicked = True
                    time.sleep(1.5)
                    break
            except:
                continue
        if not clicked:
            print(Fore.YELLOW + "      ⚠️  Gagal klik tombol komentar")
            return False
        time.sleep(random.uniform(2, 4))
        container = self.page.locator("[class*='DivCommentMain'], [data-e2e='comment-list']")
        if container.count() == 0:
            print(Fore.YELLOW + "      ⚠️  Comment panel tidak muncul")
            return False
        print(Fore.GREEN + "      ✓ Comment panel ready")
        return True

    # ── CDP & DOM FETCH (dengan CAPTCHA handling) ───────────────
    def _fetch_via_cdp(self, video_id: str, max_comments: int) -> List[Dict]:
        all_comments = []
        self._block_images_enabled = True
        print(Fore.CYAN + "   🛡️  Resource blocking ON (image/media) — fetch komentar via API")
        try:
            for sort_type in [4, 0]:
                cursor = 0
                page = 0
                max_pages = 100
                print(Fore.CYAN + f"   📡 CDP Fetch (sort_type={sort_type})...")
                time.sleep(random.uniform(15, 25))
                while len(all_comments) < max_comments and page < max_pages:
                    page += 1
                    try:
                        result = self.page.evaluate(f"""async () => {{
                            const awemeId = '{video_id}';
                            const cursor = {cursor};
                            const sortType = {sort_type};
                            const url = `/api/comment/list/?aweme_id=${{awemeId}}&cursor=${{cursor}}&count=20&sort_type=${{sortType}}&aid=1988`;
                            const resp = await fetch(url, {{credentials: 'include'}});
                            const text = await resp.text();
                            try {{
                                return JSON.parse(text);
                            }} catch(e) {{
                                return {{error: 'not_json', raw: text.slice(0,500)}};
                            }}
                        }}""")
                        if not result or result.get("error"):
                            print(Fore.YELLOW + f"   ⚠️  CDP response error: {result.get('raw','')[:100]}")
                            if self._detect_captcha():
                                if not self._wait_for_captcha_solve():
                                    break
                                continue
                            break
                        if result.get("status_code") == 5:
                            print(Fore.YELLOW + "   ⏳ Rate limit, tunggu 30s...")
                            time.sleep(30)
                            continue
                        comments_raw = result.get("comments", [])
                        if not comments_raw:
                            break
                        for c in comments_raw:
                            user = c.get("user", {})
                            username = user.get("unique_id", "")
                            text = c.get("text", "")
                            if not username or not text:
                                continue
                            like_count = c.get("digg_count", 0) or c.get("like_count", 0)
                            all_comments.append({
                                "username": username,
                                "nickname": user.get("nickname", ""),
                                "text": text,
                                "comment_id": str(c.get("cid", "")),
                                "like_count": like_count,
                                "created_at": c.get("create_time", 0),
                                "reply_count": c.get("reply_comment_total", 0),
                            })
                            if len(all_comments) >= max_comments:
                                break
                        print(Fore.CYAN + f"      Page {page}: +{len(comments_raw)} (total {len(all_comments)})")
                        cursor = result.get("cursor", 0)
                        if not result.get("has_more", False):
                            break
                        time.sleep(random.uniform(2, 4))
                    except Exception as e:
                        print(Fore.YELLOW + f"   ⚠️  CDP exception: {e}")
                        if self._detect_captcha():
                            self._wait_for_captcha_solve()
                        break
                if all_comments:
                    break
        finally:
            self._block_images_enabled = False
        return all_comments

    def _fetch_via_dom(self, max_comments: int) -> List[Dict]:
        print(Fore.CYAN + "   🖱️  DOM Scraping...")
        if self._detect_captcha():
            if not self._wait_for_captcha_solve():
                return []
        try:
            self._sort_dom_comments_newest()
            n_scrolls = min(max_comments * 2 + 10, 80)
            prev = 0
            stall = 0
            all_comments = []
            for scroll_idx in range(n_scrolls):
                self.page.evaluate("""() => {
                    const sel = '[class*="DivCommentListContainer"], [data-e2e="comment-list"]';
                    const el = document.querySelector(sel);
                    if (el) el.scrollTop += 500;
                }""")
                time.sleep(random.uniform(1, 1.5))
                current = self._parse_comments_from_dom()
                all_comments = current
                if len(current) > prev:
                    stall = 0
                    prev = len(current)
                else:
                    stall += 1
                if len(current) >= max_comments or stall >= 8:
                    break
                if scroll_idx % 10 == 0:
                    print(Fore.CYAN + f"      Scroll {scroll_idx+1}: {len(current)} komentar")
            return all_comments[:max_comments]
        except Exception as e:
            print(Fore.RED + f"   ❌ DOM error: {e}")
            return []

    def _sort_dom_comments_newest(self):
        try:
            btn = self.page.locator("[data-e2e='comment-sort-btn']")
            if btn.count():
                btn.first.click(timeout=2000)
                time.sleep(1)
                newest = self.page.locator("li:has-text('Terbaru'), div[role='option']:has-text('Terbaru')")
                if newest.count():
                    newest.first.click()
                    time.sleep(1.5)
        except:
            pass

    def _parse_comments_from_dom(self) -> List[Dict]:
        try:
            return self.page.evaluate("""() => {
                const results = [];
                const seen = new Set();
                const commentDivs = document.querySelectorAll('[data-e2e="comment-username-1"]');
                for (const el of commentDivs) {
                    try {
                        let username = el.textContent.trim().replace(/^@/, '');
                        let text = '';
                        let parent = el.parentElement;
                        for (let i=0; i<5; i++) {
                            if (!parent) break;
                            const t = parent.querySelector('[data-e2e="comment-level-1"]');
                            if (t) { text = t.textContent.trim(); break; }
                            parent = parent.parentElement;
                        }
                        if (!username || !text) continue;
                        const key = username + '::' + text;
                        if (seen.has(key)) continue;
                        seen.add(key);
                        let likeCount = 0;
                        const likeSpan = parent?.querySelector('[data-e2e="comment-like-count"]');
                        if (likeSpan) likeCount = parseInt(likeSpan.textContent.replace(/[^0-9]/g,'')) || 0;
                        results.push({
                            username, nickname: username, text,
                            comment_id: '', like_count: likeCount,
                            created_at: 0, reply_count: 0
                        });
                    } catch(e) {}
                }
                return results;
            }""")
        except:
            return []

    def _dedup_comments(self, raw: List[Dict]) -> List[Dict]:
        seen = set()
        unique = []
        for c in raw:
            key = c.get("comment_id") or hashlib.md5(f"{c['username']}::{c['text']}".encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)
        return unique

    # ── LIKERS FETCH (dengan CAPTCHA handling) ───────────────────
    def _fetch_likers_via_cdp(self, aweme_id: str, max_likers: int = 500) -> List[Dict]:
        likers = []
        cursor = 0
        print(Fore.CYAN + f"   👍 Fetching likers...")
        for _ in range(50):
            try:
                result = self.page.evaluate(f"""async () => {{
                    const url = `/api/aweme/v1/web/aweme/like/?aweme_id={aweme_id}&cursor={cursor}&count=20`;
                    const resp = await fetch(url, {{credentials: 'include'}});
                    return await resp.json();
                }}""")
                if not result or result.get("status_code") != 0:
                    if self._detect_captcha():
                        if not self._wait_for_captcha_solve():
                            break
                        continue
                    break
                users = result.get("users", [])
                if not users:
                    break
                for u in users:
                    likers.append({
                        "user_id": str(u.get("uid", "")),
                        "username": u.get("unique_id", ""),
                        "nickname": u.get("nickname", ""),
                        "avatar_url": u.get("avatar_thumb", {}).get("url_list", [None])[0],
                        "is_verified": u.get("verified", False),
                        "is_private": u.get("secret", False),
                    })
                    if len(likers) >= max_likers:
                        break
                cursor = result.get("cursor", 0)
                if not result.get("has_more", False):
                    break
                time.sleep(random.uniform(4, 8))
            except Exception as e:
                print(Fore.YELLOW + f"   ⚠️  Likers error: {e}")
                break
        return likers[:max_likers]

    # ── ACTIVE COMMENTERS (sama) ─────────────────────────────────
    def _build_active_commenters(self, comments: List[Dict]) -> List[Dict]:
        users = {}
        for c in comments:
            uname = c.get("username")
            if not uname:
                continue
            if uname not in users:
                users[uname] = {"username": uname, "comment_count": 0, "reply_count": 0, "total_likes": 0, "categories": Counter(), "sentiments": Counter()}
            u = users[uname]
            u["comment_count"] += 1
            u["total_likes"] += c.get("like_count", 0)
            u["categories"][c.get("category", "NEUTRAL")] += 1
            u["sentiments"][c.get("sentiment", "")] += 1
            for r in c.get("replies", []):
                rname = r.get("username")
                if not rname:
                    continue
                if rname not in users:
                    users[rname] = {"username": rname, "comment_count": 0, "reply_count": 0, "total_likes": 0, "categories": Counter(), "sentiments": Counter()}
                ru = users[rname]
                ru["reply_count"] += 1
                ru["total_likes"] += r.get("like_count", 0)
                ru["categories"][r.get("category", "NEUTRAL")] += 1
                ru["sentiments"][r.get("sentiment", "")] += 1
        result = []
        for u in users.values():
            total = u["comment_count"] + u["reply_count"]
            dom_cat = u["categories"].most_common(1)[0][0] if u["categories"] else "NEUTRAL"
            dom_sent = u["sentiments"].most_common(1)[0][0] if u["sentiments"] else ""
            result.append({
                "username": u["username"],
                "comment_count": u["comment_count"],
                "reply_count": u["reply_count"],
                "total_interactions": total,
                "total_likes": u["total_likes"],
                "dominant_category": dom_cat,
                "dominant_sentiment": dom_sent,
            })
        result.sort(key=lambda x: (x["total_interactions"], x["total_likes"]), reverse=True)
        return result[:30]

    # ── MAIN SCRAPE FLOW ─────────────────────────────────────────
    def scrape_post_comments(self, post_url: str, max_comments: int = 100,
                             include_replies: bool = True, max_replies_per_comment: int = 20) -> Dict:
        print(Fore.CYAN + "\n" + "=" * 70)
        print(Fore.CYAN + f"🎵 {post_url[:70]}")
        print(Fore.CYAN + "=" * 70)

        result = {
            "url": post_url, "scraped_at": datetime.now().isoformat(),
            "sentiment_mode": self.sentiment.mode, "platform": "tiktok",
            "video_id": "", "username": "", "description": "",
            "play_count": 0, "digg_count": 0, "share_count": 0, "comment_count": 0,
            "music_title": "",
            "method": "", "comments": [], "comments_count": 0,
            "sentiment_summary": {}, "caption_sentiment": {},
        }

        try:
            self.initialize_browser()
            self._enforce_rate_limit()

            parsed = self._parse_url(post_url)
            if parsed.get("is_shortlink"):
                print(Fore.CYAN + "🔗 Resolving shortlink...")
                resolved = self._resolve_shortlink(post_url)
                parsed = self._parse_url(resolved)
                clean_url = resolved
            else:
                clean_url = post_url.split("?")[0].rstrip("/")

            self._warm_up_session()
            if self._scrape_count > 0:
                self._inter_video_cooling()

            # Navigasi dengan delay
            time.sleep(EXTRA_DELAY_BEFORE_NAV)
            print(Fore.YELLOW + f"\n🌍 Navigasi ke: {clean_url}")
            self.page.goto(clean_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(EXTRA_DELAY_AFTER_NAV)

            if self._detect_captcha():
                if not self._wait_for_captcha_solve():
                    raise Exception("CAPTCHA tidak diselesaikan")

            self._close_popups()
            print(Fore.CYAN + "   📜 Scroll awal...")
            time.sleep(random.uniform(2.5, 5))
            for _ in range(3):
                self.page.mouse.wheel(0, random.randint(200, 400))
                time.sleep(random.uniform(2.5, 5))

            # ── METADATA: SSR + fallback API (views/likes) ──
            meta = self._resolve_metadata(parsed)
            for k in ["video_id", "username", "description", "play_count",
                      "digg_count", "share_count", "comment_count", "music_title"]:
                if meta.get(k):
                    result[k] = meta[k]
            if not result["video_id"] and parsed.get("video_id"):
                result["video_id"] = parsed["video_id"]
            if not result["username"] and parsed.get("username"):
                result["username"] = parsed["username"]
            video_id = result["video_id"]
            if not video_id:
                raise Exception("Tidak bisa extract video_id")
            print(Fore.GREEN + f"✅ Video ID: {video_id}")

            # Caption
            caption = self._extract_caption_multi_strategy()
            if caption:
                result["description"] = caption
                # Analisis sentiment caption
                cap_analysis = self.sentiment.analyze_sentiment(caption)
                cap_cat = self.sentiment.categorize_comment(caption)
                result["caption_sentiment"] = {
                    "text": caption, "sentiment": cap_analysis["sentiment"],
                    "category": cap_cat, "language": cap_analysis["language"],
                    "is_hate_speech": cap_analysis["is_hate_speech"],
                    "is_toxic": cap_analysis["is_toxic"],
                }

            # Engagement
            print(Fore.CYAN + "\n📈 Engagement Metrics:")
            print(Fore.CYAN + f"   ▶️  Views : {result['play_count']:,}")
            print(Fore.CYAN + f"   ❤️  Likes : {result['digg_count']:,}")
            print(Fore.CYAN + f"   💬 Comments : {result['comment_count']:,}")

            # Scrape comments
            raw_comments = self._fetch_via_cdp(video_id, max_comments)
            method = "cdp"
            if not raw_comments:
                print(Fore.YELLOW + "   ℹ️  CDP gagal, fallback DOM...")
                if self._trigger_comment_panel():
                    raw_comments = self._fetch_via_dom(max_comments)
                    method = "dom"
                else:
                    print(Fore.YELLOW + "   ℹ️  Comment panel tidak bisa di-trigger")
            result["method"] = method

            unique = self._dedup_comments(raw_comments)
            print(Fore.GREEN + f"✅ Berhasil: {len(unique)} komentar")

            # Sentiment
            final_comments = []
            for i, rc in enumerate(unique, 1):
                text = rc.get("text", "")
                if not text:
                    continue
                analysis = self.sentiment.analyze_sentiment(text)
                category = self.sentiment.categorize_comment(text)
                final_comments.append({
                    "number": i, "username": rc["username"], "nickname": rc.get("nickname",""),
                    "text": text, "comment_id": rc.get("comment_id",""),
                    "like_count": rc.get("like_count",0), "created_at": rc.get("created_at",0),
                    "reply_count": rc.get("reply_count",0), "category": category,
                    "sentiment": analysis["sentiment"], "language": analysis["language"],
                    "is_hate_speech": analysis["is_hate_speech"], "is_toxic": analysis["is_toxic"],
                    "is_sarcasm": analysis.get("is_sarcasm",False),
                    "is_wellwish": analysis.get("is_wellwish",False),
                    "hate_score": analysis["hate_score"], "hate_words": analysis["hate_words"],
                    "toxic_words": analysis["toxic_words"], "positive_words": analysis["positive_words"],
                    "negative_words": analysis.get("negative_words",[]),
                    "humor_words": analysis["humor_words"], "emojis": analysis["emojis"],
                    "ml_confidence": analysis.get("ml_confidence",0),
                    "decision_source": analysis.get("decision_source","rule"),
                })
            result["comments"] = final_comments
            result["comments_count"] = len(final_comments)
            result["sentiment_summary"] = self._summarize(final_comments, result)

            # Active commenters
            result["active_commenters"] = self._build_active_commenters(final_comments)
            result["active_commenters_count"] = len(result["active_commenters"])

            # Top 5 liked comments
            allc = final_comments[:]
            sorted_likes = sorted(allc, key=lambda x: x.get("like_count",0), reverse=True)
            top5 = []
            for rank, c in enumerate(sorted_likes[:5], 1):
                top5.append({
                    "rank": rank, "username": c["username"], "text": c["text"][:150],
                    "like_count": c["like_count"], "category": c["category"],
                    "sentiment": c["sentiment"]
                })
            result["top_5_liked_comments"] = top5

        except Exception as e:
            print(Fore.RED + f"\n❌ GAGAL: {e}")
            import traceback
            traceback.print_exc()
            result["error"] = str(e)

        self._last_scrape_time = time.time()
        self._scrape_count += 1
        return result

    # ── UNIFIED SCRAPE (panggil scrape_post_comments lalu tambah likers) ──
    def scrape_post_unified(self, post_url: str, max_comments: int = 100,
                            include_replies: bool = True, max_replies_per_comment: int = 20,
                            scrape_likers: bool = True, max_likers: int = 500) -> Dict:
        result = self.scrape_post_comments(post_url, max_comments, include_replies, max_replies_per_comment)
        if not result.get("video_id"):
            result["error"] = "Tidak dapat mengambil video_id"
            return result
        if scrape_likers:
            print(Fore.CYAN + "\n👍 Scraping likers...")
            likers = self._fetch_likers_via_cdp(result["video_id"], max_likers)
            result["likers"] = likers
            result["likers_count"] = len(likers)
            result["likers_method"] = "cdp"
        else:
            result["likers"] = []
            result["likers_count"] = 0
        return result

    # ── SUMMARY ─────────────────────────────────────────────────
    def _summarize(self, comments: List[Dict], post_data: Dict = None) -> Dict:
        if not comments:
            return {"total_comments": 0}
        total = len(comments)
        counts = {k:0 for k in ("HATE_SPEECH","TOXIC","POSITIVE","NEGATIVE","NEUTRAL","HUMOR")}
        for c in comments:
            cat = c.get("category","NEUTRAL")
            if cat in counts:
                counts[cat] += 1
        def pct(n): return round(n/total*100,1)
        return {
            "total_comments": total,
            "hate_speech_count": counts["HATE_SPEECH"], "hate_percentage": pct(counts["HATE_SPEECH"]),
            "toxic_count": counts["TOXIC"], "toxic_percentage": pct(counts["TOXIC"]),
            "positive_count": counts["POSITIVE"], "positive_percentage": pct(counts["POSITIVE"]),
            "negative_count": counts["NEGATIVE"], "negative_percentage": pct(counts["NEGATIVE"]),
            "neutral_count": counts["NEUTRAL"], "neutral_percentage": pct(counts["NEUTRAL"]),
            "humor_count": counts["HUMOR"], "humor_percentage": pct(counts["HUMOR"]),
        }

    def save(self, data: Dict, filename: str) -> str:
        fp = os.path.join(OUTPUT_DIR, filename)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(Fore.GREEN + f"\n💾 Tersimpan: {fp}")
        return fp

    def run(self):
        print(Fore.CYAN + "\n" + "=" * 70)
        print(Fore.CYAN + "  TIKTOK SCRAPER V5.8 — ANTI-CAPTCHA")
        print(Fore.CYAN + "=" * 70)
        while True:
            print(Fore.CYAN + "\n📋 MENU")
            print("  1. Scrape Single Video (comments only)")
            print("  2. Scrape Single Video (unified + likers)")
            print("  3. Exit")
            choice = input(Fore.WHITE + "\nPilih [1-3]: ").strip()
            if choice == "1":
                url = input("\n🔗 URL: ").strip()
                if not url: continue
                max_c = int(input(f"Max komentar [{MAX_COMMENTS}]: ").strip() or MAX_COMMENTS)
                result = self.scrape_post_comments(url, max_c)
                self.save(result, f"tiktok_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            elif choice == "2":
                url = input("\n🔗 URL: ").strip()
                if not url: continue
                max_c = int(input(f"Max komentar [{MAX_COMMENTS}]: ").strip() or MAX_COMMENTS)
                max_l = int(input(f"Max likers [500]: ").strip() or 500)
                result = self.scrape_post_unified(url, max_c, scrape_likers=True, max_likers=max_l)
                self.save(result, f"tiktok_unified_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            elif choice == "3":
                break

if __name__ == "__main__":
    with TikTokScraperV58() as scraper:
        scraper.run()