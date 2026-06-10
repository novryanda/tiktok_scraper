"""
tiktok_search_scraper.py
========================
TikTok Search Scraper — cari post/video berdasarkan hashtag atau keyword.

Strategi (mirip Instagram V3 tapi disesuaikan untuk TikTok):
  1. Challenge API    → /api/challenge/detail/ + /api/challenge/item_list/
  2. CDP Fetch        → fetch() in-browser ke TikTok API endpoints
  3. Discover/Search  → /api/search/item/full/ keyword search

Letakkan di:
  C:\\Users\\USER\\tiktok-scraper-ui\\backend\\engine\\tiktok_search_scraper.py
"""

import os
import re
import json
import time
import random
import traceback
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote

from dotenv import load_dotenv
from colorama import Fore, init
from playwright.sync_api import sync_playwright, Page, BrowserContext

from tiktok_cookie_injector import inject_cookies_sync, has_valid_session
from tiktok_warmup import TikTokWarmupMixin

init(autoreset=True)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ── CONFIG ────────────────────────────────────────────────────────────────
HEADLESS    = os.getenv("TIKTOK_HEADLESS", "False").lower() == "true"
PROXY       = os.getenv("TIKTOK_PROXY", "")
PROFILE_DIR = os.getenv("TIKTOK_SEARCH_PROFILE_DIR", "tiktok_search_profile")
CHROME_PROFILE = os.path.join(os.getcwd(), PROFILE_DIR)

OUTPUT_DIR = "output_tiktok_search"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CHROME_PROFILE, exist_ok=True)

# ── RATE LIMIT CONFIG ─────────────────────────────────────────────────────
MAX_RETRIES        = 3
RETRY_BASE_DELAY   = 2.0
RATE_LIMIT_WAIT    = 30


class TikTokSearchScraper(TikTokWarmupMixin):
    """
    TikTok Search Scraper — hashtag & keyword search.
    Pakai sebagai context manager: `with TikTokSearchScraper() as s: ...`
    """

    def __init__(self):
        self.playwright  = None
        self.context: Optional[BrowserContext] = None
        self.page:    Optional[Page]           = None

        os.makedirs(CHROME_PROFILE, exist_ok=True)

        if has_valid_session():
            self._use_cookie_mode = True
            print(Fore.GREEN + "🍪 TikTok Search: login via cookie session")
        elif os.path.exists(CHROME_PROFILE) and os.listdir(CHROME_PROFILE):
            self._use_cookie_mode = False
            print(Fore.GREEN + f"✅ TikTok Search: Chrome profile ({os.path.basename(CHROME_PROFILE)})")
        else:
            raise RuntimeError(
                "Tidak ada session TikTok. "
                "Tambahkan cookies via tt_session.json atau jalankan tiktok_login_helper.py"
            )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ════════════════════════════════════════════════════════════
    # BROWSER SETUP
    # ════════════════════════════════════════════════════════════

    def _build_context(self) -> BrowserContext:
        self.playwright = sync_playwright().start()

        args = [
            "--window-size=1920,1080",
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
        # Docker/root: tambah --no-sandbox
        if os.getenv("CHROME_NO_SANDBOX", "False").lower() == "true":
            args += ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        if PROXY:
            args.append(f"--proxy-server={PROXY}")

        stealth_script = """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {name: 'PDF Viewer', filename: 'internal-pdf-viewer'},
                    {name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer'},
                ]
            });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['id-ID', 'id', 'en-US', 'en']});
            Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            try { delete Object.getPrototypeOf(navigator).webdriver; } catch(e) {}
            try { delete navigator.__proto__.webdriver; } catch(e) {}
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel(R) Iris(R) Xe Graphics';
                return getParameter.call(this, parameter);
            };
        """

        # Pilih persistent profile sesuai mode
        if self._use_cookie_mode:
            persistent_profile = os.path.join(os.getcwd(), "tiktok_search_cookie_profile")
            os.makedirs(persistent_profile, exist_ok=True)
        else:
            persistent_profile = CHROME_PROFILE

        context = self.playwright.chromium.launch_persistent_context(
            persistent_profile,
            headless=HEADLESS,
            slow_mo=random.randint(100, 250),
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
        context.on("page", lambda page: page.add_init_script(stealth_script))

        if self._use_cookie_mode:
            try:
                n = inject_cookies_sync(context)
                print(Fore.GREEN + f"🍪 Inject {n} cookies ke profil search")
            except Exception as e:
                raise RuntimeError(f"Gagal inject cookies TikTok: {e}")

        return context

    def initialize_browser(self):
        if self.context:
            return
        print(Fore.CYAN + "\n🌐 Membuka browser TikTok Search...")
        self.context = self._build_context()
        self.page = (
            self.context.pages[0] if self.context.pages
            else self.context.new_page()
        )

        # Block heavy resources (tapi jangan block captcha)
        captcha_safe = ["captcha", "verify", "secsdk", "rmsec"]

        def _block_heavy(route):
            try:
                rt  = route.request.resource_type
                url = route.request.url.lower()
                for pat in captcha_safe:
                    if pat in url:
                        route.continue_()
                        return
                if rt in ("image", "media", "font"):
                    route.abort()
                else:
                    route.continue_()
            except Exception:
                try:
                    route.continue_()
                except Exception:
                    pass

        self.page.route("**/*", _block_heavy)

        # Warmup natural sebelum melakukan navigasi rutin
        try:
            if hasattr(self, "warmup_natural"):
                self.warmup_natural(label="pre-search")
        except Exception:
            pass

        print(Fore.CYAN + "   ☕ Buka homepage TikTok...")
        self.page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(4, 6))
        self._close_popups()

        if "login" in self.page.url:
            self.close()
            raise RuntimeError("Redirect ke login — session expired.")
        print(Fore.GREEN + "✅ Browser TikTok Search siap")

    def _close_popups(self):
        selectors = [
            "button[aria-label='Close']",
            "div[role='dialog'] button:has-text('Decline')",
            "div[role='dialog'] button:has-text('Not now')",
        ]
        for sel in selectors:
            try:
                loc = self.page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible(timeout=1500):
                    loc.first.click(timeout=2000)
                    time.sleep(0.5)
            except Exception:
                pass

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

    # ════════════════════════════════════════════════════════════
    # CAPTCHA DETECTION
    # ════════════════════════════════════════════════════════════

    def _detect_captcha(self) -> bool:
        try:
            result = self.page.evaluate("""() => {
                const sels = ['[id*="captcha"]','[class*="captcha"]','[class*="secsdk"]'];
                const texts = ['Tarik penggeser','Drag the slider','Verifikasi','Verifying'];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 50 && r.height > 50) return true;
                    }
                }
                const body = document.body ? document.body.innerText : '';
                return texts.some(t => body.includes(t));
            }""")
            return bool(result)
        except Exception:
            return False

    def _wait_captcha(self, timeout: int = 120) -> bool:
        print(Fore.RED + "\n🛑 CAPTCHA! Selesaikan di browser. Anda punya " + str(timeout) + "s...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._detect_captcha():
                print(Fore.GREEN + "✅ CAPTCHA teratasi!")
                time.sleep(2)
                return True
            time.sleep(2)
        return False

    # ════════════════════════════════════════════════════════════
    # CDP HELPERS — semua request via in-browser fetch()
    # ════════════════════════════════════════════════════════════

    def _cdp_get(self, path: str) -> Tuple[Optional[dict], int]:
        """GET request via in-browser fetch (cookie otomatis ikut)."""
        try:
            result = self.page.evaluate("""async (path) => {
                try {
                    const resp = await fetch(path, {
                        method: 'GET',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json, text/plain, */*',
                            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8',
                        }
                    });
                    let data = null;
                    try { data = await resp.json(); } catch(e) {}
                    return { status: resp.status, data: data };
                } catch(e) {
                    return { status: 0, error: e.toString() };
                }
            }""", path)
            if not result:
                return None, 0
            return result.get("data"), int(result.get("status", 0) or 0)
        except Exception as e:
            print(Fore.YELLOW + f"   ⚠️  CDP GET error: {e}")
            return None, 0

    def _cdp_get_with_retry(self, path: str, retries: int = MAX_RETRIES) -> Optional[dict]:
        for attempt in range(retries + 1):
            data, status = self._cdp_get(path)
            if status == 429 or status == 40:  # TikTok pakai status 40 untuk rate limit
                print(Fore.YELLOW + f"   ⚠️  Rate limit ({status}), tunggu {RATE_LIMIT_WAIT}s...")
                time.sleep(RATE_LIMIT_WAIT)
                continue
            if data is not None:
                return data
            if self._detect_captcha():
                if not self._wait_captcha():
                    return None
                continue
            if attempt < retries:
                wait = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
                print(Fore.YELLOW + f"   ↩️  Retry {attempt+1}/{retries} ({wait:.1f}s)...")
                time.sleep(wait)
        return None

    # ════════════════════════════════════════════════════════════
    # STRATEGY 1: Challenge API (untuk hashtag)
    # /api/challenge/detail/ → ambil challenge_id
    # /api/challenge/item_list/ → pagination video
    # ════════════════════════════════════════════════════════════

    def _get_challenge_info(self, hashtag: str) -> Optional[Dict]:
        """Ambil info challenge (hashtag) dari TikTok — dapat challenge_id."""
        tag = hashtag.lstrip("#").lower()
        path = f"/api/challenge/detail/?challengeName={quote(tag)}&aid=1988"
        data = self._cdp_get_with_retry(path)
        if not data:
            return None

        challenge = (
            data.get("challengeInfo", {}) or {}
        ).get("challenge") or data.get("challenge", {})

        if not challenge:
            # Coba dari searchResult
            for item in data.get("searchItemList", []) or []:
                ch = item.get("challengeInfo", {})
                if ch:
                    challenge = ch.get("challenge", {})
                    break

        if not challenge or not challenge.get("id"):
            return None

        stats = (
            data.get("challengeInfo", {}) or {}
        ).get("stats") or data.get("stats", {}) or {}

        return {
            "challenge_id":  str(challenge.get("id", "")),
            "name":          challenge.get("title", "") or challenge.get("desc", tag),
            "desc":          challenge.get("desc", ""),
            "video_count":   int(stats.get("videoCount", 0) or 0),
            "view_count":    int(stats.get("viewCount", 0) or 0),
        }

    def _fetch_hashtag_via_challenge_api(
        self, hashtag: str, max_posts: int
    ) -> Tuple[List[Dict], Dict]:
        """
        Fetch video hashtag via Challenge Item List API.
        Return (posts, challenge_info).
        """
        tag = hashtag.lstrip("#").lower()
        print(Fore.CYAN + f"   📡 [Strategy 1: Challenge API] #{tag}")

        ch_info = self._get_challenge_info(tag)
        if not ch_info:
            print(Fore.YELLOW + f"   ⚠️  Challenge info tidak ditemukan untuk #{tag}")
            return [], {}

        challenge_id = ch_info["challenge_id"]
        print(Fore.CYAN + f"   ✅ Challenge ID: {challenge_id} ({ch_info.get('video_count',0):,} videos)")

        posts:  List[Dict] = []
        seen:   set        = set()
        cursor: int        = 0
        page_num            = 0
        max_pages           = min(100, (max_posts // 10) + 5)

        while len(posts) < max_posts and page_num < max_pages:
            page_num += 1
            path = (
                f"/api/challenge/item_list/"
                f"?challengeID={challenge_id}"
                f"&count=20"
                f"&cursor={cursor}"
                f"&aid=1988"
            )
            data = self._cdp_get_with_retry(path)
            if not data:
                break

            items = data.get("itemList", []) or []
            if not items:
                print(Fore.GREEN + f"   ✅ Halaman terakhir ({len(posts)} posts)")
                break

            added = 0
            for item in items:
                parsed = self._parse_video_item(item, f"hashtag_{tag}", len(posts) + 1)
                if not parsed:
                    continue
                key = parsed["video_id"]
                if not key or key in seen:
                    continue
                seen.add(key)
                posts.append(parsed)
                added += 1
                if len(posts) >= max_posts:
                    break

            print(Fore.CYAN + f"   📡 Challenge API page {page_num}: +{added} (total {len(posts)})")

            has_more = bool(data.get("hasMore", False) or data.get("has_more", False))
            cursor   = int(data.get("cursor", 0) or 0)
            if not has_more or not cursor or added == 0:
                break

            time.sleep(random.uniform(1.5, 3.0))

        return posts, ch_info

    # ════════════════════════════════════════════════════════════
    # STRATEGY 2: CDP Search (untuk keyword & fallback hashtag)
    # /api/search/item/full/ — full-text search
    # ════════════════════════════════════════════════════════════

    def _fetch_via_search_api(
        self, query: str, max_posts: int, search_type: str = "general"
    ) -> List[Dict]:
        """
        Fetch via TikTok search API.
        search_type: 'general' | 'video'
        """
        print(Fore.CYAN + f"   📡 [Strategy 2: Search API] '{query}'")
        posts:   List[Dict] = []
        seen:    set        = set()
        offset:  int        = 0
        page_num             = 0
        max_pages            = min(50, (max_posts // 10) + 5)

        while len(posts) < max_posts and page_num < max_pages:
            page_num += 1
            path = (
                f"/api/search/item/full/"
                f"?keyword={quote(query)}"
                f"&offset={offset}"
                f"&count=20"
                f"&search_id="
                f"&aid=1988"
                f"&app_language=id-ID"
            )
            data = self._cdp_get_with_retry(path)
            if not data:
                # Coba alternate endpoint
                path2 = (
                    f"/api/search/general/full/"
                    f"?keyword={quote(query)}"
                    f"&offset={offset}"
                    f"&count=20"
                    f"&aid=1988"
                )
                data = self._cdp_get_with_retry(path2)
                if not data:
                    break

            # Bisa ada di item_list atau data
            items = (
                data.get("item_list", [])
                or data.get("data", [])
                or data.get("itemList", [])
                or []
            )

            # Filter: kalau ini array of wrapper, extract item
            actual_items = []
            for entry in items:
                if isinstance(entry, dict):
                    item = entry.get("item", entry.get("aweme_info", entry))
                    if item.get("id") or item.get("aweme_id"):
                        actual_items.append(item)

            if not actual_items:
                print(Fore.GREEN + f"   ✅ Search API: halaman terakhir ({len(posts)} posts)")
                break

            added = 0
            for item in actual_items:
                parsed = self._parse_video_item(item, f"search_{query[:20]}", len(posts) + 1)
                if not parsed:
                    continue
                key = parsed["video_id"]
                if not key or key in seen:
                    continue
                seen.add(key)
                posts.append(parsed)
                added += 1
                if len(posts) >= max_posts:
                    break

            print(Fore.CYAN + f"   📡 Search API page {page_num}: +{added} (total {len(posts)})")

            has_more = bool(
                data.get("has_more", False)
                or data.get("hasMore", False)
            )
            offset = offset + len(actual_items)
            if not has_more or added == 0:
                break

            time.sleep(random.uniform(1.5, 2.5))

        return posts

    # ════════════════════════════════════════════════════════════
    # STRATEGY 3: CDP Hashtag Page Navigate (fallback ultimate)
    # Buka halaman /tag/<hashtag> langsung lalu intercept response
    # ════════════════════════════════════════════════════════════

    def _fetch_hashtag_via_page_navigate(
        self, hashtag: str, max_posts: int
    ) -> List[Dict]:
        """
        Fallback: buka halaman tag langsung lalu extract dari SIGI_STATE.
        Dapat batch pertama saja (biasanya 12-30 video).
        """
        tag = hashtag.lstrip("#").lower()
        print(Fore.CYAN + f"   📡 [Strategy 3: Page Navigate] #{tag}")

        posts: List[Dict] = []
        seen:  set        = set()

        try:
            collected: List[dict] = []

            def _on_response(response):
                try:
                    url = response.url
                    if "item_list" in url or "challenge/item_list" in url:
                        body = response.json()
                        for item in body.get("itemList", []) or []:
                            collected.append(item)
                except Exception:
                    pass

            self.page.on("response", _on_response)
            self.page.goto(
                f"https://www.tiktok.com/tag/{tag}",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            time.sleep(random.uniform(3, 5))

            if self._detect_captcha():
                if not self._wait_captcha():
                    self.page.remove_listener("response", _on_response)
                    return []

            self._close_popups()

            # Scroll sekali untuk trigger load
            for _ in range(3):
                self.page.evaluate("window.scrollBy(0, 600);")
                time.sleep(1.5)

            self.page.remove_listener("response", _on_response)

            # Parse dari collected intercept
            for item in collected:
                parsed = self._parse_video_item(item, f"page_nav_{tag}", len(posts) + 1)
                if not parsed:
                    continue
                key = parsed["video_id"]
                if not key or key in seen:
                    continue
                seen.add(key)
                posts.append(parsed)
                if len(posts) >= max_posts:
                    break

            # Juga coba dari SIGI_STATE
            if not posts:
                sigi = self.page.evaluate("""() => {
                    const el = document.getElementById('SIGI_STATE') || document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                    if (!el) return null;
                    try { return JSON.parse(el.textContent); } catch(e) { return null; }
                }""")
                if sigi:
                    # Coba extract item dari SIGI_STATE.ItemModule
                    im = sigi.get("ItemModule", {}) or {}
                    for vid_id, item_data in im.items():
                        parsed = self._parse_sigi_item(item_data, f"sigi_{tag}", len(posts) + 1)
                        if parsed:
                            key = parsed["video_id"]
                            if key not in seen:
                                seen.add(key)
                                posts.append(parsed)
                            if len(posts) >= max_posts:
                                break

            print(Fore.CYAN + f"   📡 Page Navigate: {len(posts)} posts")

        except Exception as e:
            print(Fore.RED + f"   ❌ Page Navigate error: {e}")

        return posts

    # ════════════════════════════════════════════════════════════
    # ORCHESTRATOR
    # ════════════════════════════════════════════════════════════

    def _collect_hashtag_posts(
        self, hashtag: str, max_posts: int
    ) -> Dict:
        """
        Coba Strategy 1 → 2 → 3, return hasil terbaik.
        """
        out = {
            "posts": [], "challenge_info": {},
            "method": "", "error": None,
        }
        self.initialize_browser()

        # Strategy 1: Challenge API
        posts, ch_info = self._fetch_hashtag_via_challenge_api(hashtag, max_posts)
        if posts:
            out["posts"]          = posts[:max_posts]
            out["challenge_info"] = ch_info
            out["method"]         = "challenge_api"
            print(Fore.GREEN + f"   ✅ Challenge API: {len(out['posts'])} posts")
            return out

        print(Fore.YELLOW + "   ↩️  Challenge API kosong → coba Search API...")

        # Strategy 2a: Search API tanpa # (text search biasa)
        posts = self._fetch_via_search_api(hashtag.lstrip("#"), max_posts)
        if posts:
            out["posts"]  = posts[:max_posts]
            out["method"] = "search_api"
            print(Fore.GREEN + f"   ✅ Search API: {len(out['posts'])} posts")
            return out

        # Strategy 2b: Search API dengan # prefix (TikTok kadang beda hasil untuk hashtag search)
        posts = self._fetch_via_search_api(f"#{hashtag.lstrip('#')}", max_posts)
        if posts:
            out["posts"]  = posts[:max_posts]
            out["method"] = "search_api_with_hash"
            print(Fore.GREEN + f"   ✅ Search API (#prefix): {len(out['posts'])} posts")
            return out

        print(Fore.YELLOW + "   ↩️  Search API kosong → coba Page Navigate...")

        # Strategy 3: Navigate langsung
        posts = self._fetch_hashtag_via_page_navigate(hashtag, max_posts)
        if posts:
            out["posts"]  = posts[:max_posts]
            out["method"] = "page_navigate"
            print(Fore.GREEN + f"   ✅ Page Navigate: {len(out['posts'])} posts")
            return out

        print(Fore.RED + f"   ❌ Semua strategy gagal untuk #{hashtag}")
        out["error"] = "all_strategies_failed"
        return out

    # ════════════════════════════════════════════════════════════
    # DISCOVER — cari hashtag/user dari keyword
    # ════════════════════════════════════════════════════════════

    def _discover_hashtags(self, query: str) -> Dict:
        """
        Gunakan TikTok search suggest / autocomplete untuk
        menemukan hashtag relevan dari sebuah keyword.
        """
        result = {"hashtags": [], "users": []}

        # Endpoint suggest
        path = (
            f"/api/suggest/complete/"
            f"?keyword={quote(query)}"
            f"&scene=search_suggest"
            f"&aid=1988"
        )
        data = self._cdp_get_with_retry(path)
        if data:
            for sug in data.get("sug_list", []) or []:
                word = sug.get("sug_word", "") or sug.get("name", "")
                if word:
                    result["hashtags"].append({"name": word.lstrip("#"), "source": "suggest"})

        # Kalau suggest kosong, coba search hashtag endpoint
        if not result["hashtags"]:
            path2 = (
                f"/api/search/hashtag/full/"
                f"?keyword={quote(query)}"
                f"&count=10"
                f"&aid=1988"
            )
            data2 = self._cdp_get_with_retry(path2)
            if data2:
                for item in data2.get("challenge_list", []) or []:
                    ch = item.get("challenge_info", {}).get("challenge", {})
                    name = ch.get("title", "")
                    if name:
                        result["hashtags"].append({
                            "name":        name,
                            "video_count": (item.get("challenge_info", {}) or {}).get("stats", {}).get("videoCount", 0),
                            "source":      "search_hashtag",
                        })

        return result

    # ════════════════════════════════════════════════════════════
    # PARSING HELPERS
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _normalize_hashtag(raw: str) -> str:
        s = re.sub(r"\s+", "", (raw or "").strip().lstrip("#"))
        return s.lower()

    @staticmethod
    def _fmt_count(n) -> str:
        n = int(n or 0)
        if n >= 1_000_000_000:
            return f"{n/1_000_000_000:.1f}B"
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}K"
        return str(n)

    def _parse_video_item(self, item: dict, source: str, rank: int) -> Optional[Dict]:
        """
        Parse item dari Challenge API / Search API.
        Field yang diambil: video_id, url, author, stats, caption, hashtags, dll.
        """
        if not item:
            return None

        # video id bisa di 'id' atau 'aweme_id'
        vid_id = str(item.get("id", "") or item.get("aweme_id", "") or "")
        if not vid_id:
            return None

        # Author
        author = item.get("author", {}) or {}
        username    = author.get("uniqueId", "") or author.get("unique_id", "")
        full_name   = author.get("nickname", "")
        is_verified = bool(author.get("verified", False))

        # Caption / desc
        desc = (item.get("desc", "") or "")[:500]

        # Hashtags dari textExtra
        hashtags = []
        for te in (item.get("textExtra", []) or []):
            ht = te.get("hashtagName", "") or te.get("hashtag_name", "")
            if ht:
                hashtags.append(ht)

        # Stats — bisa di 'stats' atau 'statsV2'
        stats   = item.get("stats", {}) or {}
        statsv2 = item.get("statsV2", {}) or {}

        def _s(key):
            v = stats.get(key, 0)
            if not v:
                v = statsv2.get(key, 0)
            try:
                return int(v or 0)
            except (ValueError, TypeError):
                return 0

        play_count    = _s("playCount")
        like_count    = _s("diggCount")
        comment_count = _s("commentCount")
        share_count   = _s("shareCount")
        collect_count = _s("collectCount")

        # Timestamps
        create_time = int(item.get("createTime", 0) or 0)
        try:
            created_iso = datetime.fromtimestamp(create_time).isoformat() if create_time else ""
        except Exception:
            created_iso = ""

        # Video duration
        video_info = item.get("video", {}) or {}
        duration   = int(video_info.get("duration", 0) or 0)

        # Music
        music      = item.get("music", {}) or {}
        music_title = music.get("title", "")

        # Thumbnail
        thumb = ""
        covers = video_info.get("cover", {}) or {}
        urls   = covers.get("url_list", []) if isinstance(covers, dict) else []
        if urls:
            thumb = urls[0]
        if not thumb:
            thumb = (video_info.get("originCover", "") or
                     item.get("video", {}).get("dynamicCover", ""))
            if isinstance(thumb, dict):
                thumb = thumb.get("url_list", [""])[0]

        # URL video
        url = f"https://www.tiktok.com/@{username}/video/{vid_id}" if username else f"https://www.tiktok.com/video/{vid_id}"

        return {
            "video_id":       vid_id,
            "url":            url,
            "username":       username,
            "full_name":      full_name,
            "is_verified":    is_verified,
            "caption":        desc,
            "hashtags":       hashtags,
            "like_count":     like_count,
            "comment_count":  comment_count,
            "share_count":    share_count,
            "play_count":     play_count,
            "collect_count":  collect_count,
            "duration":       duration,
            "music_title":    music_title,
            "create_time":    create_time,
            "create_time_iso": created_iso,
            "thumbnail_url":  thumb,
            "source":         source,
            "rank":           rank,
        }

    def _parse_sigi_item(self, item: dict, source: str, rank: int) -> Optional[Dict]:
        """
        Parse item dari SIGI_STATE.ItemModule (format halaman).
        Sedikit berbeda field naming dari API response.
        """
        if not item:
            return None
        vid_id = str(item.get("id", "") or item.get("aweme_id", "") or "")
        if not vid_id:
            return None

        # Di SIGI_STATE, author bisa berupa string (uniqueId)
        author   = item.get("author", {})
        username = author if isinstance(author, str) else (author.get("uniqueId", "") or "")
        author_obj = {} if isinstance(author, str) else (author or {})

        stats = item.get("stats", {}) or {}

        def _s(key):
            try:
                return int(stats.get(key, 0) or 0)
            except Exception:
                return 0

        create_time = int(item.get("createTime", 0) or 0)
        try:
            created_iso = datetime.fromtimestamp(create_time).isoformat() if create_time else ""
        except Exception:
            created_iso = ""

        hashtags = []
        for te in (item.get("textExtra", []) or []):
            ht = te.get("hashtagName", "")
            if ht:
                hashtags.append(ht)

        video_info = item.get("video", {}) or {}
        music      = item.get("music", {}) or {}
        url = f"https://www.tiktok.com/@{username}/video/{vid_id}"

        return {
            "video_id":        vid_id,
            "url":             url,
            "username":        username,
            "full_name":       author_obj.get("nickname", ""),
            "is_verified":     bool(author_obj.get("verified", False)),
            "caption":         (item.get("desc", "") or "")[:500],
            "hashtags":        hashtags,
            "like_count":      _s("diggCount"),
            "comment_count":   _s("commentCount"),
            "share_count":     _s("shareCount"),
            "play_count":      _s("playCount"),
            "collect_count":   _s("collectCount"),
            "duration":        int(video_info.get("duration", 0) or 0),
            "music_title":     music.get("title", ""),
            "create_time":     create_time,
            "create_time_iso": created_iso,
            "thumbnail_url":   "",
            "source":          source,
            "rank":            rank,
        }

    # ════════════════════════════════════════════════════════════
    # PUBLIC API
    # ════════════════════════════════════════════════════════════

    def search_hashtag(
        self,
        hashtag: str,
        max_posts: int = 60,
    ) -> Dict:
        """
        Scrape video dari sebuah hashtag TikTok.
        Return dict dengan posts, challenge_info, metadata.
        """
        tag = self._normalize_hashtag(hashtag)
        result: Dict = {
            "query":         hashtag,
            "hashtag":       tag,
            "scraped_at":    datetime.now().isoformat(),
            "scraped_date":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "success":       False,
            "total_fetched": 0,
            "method":        "",
            "challenge_info": {},
            "posts":         [],
            "error":         None,
        }
        if not tag:
            result["error"] = "Hashtag tidak valid"
            return result

        print(Fore.CYAN + "\n" + "=" * 70)
        print(Fore.CYAN + f"🔎 TIKTOK SEARCH HASHTAG: #{tag}  (max_posts={max_posts})")
        print(Fore.CYAN + "=" * 70)

        try:
            collected = self._collect_hashtag_posts(tag, max_posts)

            if collected.get("error") == "all_strategies_failed" and not collected["posts"]:
                result["error"] = (
                    "Semua strategy gagal. "
                    "Hashtag mungkin tidak ada atau sesi perlu di-refresh."
                )
                return result

            result.update({
                "posts":          collected["posts"],
                "total_fetched":  len(collected["posts"]),
                "challenge_info": collected.get("challenge_info", {}),
                "method":         collected.get("method", ""),
                "success":        True,
            })
            print(Fore.GREEN + f"\n✅ #{tag}: {result['total_fetched']} post via {result['method']}")

        except Exception as e:
            traceback.print_exc()
            result["error"] = str(e)

        return result

    def search_keyword(
        self,
        keyword: str,
        max_posts: int    = 60,
        max_hashtags: int = 5,
    ) -> Dict:
        """
        Cari video berdasarkan keyword:
          1. Discover hashtag relevan
          2. Scrape tiap hashtag
          3. Juga scrape langsung via Search API
          4. Dedup + rank by likes
        """
        result: Dict = {
            "query":             keyword,
            "scraped_at":        datetime.now().isoformat(),
            "scraped_date":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "success":           False,
            "total_fetched":     0,
            "searched_hashtags": [],
            "suggested_hashtags": [],
            "posts":             [],
            "error":             None,
        }
        kw = (keyword or "").strip()
        if not kw:
            result["error"] = "Keyword kosong"
            return result

        print(Fore.CYAN + "\n" + "=" * 70)
        print(Fore.CYAN + f"🔎 TIKTOK SEARCH KEYWORD: '{kw}'  (max_posts={max_posts})")
        print(Fore.CYAN + "=" * 70)

        try:
            self.initialize_browser()

            # Discover related hashtags
            disc = self._discover_hashtags(kw)
            suggested = disc.get("hashtags", [])[:20]
            result["suggested_hashtags"] = suggested

            candidate_tags = [h["name"] for h in suggested if h.get("name")]
            if not candidate_tags:
                # Fallback: normalize keyword jadi hashtag
                fb = self._normalize_hashtag(kw)
                candidate_tags = [fb] if fb else []
            chosen = candidate_tags[:max_hashtags]

            seen: set  = set()
            agg:  List[Dict] = []

            def _add(posts_list: List[Dict], source_tag: str):
                count = 0
                for p in posts_list:
                    key = p.get("video_id", "")
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    p["search_source_tag"] = source_tag
                    agg.append(p)
                    count += 1
                return count

            # Step 1: scrape tiap hashtag
            for i, tag in enumerate(chosen, 1):
                if not tag:
                    continue
                print(Fore.CYAN + f"\n   [{i}/{len(chosen)}] #{tag}...")
                collected = self._collect_hashtag_posts(tag, max_posts)
                added = _add(collected.get("posts", []), tag)
                result["searched_hashtags"].append({
                    "hashtag": tag,
                    "method":  collected.get("method", ""),
                    "fetched": added,
                })
                _log = f"  +{added} posts dari #{tag} (total: {len(agg)})"
                print(Fore.CYAN + _log)
                if i < len(chosen):
                    time.sleep(random.uniform(2.0, 4.0))

            # Step 2: juga scrape langsung via Search API
            print(Fore.CYAN + f"\n   [Direct Search API] '{kw}'...")
            direct_posts = self._fetch_via_search_api(kw, max_posts)
            added_direct  = _add(direct_posts, f"direct_{kw[:20]}")
            print(Fore.CYAN + f"   +{added_direct} posts dari direct search (total: {len(agg)})")

            # Sort by likes
            agg.sort(
                key=lambda x: (x.get("like_count", 0), x.get("play_count", 0)),
                reverse=True,
            )
            agg = agg[:max_posts]
            for idx, p in enumerate(agg, 1):
                p["rank"] = idx

            result["posts"]         = agg
            result["total_fetched"] = len(agg)
            result["success"]       = True
            print(Fore.GREEN + f"\n✅ '{kw}': {len(agg)} post")

        except Exception as e:
            traceback.print_exc()
            result["error"] = str(e)

        return result

    def discover(self, query: str) -> Dict:
        """Temukan hashtag & user yang relevan untuk sebuah query."""
        result = {
            "query":      query,
            "scraped_at": datetime.now().isoformat(),
            "success":    False,
            "hashtags":   [],
            "users":      [],
            "error":      None,
        }
        if not (query or "").strip():
            result["error"] = "Query kosong"
            return result
        try:
            self.initialize_browser()
            disc             = self._discover_hashtags(query.strip())
            result["hashtags"] = disc.get("hashtags", [])
            result["users"]    = disc.get("users", [])
            result["success"]  = True
        except Exception as e:
            traceback.print_exc()
            result["error"] = str(e)
        return result

    def _save(self, data: Dict, filename: str) -> str:
        fp = os.path.join(OUTPUT_DIR, filename)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        print(Fore.GREEN + f"💾 Saved: {fp}")
        return fp

    def run(self):
        print(Fore.CYAN + "\n" + "=" * 70)
        print(Fore.CYAN + "  TIKTOK SEARCH SCRAPER")
        print(Fore.CYAN + "  Strategy: Challenge API → Search API → Page Navigate")
        print(Fore.CYAN + "=" * 70)
        while True:
            print(Fore.CYAN + "\n📋 MENU")
            print("  1. Search by Hashtag")
            print("  2. Search by Keyword")
            print("  3. Discover")
            print("  4. Exit")
            choice = input("\nPilih [1-4]: ").strip()
            if choice == "1":
                tag = input("Hashtag (tanpa #): ").strip()
                if not tag:
                    continue
                raw = input("Max posts [60]: ").strip()
                mp  = int(raw) if raw.isdigit() else 60
                res = self.search_hashtag(tag, max_posts=mp)
                self._save(
                    res,
                    f"tiktok_search_tag_{self._normalize_hashtag(tag)}"
                    f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                )
            elif choice == "2":
                kw = input("Keyword: ").strip()
                if not kw:
                    continue
                raw = input("Max posts [60]: ").strip()
                mp  = int(raw) if raw.isdigit() else 60
                raw = input("Max hashtags [5]: ").strip()
                mh  = int(raw) if raw.isdigit() else 5
                res = self.search_keyword(kw, max_posts=mp, max_hashtags=mh)
                self._save(res, f"tiktok_search_kw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            elif choice == "3":
                q = input("Query: ").strip()
                if not q:
                    continue
                res = self.discover(q)
                print(json.dumps(res, ensure_ascii=False, indent=2, default=str)[:2000])
            elif choice == "4":
                print(Fore.CYAN + "\n👋 Bye!")
                break
            else:
                print(Fore.RED + "❌ Pilihan tidak valid")


if __name__ == "__main__":
    with TikTokSearchScraper() as scraper:
        scraper.run()