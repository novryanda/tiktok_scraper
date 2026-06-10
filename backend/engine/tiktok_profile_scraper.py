# ============================================================
# TIKTOK PROFILE SCRAPER V2.1 — ANTI-CAPTCHA (NO-NAV FIRST)
# ============================================================
# Changelog v2.1 (dari V2.0):
#   ✅ STRATEGY UTAMA: ambil data profil TANPA buka halaman profil
#        → fetch() HTML SSR via XHR dari homepage → parse __UNIVERSAL_DATA__
#        → ini menghilangkan CAPTCHA yang dipicu navigasi ke /@username
#   ✅ Fallback API /api/user/detail/ (juga tanpa navigasi)
#   ✅ Baru buka halaman profil HANYA jika no-nav gagal ATAU butuh lists
#   ✅ Port _detect_captcha() + _wait_for_captcha_solve() dari V58
#        → CAPTCHA bisa diselesaikan manual (butuh TIKTOK_HEADLESS=False)
#   ✅ Resource blocking captcha-safe (gambar puzzle CAPTCHA TIDAK diblok)
#   ✅ Browser fingerprint disamakan dgn post scraper V58 yang sudah aman
#        (cookie mode TANPA channel="chrome", stealth lebih kaya)
#   ✅ scrape_lists OPSIONAL (env TIKTOK_SCRAPE_LISTS, default False)
#        → growth tracking tidak perlu buka modal followers (sumber CAPTCHA)
#   ✅ close() tetap ada (fix V2.0)
# ============================================================

import os
import re
import json
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from urllib.parse import quote

from dotenv import load_dotenv
from colorama import Fore, init
from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeout

from tiktok_cookie_injector import inject_cookies_sync, has_valid_session
from tiktok_warmup import TikTokWarmupMixin  # ← WAJIB: warmup mixin

init(autoreset=True)
load_dotenv()

# ── CONFIG ────────────────────────────────────────────────────
HEADLESS               = os.getenv("TIKTOK_HEADLESS", "False").lower() == "true"
PROXY                  = os.getenv("TIKTOK_PROXY", "")
DELAY_BETWEEN_PROFILES = int(os.getenv("TIKTOK_DELAY_BETWEEN_PROFILES", 10))
DEBUG_MODE             = os.getenv("TIKTOK_DEBUG", "False").lower() == "true"
DEBUG_HTML             = os.getenv("TIKTOK_DEBUG_HTML", "False").lower() == "true"
MAX_FOLLOWERS          = int(os.getenv("TIKTOK_MAX_FOLLOWERS", "200"))
MAX_FOLLOWING          = int(os.getenv("TIKTOK_MAX_FOLLOWING", "200"))
# ── CHANGED: lists default OFF (sumber utama CAPTCHA pada profil) ──
SCRAPE_LISTS_DEFAULT   = os.getenv("TIKTOK_SCRAPE_LISTS", "False").lower() == "true"
CAPTCHA_TIMEOUT        = int(os.getenv("TIKTOK_CAPTCHA_TIMEOUT", "180"))

_FILE_DIR             = os.path.dirname(os.path.abspath(__file__))
TIKTOK_CHROME_PROFILE = os.path.join(_FILE_DIR, "tiktok_chrome_real_profile")
OUTPUT_DIR            = os.path.join(_FILE_DIR, "output_tiktok_profiles")
TRACKING_FILE         = os.path.join(OUTPUT_DIR, "growth_tracking.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def debug_print(msg: str):
    if DEBUG_MODE:
        print(Fore.MAGENTA + f"   🔍 [DEBUG] {msg}")


class TikTokProfileScraper(TikTokWarmupMixin):

    def __init__(self):
        print(Fore.CYAN + "\n🎭 Initializing TikTok Profile Scraper V2.1 (Anti-CAPTCHA No-Nav)...")

        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

        self._last_scrape_time: float = 0.0
        self._min_gap_seconds: int = 30
        self._block_images_enabled: bool = False   # default: jangan blok gambar (biar CAPTCHA bisa dirender)

        # buffer untuk response interception
        self._captured_list_responses: list = []

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

        print(Fore.GREEN + "✅ TikTok Profile Scraper V2.1 siap")

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def close(self):
        try:
            if self.context:
                self.context.close()
                self.context = None
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
        except Exception:
            pass

    # ── BROWSER SETUP (disamakan dengan post scraper V58 yang aman) ──────────

    def _build_context(self):
        self.playwright = sync_playwright().start()

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

        if os.getenv("CHROME_NO_SANDBOX", "False").lower() == "true":
            args += ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]

        if PROXY:
            args.append(f"--proxy-server={PROXY}")

        # ── CHANGED: stealth diperkaya, identik dengan V58 ──
        stealth_script = """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {name: 'PDF Viewer', filename: 'internal-pdf-viewer'},
                    {name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer'},
                    {name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer'},
                ]
            });
            window.chrome = {
                runtime: {},
                csi: function() { return {}; },
                loadTimes: function() {
                    return {
                        requestTime: Date.now()/1000 - 1,
                        startLoadTime: Date.now()/1000 - 1,
                        commitLoadTime: Date.now()/1000 - 0.9,
                        finishDocumentLoadTime: Date.now()/1000 - 0.5,
                        finishLoadTime: Date.now()/1000 - 0.3,
                        firstPaintTime: Date.now()/1000 - 0.4,
                    };
                },
            };
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
            try {
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications'
                        ? Promise.resolve({state: Notification.permission})
                        : originalQuery(parameters)
                );
            } catch(e) {}
            try {
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';
                    if (parameter === 37446) return 'Intel(R) Iris(R) Xe Graphics';
                    return getParameter.call(this, parameter);
                };
            } catch(e) {}
            if (!navigator.connection) {
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({downlink: 10, effectiveType: '4g', rtt: 50, saveData: false})
                });
            }
        """

        common_kwargs = dict(
            headless=HEADLESS,
            slow_mo=random.randint(120, 280),
            args=args,
            no_viewport=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            ),
            locale="id-ID",
            timezone_id="Asia/Jakarta",
            bypass_csp=True,
            java_script_enabled=True,
        )

        if self._use_cookie_mode:
            # ── CHANGED: TANPA channel="chrome" → identik dengan V58 cookie mode
            # (UA dipaksa Chrome 148 + real Chrome = mismatch sec-ch-ua → mudah terdeteksi)
            persistent_profile = os.path.join(_FILE_DIR, "tiktok_cookie_profile_persistent")
            os.makedirs(persistent_profile, exist_ok=True)
            print(Fore.CYAN + f"   🍪 Cookie mode: persistent profile → {os.path.basename(persistent_profile)}")
            context = self.playwright.chromium.launch_persistent_context(
                persistent_profile, **common_kwargs
            )
        else:
            context = self.playwright.chromium.launch_persistent_context(
                TIKTOK_CHROME_PROFILE, channel="chrome", **common_kwargs
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
            for sel in [
                "[data-e2e='top-login-button']",
                "button:has-text('Log in')",
                "button:has-text('Log masuk')",
            ]:
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

    def _close_popups(self):
        for selector in [
            "div[role='dialog'] button:has-text('Not now')",
            "div[role='dialog'] button:has-text('Decline')",
            "div[role='dialog'] button:has-text('Close')",
            "div[role='dialog'] button:has-text('Cancel')",
            "button[aria-label='Close']",
        ]:
            try:
                if self.page.locator(selector).count() > 0:
                    self.page.locator(selector).first.click(timeout=2000)
                    time.sleep(0.8)
            except:
                pass

    def _enforce_rate_limit(self):
        if self._last_scrape_time <= 0:
            return
        elapsed = time.time() - self._last_scrape_time
        if elapsed < self._min_gap_seconds:
            wait = self._min_gap_seconds - elapsed
            print(Fore.YELLOW + f"\n⏱️  Rate-limit guard: tunggu {wait:.0f}s sebelum scrape berikutnya...")
            time.sleep(wait)

    # ════════════════════════════════════════════════════════════
    # CAPTCHA DETECTION + MANUAL SOLVE (port dari V58)
    # ════════════════════════════════════════════════════════════

    def _detect_captcha(self) -> bool:
        try:
            result = self.page.evaluate("""() => {
                const captchaSelectors = [
                    '[id*="captcha"]','[class*="captcha"]','[id*="verify"]',
                    '.tt-verify','#captcha-verify-container','#captcha_container',
                    '[class*="secsdk-captcha"]','[class*="cap-flex"]',
                    'div[role="dialog"] img[src*="captcha"]',
                ];
                const bodyText = document.body ? document.body.innerText : '';
                const textTriggers = [
                    'Tarik penggeser','sesuai dengan puzzle','Drag the slider',
                    'fit the puzzle','Geser untuk','Verifikasi','verification required',
                    'Memverifikasi','Verifying',
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

    def _wait_for_captcha_solve(self, timeout_seconds: int = CAPTCHA_TIMEOUT) -> bool:
        # Pastikan gambar tidak diblok agar puzzle CAPTCHA bisa dirender & di-solve
        prev_blocking = self._block_images_enabled
        self._block_images_enabled = False

        print(Fore.RED + "\n" + "=" * 70)
        print(Fore.RED + "🛑 CAPTCHA TERDETEKSI!")
        if HEADLESS:
            print(Fore.RED + "⚠️  Mode HEADLESS aktif → tidak bisa diselesaikan manual.")
            self._block_images_enabled = prev_blocking
            return False
        print(Fore.YELLOW + f"Selesaikan CAPTCHA di jendela browser. Waktu: {timeout_seconds} detik.\n")

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
                print(Fore.YELLOW + f"   ⏳ Masih menunggu CAPTCHA... ({remaining}s tersisa)")
                last_check = time.time()
            time.sleep(2)

        print(Fore.RED + "\n❌ Timeout CAPTCHA.")
        self._block_images_enabled = prev_blocking
        return False

    # ════════════════════════════════════════════════════════════
    # BROWSER INIT
    # ════════════════════════════════════════════════════════════

    def initialize_browser(self):
        if self.context:
            return

        print(Fore.CYAN + "\n🌐 Membuka browser TikTok (stealth)...")
        self.context = self._build_context()
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self._block_images_enabled = False

        # ── CHANGED: resource blocking captcha-safe (port dari V58) ──
        captcha_safe_patterns = [
            "captcha", "verify", "secsdk", "tiktokcdn-us.com", "/aweme/",
            "rmsec", "tiktokv.com/captcha", "byteoversea.com", "/captcha-sdk",
            "favicon", "/icon",
        ]

        def block_heavy_resources(route):
            try:
                resource_type = route.request.resource_type
                url = route.request.url.lower()
                # JANGAN pernah blok resource CAPTCHA/verify
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
                if resource_type in ("image", "media"):
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
        time.sleep(random.uniform(3, 5))
        self._close_popups()

        if "login" in self.page.url:
            self.close()
            raise RuntimeError(
                "Redirect ke login page — session expired. "
                "Perbarui cookies di tt_session.json."
            )

        if not self._is_logged_in():
            self.close()
            raise RuntimeError(
                "Browser terbuka tapi belum login ke TikTok. "
                "Perbarui cookies di tt_session.json."
            )

        print(Fore.GREEN + "✅ Browser TikTok siap (LOGGED IN ✓)")

        # Warmup natural di FYP — bikin sesi terlihat seperti manusia
        print(Fore.YELLOW + "\n🔥 Warmup natural...")
        try:
            self.warmup_natural(label="profile-init")
        except Exception as e:
            debug_print(f"warmup_natural error (diabaikan): {e}")

    # ── URL PARSER ──────────────────────────────────────────────

    @staticmethod
    def _parse_url_to_username(raw_input: str) -> str:
        raw = raw_input.strip()
        if "tiktok.com" in raw.lower():
            match = re.search(r'tiktok\.com/@([^/?&#\s]+)', raw, re.IGNORECASE)
            if match:
                extracted = match.group(1)
                print(Fore.CYAN + f"   🔗 URL terdeteksi → username: @{extracted}")
                return extracted
            else:
                raise ValueError(f"Tidak bisa parse username dari URL: {raw}")
        return raw

    @staticmethod
    def _sanitize_username(username: str) -> str:
        username = username.strip().lstrip('@').replace(' ', '').replace('\t', '')
        username = username.lower()
        username = re.sub(r'[^a-z0-9_.]', '', username)
        username = re.sub(r'\.{2,}', '.', username)
        username = username.strip('.')
        if not username:
            raise ValueError("Username tidak valid setelah sanitasi")
        return username

    def _resolve_username(self, raw_input: str) -> str:
        raw = self._parse_url_to_username(raw_input)
        return self._sanitize_username(raw)

    # ── NUMBER PARSER ────────────────────────────────────────────

    def _parse_number(self, text: str) -> int:
        if not text:
            return 0
        text = str(text).strip().upper().replace(',', '').replace('.', '')
        for suffix, multiplier in {'K': 1000, 'M': 1000000, 'B': 1000000000}.items():
            if suffix in text:
                try:
                    return int(float(text.replace(suffix, '')) * multiplier)
                except:
                    pass
        try:
            return int(text)
        except:
            return 0

    # ════════════════════════════════════════════════════════════
    # STRATEGY NO-NAV (UTAMA) — ambil profil TANPA buka halaman profil
    # ════════════════════════════════════════════════════════════

    def _blank_profile(self, username: str) -> Dict:
        return {
            "username": username, "display_name": "", "bio": "", "avatar_url": "",
            "followers": 0, "following": 0, "total_likes": 0, "total_videos": 0,
            "is_verified": False, "is_private": False, "you_follow": False,
            "follows_you": False, "is_mutual": False,
            "sec_uid": "", "user_id": "",
            "followers_list": [], "following_list": [], "mutual_followers_list": [],
            "method": "",
        }

    @staticmethod
    def _map_userinfo(ui: Dict) -> Optional[Dict]:
        """Map blok userInfo (user + stats) ke struktur profil kita."""
        if not ui:
            return None
        user = ui.get("user", {}) or {}
        stats = ui.get("stats", {}) or ui.get("statsV2", {}) or {}
        if not user.get("uniqueId") and not stats:
            return None

        def _i(v):
            try:
                return int(v or 0)
            except (TypeError, ValueError):
                return 0

        return {
            "display_name": user.get("nickname", "") or "",
            "bio": user.get("signature", "") or "",
            "avatar_url": user.get("avatarLarger", "") or user.get("avatarMedium", "") or "",
            "followers": _i(stats.get("followerCount")),
            "following": _i(stats.get("followingCount")),
            "total_likes": _i(stats.get("heartCount") or stats.get("heart")),
            "total_videos": _i(stats.get("videoCount")),
            "is_verified": bool(user.get("verified", False)),
            "is_private": bool(user.get("privateAccount", False) or user.get("secret", False)),
            "sec_uid": user.get("secUid", "") or "",
            "user_id": user.get("id", "") or "",
        }

    def _fetch_profile_via_xhr_html(self, username: str) -> Optional[Dict]:
        """
        STRATEGI ANTI-CAPTCHA UTAMA.
        Ambil HTML SSR halaman profil via fetch() (XHR) — TANPA page.goto().
        Lalu parse __UNIVERSAL_DATA_FOR_REHYDRATION__ pakai DOMParser.
        Karena tidak ada navigasi, CAPTCHA navigasi tidak terpicu.
        """
        try:
            result = self.page.evaluate("""async (uname) => {
                try {
                    const url = 'https://www.tiktok.com/@' + uname + '?lang=id-ID';
                    const resp = await fetch(url, {
                        credentials: 'include',
                        headers: {
                            'Accept': 'text/html,application/xhtml+xml',
                            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8'
                        }
                    });
                    const html = await resp.text();
                    const isCaptcha = /captcha|verify|secsdk|Tarik penggeser/i.test(html);
                    let doc;
                    try { doc = new DOMParser().parseFromString(html, 'text/html'); }
                    catch(e) { return {found:false, captcha:isCaptcha}; }
                    const el = doc.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                    if (!el) return {found:false, captcha:isCaptcha};
                    let data;
                    try { data = JSON.parse(el.textContent); }
                    catch(e) { return {found:false, captcha:isCaptcha}; }
                    const scope = (data && data.__DEFAULT_SCOPE__) || {};
                    let ui = null;
                    for (const k of ['webapp.user-detail','webapp.user-profile','UserPage']) {
                        const part = scope[k] || data[k];
                        if (part && part.userInfo) { ui = part.userInfo; break; }
                    }
                    if (!ui) return {found:false, captcha:isCaptcha};
                    return {found:true, userInfo: ui};
                } catch(e) {
                    return {found:false, error: e.toString()};
                }
            }""", username)

            if not result:
                return None
            if result.get("captcha"):
                debug_print("XHR-HTML: response berisi captcha/verify")
            if not result.get("found"):
                return None

            mapped = self._map_userinfo(result.get("userInfo"))
            if mapped:
                mapped["method"] = "xhr_html"
                return mapped
        except Exception as e:
            debug_print(f"XHR-HTML error: {e}")
        return None

    def _fetch_profile_via_api(self, username: str) -> Optional[Dict]:
        """
        Fallback no-nav: API /api/user/detail/ via fetch() dari homepage.
        """
        endpoints = [
            f"/api/user/detail/?uniqueId={quote(username)}&aid=1988&app_name=tiktok_web&device_platform=web_pc",
            f"/api/user/detail/?uniqueId={quote(username)}&aid=1988",
        ]
        for ep in endpoints:
            try:
                result = self.page.evaluate("""async (url) => {
                    try {
                        const resp = await fetch(url, {
                            method: 'GET',
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8',
                                'Referer': 'https://www.tiktok.com/'
                            }
                        });
                        const text = await resp.text();
                        try { return {status: resp.status, data: JSON.parse(text)}; }
                        catch(e) { return {status: resp.status, data: null}; }
                    } catch(e) {
                        return {status: 0, error: e.toString()};
                    }
                }""", ep)

                if not result:
                    continue
                data = result.get("data")
                if not data:
                    continue
                mapped = self._map_userinfo(data.get("userInfo"))
                if mapped:
                    mapped["method"] = "api_user_detail"
                    return mapped
            except Exception as e:
                debug_print(f"API user detail error ({ep}): {e}")
        return None

    # ════════════════════════════════════════════════════════════
    # STRATEGY 2/3: DOM / Metadata (dipakai kalau no-nav gagal & sudah di profil)
    # ════════════════════════════════════════════════════════════

    def _extract_stats_from_html(self) -> Dict:
        html = self.page.content()
        stats = {"followers": 0, "following": 0, "likes": 0}
        for pat, key in [
            (r'(\d+(?:[.,]\d+)?[KMB]?)\s*[Ff]ollowers?', "followers"),
            (r'(\d+(?:[.,]\d+)?[KMB]?)\s*[Ff]ollowing', "following"),
            (r'(\d+(?:[.,]\d+)?[KMB]?)\s*[Ll]ikes', "likes"),
        ]:
            m = re.search(pat, html)
            if m:
                stats[key] = self._parse_number(m.group(1))
        for key, sel in [
            ("followers", "[data-e2e='followers-count']"),
            ("following", "[data-e2e='following-count']"),
            ("likes", "[data-e2e='likes-count']"),
        ]:
            if stats[key] == 0:
                try:
                    el = self.page.locator(sel)
                    if el.count():
                        title = el.first.get_attribute("title")
                        if title:
                            stats[key] = self._parse_number(title)
                except:
                    pass
        for pat, key in [
            (r'"followerCount":\s*(\d+)', "followers"),
            (r'"followingCount":\s*(\d+)', "following"),
            (r'"heartCount":\s*(\d+)', "likes"),
        ]:
            m = re.search(pat, html)
            if m:
                stats[key] = int(m.group(1))
        return stats

    def _extract_from_metadata(self) -> Optional[Dict]:
        try:
            ui = self.page.evaluate("""() => {
                const script = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                if (!script) return null;
                const data = JSON.parse(script.textContent);
                const scope = data.__DEFAULT_SCOPE__ || {};
                for (const key of ['webapp.user-detail', 'webapp.user-profile', 'UserPage']) {
                    const part = scope[key] || data[key];
                    if (part?.userInfo) return part.userInfo;
                }
                return null;
            }""")
            return self._map_userinfo(ui) if ui else None
        except Exception as e:
            debug_print(f"Metadata extraction error: {e}")
            return None

    def _get_friendship_status(self) -> Dict:
        default = {"is_private": False, "you_follow": False, "follows_you": False, "is_mutual": False, "follow_status_raw": None, "ftc_raw": None}
        try:
            status = self.page.evaluate("""() => {
                const script = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                if (!script) return null;
                const data = JSON.parse(script.textContent);
                const scope = data.__DEFAULT_SCOPE__ || {};
                let user = null;
                for (const key of ['webapp.user-detail', 'webapp.user-profile', 'UserPage']) {
                    const part = scope[key] || data[key];
                    if (part?.userInfo) { user = part.userInfo.user; break; }
                    if (part?.user) { user = part.user; break; }
                }
                if (!user) return null;
                return { followStatus: user.followStatus ?? 0, ftc: user.ftc ?? 0, secret: user.secret ?? false };
            }""")
            if not status:
                return default
            fs = status.get("followStatus", 0)
            ftc = status.get("ftc", 0)
            you_follow = fs == 1
            follows_you = ftc == 1
            return {
                "is_private": bool(status.get("secret", False)),
                "you_follow": you_follow,
                "follows_you": follows_you,
                "is_mutual": you_follow and follows_you,
                "follow_status_raw": fs,
                "ftc_raw": ftc,
            }
        except Exception as e:
            debug_print(f"Friendship status error: {e}")
            return default

    def _get_ids_from_metadata(self) -> Dict[str, Optional[str]]:
        try:
            ids = self.page.evaluate("""() => {
                const script = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                if (!script) return null;
                const data = JSON.parse(script.textContent);
                const scope = data.__DEFAULT_SCOPE__ || {};
                let user = null;
                for (const key of ['webapp.user-detail', 'webapp.user-profile', 'UserPage']) {
                    const part = scope[key] || data[key];
                    if (part?.userInfo) { user = part.userInfo.user; break; }
                    if (part?.user) { user = part.user; break; }
                }
                if (!user) return null;
                return { id: user.id || null, secUid: user.secUid || null };
            }""")
            if not ids:
                return {"id": None, "secUid": None}
            return {"id": ids.get("id"), "secUid": ids.get("secUid")}
        except Exception as e:
            debug_print(f"Gagal ambil ids: {e}")
            return {"id": None, "secUid": None}

    # ════════════════════════════════════════════════════════════
    # NAVIGASI KE PROFIL (hanya kalau no-nav gagal atau butuh lists)
    # ════════════════════════════════════════════════════════════

    def _navigate_to_profile(self, username: str):
        """Buka halaman profil + tangani CAPTCHA (solve manual jika non-headless)."""
        target = f"/@{username}"
        if target in (self.page.url or ""):
            return  # sudah di halaman profil

        profile_url = f"https://www.tiktok.com/@{username}"
        try:
            self.pre_nav_pause(label="profile-goto")
        except Exception:
            time.sleep(random.uniform(2.0, 4.0))

        print(Fore.YELLOW + f"\n🌍 Navigasi ke: {profile_url}")
        for attempt in range(2):
            try:
                self.page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
                break
            except Exception:
                time.sleep(8)

        time.sleep(random.uniform(3.5, 6.5))
        self._close_popups()

        if DEBUG_HTML:
            try:
                with open("debug_profile.html", "w", encoding="utf-8") as f:
                    f.write(self.page.content())
                print(Fore.CYAN + "   💾 debug_profile.html disimpan")
            except Exception:
                pass

        # ── CHANGED: tangani CAPTCHA dengan solver, bukan langsung raise ──
        if self._detect_captcha():
            print(Fore.RED + "   🛑 CAPTCHA terdeteksi saat buka halaman profil!")
            if not self._wait_for_captcha_solve():
                raise RuntimeError(
                    "CAPTCHA pada halaman profil tidak teratasi. "
                    "Jalankan dengan TIKTOK_HEADLESS=False untuk solve manual, "
                    "atau perbarui cookies di Settings → upload tt_session.json baru."
                )

        self._wait_for_profile_ready()

    # ════════════════════════════════════════════════════════════
    # FOLLOWERS / FOLLOWING via RESPONSE INTERCEPTION
    # ════════════════════════════════════════════════════════════

    def _ensure_on_profile(self, username: str):
        self._navigate_to_profile(username)

    def _list_is_private(self) -> bool:
        try:
            content = self.page.content().lower()
            return any(p in content for p in [
                "following list is private",
                "this user's following list is private",
                "this account's following list is private",
                "daftar yang diikuti bersifat pribadi",
                "follower list is private",
            ])
        except Exception:
            return False

    def _open_list_modal(self, kind: str) -> bool:
        selectors = (
            ["[data-e2e='followers']", "strong[data-e2e='followers-count']", "[data-e2e='followers-count']"]
            if kind == "followers" else
            ["[data-e2e='following']", "strong[data-e2e='following-count']", "[data-e2e='following-count']"]
        )
        for sel in selectors:
            try:
                loc = self.page.locator(sel)
                if loc.count() == 0:
                    continue
                loc.first.click(timeout=4000)
                try:
                    self.page.wait_for_selector("div[role='dialog'], [data-e2e='follow-info-popup']", timeout=6000)
                    time.sleep(1.5)
                    return True
                except PlaywrightTimeout:
                    debug_print(f"Modal {kind} tidak muncul setelah klik {sel}")
            except Exception as e:
                debug_print(f"Klik {sel} gagal: {e}")
        return False

    def _drain_captured_responses(self, collected: Dict[str, bool]):
        while self._captured_list_responses:
            resp = self._captured_list_responses.pop(0)
            try:
                data = resp.json()
            except Exception:
                continue
            user_list = data.get("userList") or data.get("userInfoList") or []
            if not isinstance(user_list, list):
                continue
            for u in user_list:
                info = u.get("user") or u.get("userInfo") or {}
                uid = info.get("uniqueId")
                if uid:
                    collected[uid] = True

    def _scrape_list_via_ui(self, kind: str, max_count: int) -> List[str]:
        collected: Dict[str, bool] = {}
        self._captured_list_responses = []

        def handle_response(response):
            try:
                if "/api/user/list/" in response.url and response.status == 200:
                    self._captured_list_responses.append(response)
            except Exception:
                pass

        self.page.on("response", handle_response)
        try:
            if not self._open_list_modal(kind):
                print(Fore.YELLOW + f"   ⚠️  Tidak bisa membuka modal {kind}")
                return []
            if self._list_is_private():
                print(Fore.YELLOW + f"   🔒 Daftar {kind} bersifat PRIVAT")
                return []

            scroll_js = """
                () => {
                    const dialog = document.querySelector("div[role='dialog'], [data-e2e='follow-info-popup']");
                    if (!dialog) return false;
                    let target = null;
                    const divs = dialog.querySelectorAll('div');
                    for (const el of divs) {
                        if (el.scrollHeight > el.clientHeight + 20) { target = el; break; }
                    }
                    target = target || dialog;
                    target.scrollTop = target.scrollHeight;
                    return true;
                }
            """
            self._drain_captured_responses(collected)
            stagnant = 0
            last_count = len(collected)

            for i in range(80):
                if len(collected) >= max_count:
                    break
                try:
                    ok = self.page.evaluate(scroll_js)
                except Exception as e:
                    debug_print(f"Scroll error: {e}")
                    break
                if not ok:
                    break
                time.sleep(random.uniform(1.3, 2.4))
                self._drain_captured_responses(collected)
                # cek CAPTCHA di tengah scroll
                if self._detect_captcha():
                    if not self._wait_for_captcha_solve():
                        break
                if len(collected) == last_count:
                    stagnant += 1
                    if stagnant >= 5:
                        debug_print(f"{kind}: tidak ada user baru setelah {stagnant}x scroll, stop.")
                        break
                else:
                    stagnant = 0
                last_count = len(collected)
                debug_print(f"{kind} scroll {i+1}: terkumpul {len(collected)}")

            self._drain_captured_responses(collected)
        finally:
            try:
                self.page.remove_listener("response", handle_response)
            except Exception:
                pass
            try:
                self.page.keyboard.press("Escape")
                time.sleep(0.6)
            except Exception:
                pass

        return list(collected.keys())[:max_count]

    def scrape_followers_and_following(self, username: str, max_followers: int = MAX_FOLLOWERS, max_following: int = MAX_FOLLOWING) -> Dict:
        print(Fore.CYAN + "\n👥 Memulai scraping followers & following (mode: UI interception)...")
        self._ensure_on_profile(username)

        ids = self._get_ids_from_metadata()
        if ids.get("id"):
            print(Fore.CYAN + f"   🆔 User ID: {ids['id']}  |  secUid: {(ids.get('secUid') or '')[:24]}...")

        print(Fore.CYAN + "   📜 Mengambil daftar followers...")
        followers = self._scrape_list_via_ui("followers", max_followers)
        print(Fore.GREEN + f"   ✅ Followers terkumpul: {len(followers)}")
        time.sleep(random.uniform(2.5, 4.5))

        print(Fore.CYAN + "   📜 Mengambil daftar following...")
        following = self._scrape_list_via_ui("following", max_following)
        print(Fore.GREEN + f"   ✅ Following terkumpul: {len(following)}")

        followers_set: Set[str] = set(followers)
        mutual = [u for u in following if u in followers_set]
        print(Fore.GREEN + f"   🤝 Mutual followers: {len(mutual)}")

        if not followers and not following:
            return {
                "followers": [], "following": [], "mutual_followers": [],
                "note": "Daftar kosong. Kemungkinan: daftar privat, akun terlalu besar, atau rate-limit/CAPTCHA.",
            }
        return {"followers": followers, "following": following, "mutual_followers": mutual}

    def _scrape_lists_into(self, profile: Dict, username: str):
        if profile.get("is_private"):
            debug_print("Profil privat — lewati scraping daftar")
            return
        lists = self.scrape_followers_and_following(username)
        if "error" not in lists:
            profile["followers_list"] = lists.get("followers", [])
            profile["following_list"] = lists.get("following", [])
            profile["mutual_followers_list"] = lists.get("mutual_followers", [])
            if lists.get("note"):
                profile["lists_note"] = lists["note"]

    # ════════════════════════════════════════════════════════════
    # EKSTRAKSI DATA dari halaman profil (fallback setelah navigasi)
    # ════════════════════════════════════════════════════════════

    def _extract_profile_data(self, username: str) -> Dict:
        print(Fore.CYAN + "   📊 Extracting profile data (on-page)...")
        profile = self._blank_profile(username)

        try:
            name_sel = self.page.locator("[data-e2e='user-title'], h1[data-e2e='user-title']")
            if name_sel.count():
                profile["display_name"] = name_sel.first.text_content().strip()
            bio_sel = self.page.locator("[data-e2e='user-bio'], h2[data-e2e='user-bio']")
            if bio_sel.count():
                profile["bio"] = bio_sel.first.text_content().strip()
            avatar_sel = self.page.locator("[data-e2e='user-avatar'] img, img[alt*='avatar']")
            if avatar_sel.count():
                profile["avatar_url"] = avatar_sel.first.get_attribute("src") or ""
        except Exception as e:
            debug_print(f"DOM basic extraction error: {e}")

        friendship = self._get_friendship_status()
        profile["is_private"] = friendship["is_private"]
        profile["you_follow"] = friendship["you_follow"]
        profile["follows_you"] = friendship["follows_you"]
        profile["is_mutual"] = friendship["is_mutual"]

        # Metadata JSON (paling lengkap di halaman)
        print(Fore.CYAN + "   📡 [On-page Strategy 1] Metadata JSON...")
        meta = self._extract_from_metadata()
        if meta:
            for k in ("display_name", "bio", "avatar_url", "followers", "following",
                      "total_likes", "total_videos", "is_verified", "is_private",
                      "sec_uid", "user_id"):
                if meta.get(k):
                    profile[k] = meta[k]
            profile["method"] = "metadata_json"
            if profile["followers"] > 0 or profile["display_name"]:
                print(Fore.GREEN + "   ✅ Berhasil via Metadata JSON")
                return profile

        # HTML regex fallback
        print(Fore.CYAN + "   📡 [On-page Strategy 2] HTML Regex...")
        stats = self._extract_stats_from_html()
        if stats["followers"] > 0:
            profile["followers"] = stats["followers"]
            profile["following"] = stats["following"]
            profile["total_likes"] = stats["likes"]
            video_match = re.search(r'(\d+(?:[.,]\d+)?[KMB]?)\s*[Vv]ideos?', self.page.content())
            if video_match:
                profile["total_videos"] = self._parse_number(video_match.group(1))
            profile["method"] = "html_regex"
            print(Fore.GREEN + "   ✅ Berhasil via HTML Regex")
            return profile

        profile["method"] = profile["method"] or "partial"
        return profile

    def _wait_for_profile_ready(self) -> bool:
        try:
            self.page.wait_for_selector("[data-e2e='user-title'], h1[data-e2e='user-title']", timeout=10000)
            time.sleep(2)
            return True
        except:
            try:
                self.page.evaluate("window.scrollBy(0, 300);")
                time.sleep(2)
                self.page.wait_for_selector("[data-e2e='user-title']", timeout=5000)
                return True
            except:
                return False

    # ════════════════════════════════════════════════════════════
    # MAIN SCRAPE — API/XHR-first, navigasi hanya sebagai fallback
    # ════════════════════════════════════════════════════════════

    def scrape_profile(self, username_or_url: str, scrape_lists: Optional[bool] = None) -> Dict:
        if scrape_lists is None:
            scrape_lists = SCRAPE_LISTS_DEFAULT

        try:
            username = self._resolve_username(username_or_url)
        except ValueError as e:
            return {
                "success": False, "username": username_or_url,
                "scraped_at": datetime.now().isoformat(),
                "data": {}, "error": f"Username tidak valid: {e}",
            }

        print(Fore.CYAN + "\n" + "=" * 70)
        print(Fore.CYAN + f"👤 Scraping: @{username}  (lists={'ON' if scrape_lists else 'OFF'})")
        print(Fore.CYAN + "=" * 70)

        result = {
            "success": False, "username": username,
            "scraped_at": datetime.now().isoformat(),
            "data": {}, "error": None,
        }

        try:
            self.initialize_browser()      # homepage + warmup
            self._enforce_rate_limit()

            profile_data: Optional[Dict] = None

            # ── STRATEGY A: NO-NAV (XHR HTML → API) — tanpa CAPTCHA ──
            print(Fore.CYAN + "\n📡 [No-Nav] Coba ambil profil TANPA buka halaman profil...")
            api = self._fetch_profile_via_xhr_html(username) or self._fetch_profile_via_api(username)

            if api and (api.get("followers", 0) > 0 or api.get("display_name") or api.get("total_videos", 0) > 0):
                profile_data = self._blank_profile(username)
                profile_data.update(api)
                print(Fore.GREEN + f"   ✅ Data profil didapat via {profile_data['method']} (TANPA CAPTCHA)")

                # Buka halaman profil HANYA kalau butuh lists & akun tidak privat
                if scrape_lists and not profile_data.get("is_private"):
                    try:
                        self._navigate_to_profile(username)
                        self._scrape_lists_into(profile_data, username)
                    except Exception as e:
                        print(Fore.YELLOW + f"   ⚠️  Scraping lists gagal: {e}")
                        profile_data["lists_note"] = f"Lists gagal: {e}"

            # ── STRATEGY B: NO-NAV gagal → fallback buka halaman profil ──
            if not profile_data:
                print(Fore.YELLOW + "   ↩️  No-Nav kosong → fallback buka halaman profil...")
                self._navigate_to_profile(username)   # ada CAPTCHA solver di dalam

                for _ in range(3):
                    self.page.evaluate("window.scrollBy(0, 400);")
                    time.sleep(random.uniform(0.6, 1.2))

                profile_data = None
                for retry in range(3):
                    profile_data = self._extract_profile_data(username)
                    if profile_data["followers"] > 0 or profile_data["display_name"]:
                        break
                    print(Fore.YELLOW + f"   🔄 Retry {retry+1}/3 karena data kosong...")
                    time.sleep(2)
                    self.page.evaluate("window.scrollBy(0, 200);")

                if scrape_lists and profile_data and not profile_data.get("is_private"):
                    try:
                        self._scrape_lists_into(profile_data, username)
                    except Exception as e:
                        print(Fore.YELLOW + f"   ⚠️  Scraping lists gagal: {e}")

            if not profile_data or (profile_data["followers"] == 0 and not profile_data["display_name"]):
                raise Exception(
                    f"Tidak dapat mengekstrak data dari @{username}. "
                    "Kemungkinan akun tidak ada, session expired, atau kena CAPTCHA. "
                    "Set TIKTOK_DEBUG_HTML=true untuk inspeksi."
                )

            self._display_profile_box(profile_data)
            profile_data["scraped_at"] = result["scraped_at"]  # wajib untuk save_tracking_data
            result["success"] = True
            result["data"] = profile_data

        except Exception as e:
            print(Fore.RED + f"\n❌ GAGAL: {e}")
            result["error"] = str(e)

        self._last_scrape_time = time.time()
        return result

    # ── DISPLAY ─────────────────────────────────────────────────

    def _display_profile_box(self, data: Dict):
        box_width = 68
        print("\n" + Fore.CYAN + "┌" + "─" * box_width + "┐")
        print(Fore.CYAN + "│" + "  👤 PROFIL TIKTOK".center(box_width) + "│")
        print(Fore.CYAN + "├" + "─" * box_width + "┤")
        print(Fore.CYAN + "│  " + f"📡 Method: {data.get('method','unknown')}".ljust(box_width - 2) + "│")
        verified = " ✓" if data.get("is_verified") else ""
        print(Fore.CYAN + "│  " + f"@{data['username']}{verified}".ljust(box_width - 2) + "│")
        if data.get("display_name"):
            print(Fore.CYAN + "│  " + f"{data['display_name']}".ljust(box_width - 2) + "│")
        print(Fore.CYAN + "├" + "─" * box_width + "┤")
        print(Fore.CYAN + "│  " + f"👥 Followers  : {data['followers']:>15,}".ljust(box_width - 2) + "│")
        print(Fore.CYAN + "│  " + f"👤 Following  : {data['following']:>15,}".ljust(box_width - 2) + "│")
        print(Fore.CYAN + "│  " + f"❤️  Total Likes: {data['total_likes']:>15,}".ljust(box_width - 2) + "│")
        print(Fore.CYAN + "│  " + f"🎬 Videos     : {data['total_videos']:>15,}".ljust(box_width - 2) + "│")
        if data['followers'] > 0:
            eng = (data['total_likes'] / data['followers']) * 100
            print(Fore.CYAN + "│  " + f"📊 Engagement : {eng:>14.2f}%".ljust(box_width - 2) + "│")
        print(Fore.CYAN + "│  " + ("🤝 Mutual Follow: " + ("✅ YES" if data.get("is_mutual") else "❌ NO")).ljust(box_width - 2) + "│")
        print(Fore.CYAN + "│  " + ("🔒 Private: " + ("✅" if data.get("is_private") else "❌")).ljust(box_width - 2) + "│")
        fl = data.get("followers_list", [])
        fg = data.get("following_list", [])
        if fl or fg:
            print(Fore.CYAN + "├" + "─" * box_width + "┤")
            print(Fore.CYAN + "│  " + f"📜 Followers list : {len(fl)} | Following list : {len(fg)}".ljust(box_width - 2) + "│")
        mutual_list = data.get("mutual_followers_list", [])
        if mutual_list:
            print(Fore.CYAN + "├" + "─" * box_width + "┤")
            print(Fore.CYAN + "│  " + f"🤝 Mutual Followers ({len(mutual_list)}):".ljust(box_width - 2) + "│")
            for u in mutual_list[:10]:
                print(Fore.CYAN + "│    " + f"@{u}".ljust(box_width - 4) + "│")
            if len(mutual_list) > 10:
                print(Fore.CYAN + "│    " + f"... dan {len(mutual_list)-10} lainnya".ljust(box_width - 4) + "│")
        if data.get("bio"):
            print(Fore.CYAN + "├" + "─" * box_width + "┤")
            print(Fore.CYAN + "│  " + "📝 Bio:".ljust(box_width - 2) + "│")
            words = data["bio"].split()
            lines, cur = [], ""
            for w in words:
                if len(cur) + len(w) + 1 <= box_width - 6:
                    cur += (" " if cur else "") + w
                else:
                    if cur: lines.append(cur)
                    cur = w
            if cur: lines.append(cur)
            for line in lines[:5]:
                print(Fore.CYAN + "│  " + line.ljust(box_width - 2) + "│")
        print(Fore.CYAN + "└" + "─" * box_width + "┘")
        print(Fore.RESET)

    # ── TRACKING & ANALYTICS ─────────────────────────────────────

    def save_tracking_data(self, profile_data: Dict):
        username = profile_data.get("username", "")
        if not username:
            print(Fore.YELLOW + "   ⚠️  save_tracking_data: username kosong, skip")
            return
        scraped_at = profile_data.get("scraped_at") or datetime.now().isoformat()

        tracking_data = {}
        if os.path.exists(TRACKING_FILE):
            try:
                with open(TRACKING_FILE, "r", encoding="utf-8") as f:
                    tracking_data = json.load(f)
            except Exception:
                tracking_data = {}

        if username not in tracking_data:
            tracking_data[username] = {"username": username, "first_tracked": scraped_at, "history": []}

        tracking_data[username]["history"].append({
            "scraped_at": scraped_at,
            "followers":    profile_data.get("followers", 0),
            "following":    profile_data.get("following", 0),
            "total_likes":  profile_data.get("total_likes", 0),
            "total_videos": profile_data.get("total_videos", 0),
        })
        tracking_data[username]["last_tracked"] = scraped_at

        with open(TRACKING_FILE, "w", encoding="utf-8") as f:
            json.dump(tracking_data, f, ensure_ascii=False, indent=2)
        print(Fore.GREEN + f"\n💾 Tracking data updated: @{username} → {TRACKING_FILE}")

    def analyze_growth(self, username: str, days: int = 30) -> Dict:
        try:
            username = self._resolve_username(username)
        except ValueError:
            print(Fore.RED + "❌ Username tidak valid"); return {}
        if not os.path.exists(TRACKING_FILE):
            print(Fore.RED + "❌ Belum ada tracking data"); return {}
        with open(TRACKING_FILE, "r", encoding="utf-8") as f:
            tracking_data = json.load(f)
        if username not in tracking_data:
            print(Fore.RED + f"❌ Tidak ada tracking data untuk @{username}"); return {}
        history = tracking_data[username]["history"]
        if len(history) < 2:
            print(Fore.YELLOW + f"⚠️  Hanya ada {len(history)} data point"); return {}
        cutoff = datetime.now() - timedelta(days=days)
        fh = [h for h in history if datetime.fromisoformat(h["scraped_at"]) >= cutoff]
        if len(fh) < 2: fh = history
        fh.sort(key=lambda x: x["scraped_at"])
        first, last = fh[0], fh[-1]
        fd = datetime.fromisoformat(first["scraped_at"])
        ld = datetime.fromisoformat(last["scraped_at"])
        span = (ld - fd).days or 1
        def _growth(key):
            s, e = first[key], last[key]; g = e - s
            return {"start":s,"end":e,"growth":g,"growth_pct":round(g/s*100,2) if s>0 else 0,"avg_per_day":round(g/span,2)}
        return {
            "username": username, "analyzed_at": datetime.now().isoformat(),
            "period": {"start_date":fd.isoformat(),"end_date":ld.isoformat(),"days":span,"data_points":len(fh)},
            "followers":_growth("followers"),"following":_growth("following"),
            "likes":_growth("total_likes"),"videos":_growth("total_videos"),"history":fh,
        }

    def export_to_csv(self, username: str, output_file: str = None):
        try:
            username = self._resolve_username(username)
        except ValueError:
            print(Fore.RED + "❌ Username tidak valid"); return
        if not os.path.exists(TRACKING_FILE):
            print(Fore.RED + "❌ Belum ada tracking data"); return
        with open(TRACKING_FILE, "r", encoding="utf-8") as f:
            tracking_data = json.load(f)
        if username not in tracking_data:
            print(Fore.RED + f"❌ Tidak ada data untuk @{username}"); return
        if not output_file:
            output_file = os.path.join(OUTPUT_DIR, f"{username}_growth_history.csv")
        import csv
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date","Followers","Following","Total Likes","Videos"])
            for entry in tracking_data[username]["history"]:
                date = datetime.fromisoformat(entry["scraped_at"]).strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([date,entry["followers"],entry["following"],entry["total_likes"],entry["total_videos"]])
        print(Fore.GREEN + f"\n💾 CSV exported: {output_file}")

    def save(self, data: Dict, filename: str) -> str:
        fp = os.path.join(OUTPUT_DIR, filename)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(Fore.GREEN + f"\n💾 Tersimpan: {fp}")
        return fp

    # ── CLI ──────────────────────────────────────────────────────

    def run(self):
        print(Fore.CYAN + "\n" + "=" * 70)
        print(Fore.CYAN + "  TIKTOK PROFILE SCRAPER V2.1 (Anti-CAPTCHA No-Nav)")
        print(Fore.CYAN + "=" * 70)

        while True:
            print(Fore.CYAN + "\n📋 MENU")
            print("  1. Scrape Single Profile (stats only, anti-CAPTCHA)")
            print("  2. Analyze Growth")
            print("  3. Export to CSV")
            print("  4. Exit")
            print("  5. Scrape Profile + Followers/Following lists")

            choice = input(Fore.WHITE + "\nPilih [1-5]: ").strip()

            if choice == "1":
                username_input = input(Fore.WHITE + "\n👤 Username / URL: ").strip()
                if not username_input: continue
                result = self.scrape_profile(username_input, scrape_lists=False)
                if result["success"]:
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                    self.save(result["data"], f"profile_{result['username']}_{ts}.json")
                    self.save_tracking_data(result["data"])

            elif choice == "2":
                username = input("\n👤 Username: ").strip()
                days = input("📅 Berapa hari? [30]: ").strip()
                days = int(days) if days.isdigit() else 30
                analysis = self.analyze_growth(username, days)
                if analysis:
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                    self.save(analysis, f"growth_{analysis['username']}_{ts}.json")

            elif choice == "3":
                username = input("\n👤 Username: ").strip()
                self.export_to_csv(username)

            elif choice == "4":
                print(Fore.CYAN + "\n👋 Bye!")
                break

            elif choice == "5":
                username_input = input(Fore.WHITE + "\n👤 Username / URL: ").strip()
                if not username_input: continue
                result = self.scrape_profile(username_input, scrape_lists=True)
                if result["success"]:
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                    self.save(result["data"], f"profile_full_{result['username']}_{ts}.json")
                    self.save_tracking_data(result["data"])
                else:
                    print(Fore.RED + f"❌ {result.get('error')}")


if __name__ == "__main__":
    with TikTokProfileScraper() as scraper:
        scraper.run()