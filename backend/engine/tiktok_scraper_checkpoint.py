# tiktok_scraper_checkpoint.py  → taruh di ENGINE_DIR (folder yang sama dgn tiktok_scraper.py)
"""
TikTokCheckpointMixin — scraping komentar TikTok BATCH-PER-BATCH.

v2 (FIX ANTI-CAPTCHA):
  - scrape_all_checkpointed() sekarang NAVIGASI + WARM-UP HANYA SEKALI,
    lalu loop fetch komentar langsung TANPA reload halaman antar batch.
    (versi lama reload tiap batch → memicu CAPTCHA + logout + timeout.)
  - Cooldown antar batch tetap ada (anti rate-limit), tapi tanpa goto ulang.
  - Berhenti cepat kalau halaman ke-challenge / batch kosong → tidak loop 180s berkali.

v3 (FIX METADATA views/likes):
  - Pakai self._resolve_metadata(parsed) (didefinisikan di TikTokScraperV58):
    SSR (UNIVERSAL_DATA/SIGI) → statsV2 → fallback API item detail.
    Ini bikin play_count/digg_count/share_count/comment_count keisi.

Cara pasang di tiktok_scraper.py:
    from tiktok_scraper_checkpoint import TikTokCheckpointMixin
    class TikTokScraperV58(TikTokCheckpointMixin):
        ...
"""
import os
import time
import random
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from colorama import Fore


DEFAULT_SORT_TYPE = int(os.getenv("TIKTOK_CHECKPOINT_SORT_TYPE", "0"))


class TikTokCheckpointMixin:

    # ════════════════════════════════════════════════════════════
    # BATCH FETCHER — ambil komentar HINGGA batch_size lalu berhenti
    # di BATAS HALAMAN (count=20). TIDAK melakukan navigasi apa pun.
    # ════════════════════════════════════════════════════════════
    def _fetch_batch_cdp_tiktok(
        self,
        video_id: str,
        batch_size: int,
        start_cursor: Optional[int],
        sort_type: int,
    ) -> Tuple[List[Dict], Optional[int], bool]:
        all_comments: List[Dict] = []
        cursor = start_cursor or 0
        has_more = True
        page_num = 0
        max_pages = 200
        captcha_fail = 0

        self._block_images_enabled = True
        try:
            while len(all_comments) < batch_size and page_num < max_pages:
                page_num += 1
                try:
                    result = self.page.evaluate(f"""async () => {{
                        const awemeId  = '{video_id}';
                        const cursor   = {cursor};
                        const sortType = {sort_type};
                        const url = `/api/comment/list/?aweme_id=${{awemeId}}&cursor=${{cursor}}&count=20&sort_type=${{sortType}}&aid=1988`;
                        const resp = await fetch(url, {{credentials: 'include'}});
                        const text = await resp.text();
                        try {{
                            return JSON.parse(text);
                        }} catch(e) {{
                            return {{error: 'not_json', raw: text.slice(0,300)}};
                        }}
                    }}""")

                    if not result or result.get("error"):
                        raw = (result or {}).get("raw", "")
                        print(Fore.YELLOW + f"   ⚠️  CDP response error: {raw[:80]}")
                        if self._detect_captcha():
                            captcha_fail += 1
                            if captcha_fail > 1 or not self._wait_for_captcha_solve():
                                print(Fore.RED + "   ❌ CAPTCHA tidak teratasi — hentikan batch.")
                                break
                            continue
                        break

                    if result.get("status_code") == 5:
                        print(Fore.YELLOW + "   ⏳ Rate limit (status 5), tunggu 30s...")
                        time.sleep(30)
                        continue

                    comments_raw = result.get("comments", []) or []
                    if not comments_raw:
                        has_more = False
                        break

                    for c in comments_raw:
                        user = c.get("user", {}) or {}
                        username = user.get("unique_id", "")
                        text = c.get("text", "")
                        if not username or not text:
                            continue
                        like_count = c.get("digg_count", 0) or c.get("like_count", 0)
                        all_comments.append({
                            "username":    username,
                            "nickname":    user.get("nickname", ""),
                            "text":        text,
                            "comment_id":  str(c.get("cid", "")),
                            "like_count":  like_count,
                            "created_at":  c.get("create_time", 0),
                            "reply_count": c.get("reply_comment_total", 0),
                        })

                    new_cursor = result.get("cursor", 0)
                    print(Fore.CYAN + f"   📡 CDP page {page_num}: total batch {len(all_comments)} "
                                      f"(cursor={new_cursor})")
                    cursor = new_cursor

                    if not result.get("has_more", False):
                        has_more = False
                        break

                    time.sleep(random.uniform(2.0, 4.0))

                except Exception as e:
                    print(Fore.RED + f"   ❌ CDP batch error: {e}")
                    if self._detect_captcha():
                        self._wait_for_captcha_solve()
                    break
        finally:
            self._block_images_enabled = False

        return all_comments, cursor, has_more

    # ── helper: bangun entry komentar + sentimen (dipakai bersama) ──
    def _build_ckpt_entry(self, rc: Dict, number: int, analyze_sentiment: bool = True) -> Dict:
        text = rc.get("text", "")
        entry: Dict = {
            "number":      number,
            "username":    rc.get("username", ""),
            "nickname":    rc.get("nickname", ""),
            "text":        text,
            "comment_id":  rc.get("comment_id", ""),
            "like_count":  rc.get("like_count", 0),
            "created_at":  rc.get("created_at", 0),
            "reply_count": rc.get("reply_count", 0),
        }
        if analyze_sentiment and text:
            analysis = self.sentiment.analyze_sentiment(text)
            category = self.sentiment.categorize_comment(text)
            entry.update({
                "category":        category,
                "sentiment":       analysis["sentiment"],
                "language":        analysis["language"],
                "is_hate_speech":  analysis["is_hate_speech"],
                "is_toxic":        analysis["is_toxic"],
                "is_sarcasm":      analysis.get("is_sarcasm", False),
                "is_wellwish":     analysis.get("is_wellwish", False),
                "hate_score":      analysis["hate_score"],
                "hate_words":      analysis["hate_words"],
                "toxic_words":     analysis["toxic_words"],
                "positive_words":  analysis["positive_words"],
                "negative_words":  analysis.get("negative_words", []),
                "humor_words":     analysis["humor_words"],
                "emojis":          analysis["emojis"],
                "ml_confidence":   analysis.get("ml_confidence", 0),
                "decision_source": analysis.get("decision_source", "rule"),
            })
        return entry

    # ════════════════════════════════════════════════════════════
    # PUBLIC: scrape SATU batch (stateless — cursor dibawa pemanggil).
    # Tetap navigasi tiap dipanggil → cocok utk pemakaian API per-batch,
    # JANGAN dipakai untuk loop banyak batch (pakai scrape_all_checkpointed).
    # ════════════════════════════════════════════════════════════
    def scrape_checkpoint_batch(
        self,
        post_url: str,
        batch_size: int = 300,
        cursor: Optional[Dict] = None,
        fetch_meta: bool = True,
        analyze_sentiment: bool = True,
        sort_type: Optional[int] = None,
        do_warmup: Optional[bool] = None,
    ) -> Dict:
        parsed = self._parse_url(post_url)
        out: Dict = {
            "url": post_url, "video_id": "", "username": "",
            "batch_comments": [], "batch_count": 0,
            "next_cursor": None, "has_more": False,
            "method": "cdp", "meta": {}, "error": None,
        }
        if do_warmup is None:
            do_warmup = fetch_meta

        try:
            self.initialize_browser()

            if parsed.get("is_shortlink"):
                resolved = self._resolve_shortlink(post_url)
                parsed = self._parse_url(resolved)
                clean_url = resolved
            else:
                clean_url = post_url.split("?")[0].rstrip("/")

            if do_warmup:
                self._warm_up_session()

            print(Fore.YELLOW + f"\n🌍 [Checkpoint] Buka: {clean_url}")
            self.page.goto(clean_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(random.uniform(4, 7))
            if self._detect_captcha():
                if not self._wait_for_captcha_solve():
                    raise Exception("CAPTCHA tidak diselesaikan")
            self._close_popups()

            # ── METADATA: SSR + fallback API (views/likes) ──
            meta = self._resolve_metadata(parsed)
            video_id = meta.get("video_id") or parsed.get("video_id", "")
            if not video_id:
                raise Exception("Tidak bisa extract video_id")
            out["video_id"] = video_id
            out["username"] = meta.get("username") or parsed.get("username", "")

            if fetch_meta:
                caption = self._extract_caption_multi_strategy()
                out["meta"] = {
                    "video_id": video_id, "username": out["username"],
                    "description": caption or meta.get("description", ""),
                    "play_count": meta.get("play_count", 0),
                    "digg_count": meta.get("digg_count", 0),
                    "share_count": meta.get("share_count", 0),
                    "comment_count": meta.get("comment_count", 0),
                    "music_title": meta.get("music_title", ""),
                }

            if cursor and cursor.get("sort_type") is not None:
                st = int(cursor["sort_type"])
            elif sort_type is not None:
                st = int(sort_type)
            else:
                st = DEFAULT_SORT_TYPE
            cursor_value = cursor.get("value") if cursor else None

            raw, new_cursor, has_more = self._fetch_batch_cdp_tiktok(
                video_id, batch_size, cursor_value, st
            )

            seen = set()
            final: List[Dict] = []
            n = 0
            for c in raw:
                cid = c.get("comment_id", "")
                key = cid or hashlib.md5(f"{c.get('username','')}::{c.get('text','')}".encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                n += 1
                final.append(self._build_ckpt_entry(c, n, analyze_sentiment))

            cursor_advanced = (new_cursor is not None) and (new_cursor != (cursor_value or 0))
            can_continue = bool(has_more and cursor_advanced)
            out.update({
                "batch_comments": final,
                "batch_count": len(final),
                "next_cursor": {"method": "cdp", "value": new_cursor, "sort_type": st} if can_continue else None,
                "has_more": can_continue,
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            out["error"] = str(e)
        return out

    # ════════════════════════════════════════════════════════════
    # PUBLIC: loop semua batch dalam SATU sesi — NAVIGASI SEKALI saja.
    # (Ini yang dipakai endpoint /api/scrape/video/checkpoint.)
    # ════════════════════════════════════════════════════════════
    def scrape_all_checkpointed(
        self,
        post_url: str,
        batch_size: int = 300,
        max_total: int = 2000,
        analyze_sentiment: bool = True,
        sort_type: Optional[int] = None,
        cooldown_min: int = 10,
        cooldown_max: int = 20,
    ) -> Dict:
        st = DEFAULT_SORT_TYPE if sort_type is None else int(sort_type)
        all_comments: List[Dict] = []
        seen = set()
        meta_out: Dict = {}
        video_id = ""
        username = ""
        batch_idx = 0
        cursor = 0
        run_error: Optional[str] = None
        parsed = self._parse_url(post_url)

        try:
            self.initialize_browser()

            # ── NAVIGASI + WARM-UP: SEKALI saja ──
            if parsed.get("is_shortlink"):
                print(Fore.CYAN + "🔗 [Checkpoint] Resolving shortlink...")
                resolved = self._resolve_shortlink(post_url)
                parsed = self._parse_url(resolved)
                clean_url = resolved
            else:
                clean_url = post_url.split("?")[0].rstrip("/")

            self._warm_up_session()

            print(Fore.YELLOW + f"\n🌍 [Checkpoint] Buka (sekali): {clean_url}")
            self.page.goto(clean_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(random.uniform(4, 7))
            if self._detect_captcha():
                if not self._wait_for_captcha_solve():
                    raise Exception("CAPTCHA tidak diselesaikan")
            self._close_popups()
            for _ in range(3):
                try:
                    self.page.evaluate(f"window.scrollBy(0, {random.randint(200, 400)});")
                except Exception:
                    pass
                time.sleep(1)

            # ── METADATA: SSR + fallback API (views/likes) ──
            meta = self._resolve_metadata(parsed)
            video_id = meta.get("video_id") or parsed.get("video_id", "")
            if not video_id:
                raise Exception("Tidak bisa extract video_id")
            username = meta.get("username") or parsed.get("username", "")
            caption = self._extract_caption_multi_strategy()
            meta_out = {
                "description":   caption or meta.get("description", ""),
                "music_title":   meta.get("music_title", ""),
                "play_count":    meta.get("play_count", 0),
                "digg_count":    meta.get("digg_count", 0),
                "share_count":   meta.get("share_count", 0),
                "comment_count": meta.get("comment_count", 0),
            }
            print(Fore.GREEN + f"✅ Video ID: {video_id} — mulai checkpoint (sort_type={st})")

            # ── LOOP BATCH: TANPA navigasi ulang ──
            while len(all_comments) < max_total:
                batch_idx += 1
                remaining = max_total - len(all_comments)
                this_batch = min(batch_size, remaining)

                print(Fore.MAGENTA + f"\n{'='*70}\n🔁 CHECKPOINT BATCH #{batch_idx} "
                                     f"(terkumpul: {len(all_comments)}/{max_total}, cursor={cursor})\n{'='*70}")

                raw, new_cursor, has_more = self._fetch_batch_cdp_tiktok(
                    video_id, this_batch, cursor, st
                )

                if not raw:
                    print(Fore.YELLOW + "   ℹ️  Batch kosong / ke-challenge — hentikan loop.")
                    break

                for c in raw:
                    cid = c.get("comment_id", "")
                    key = cid or hashlib.md5(f"{c.get('username','')}::{c.get('text','')}".encode()).hexdigest()
                    if key in seen:
                        continue
                    seen.add(key)
                    all_comments.append(self._build_ckpt_entry(c, len(all_comments) + 1, analyze_sentiment))

                if not has_more:
                    print(Fore.GREEN + "\n🏁 Semua komentar sudah habis.")
                    break
                if new_cursor is None or new_cursor == cursor:
                    print(Fore.YELLOW + "   ℹ️  Cursor tidak maju — hentikan loop.")
                    break
                cursor = new_cursor

                if len(all_comments) < max_total and cooldown_max > 0:
                    cd = random.uniform(cooldown_min, cooldown_max)
                    print(Fore.YELLOW + f"\n😴 Cooldown antar batch {cd:.0f}s (tanpa reload)...")
                    time.sleep(cd)

        except Exception as e:
            import traceback
            traceback.print_exc()
            run_error = str(e)

        # renumber
        all_comments = all_comments[:max_total]
        for i, c in enumerate(all_comments, 1):
            c["number"] = i

        result: Dict = {
            "url":           post_url,
            "scraped_at":    datetime.now().isoformat(),
            "sentiment_mode": getattr(self.sentiment, "mode", ""),
            "platform":      "tiktok",
            "video_id":      video_id,
            "username":      username,
            "description":   meta_out.get("description", ""),
            "music_title":   meta_out.get("music_title", ""),
            "play_count":    meta_out.get("play_count", 0),
            "digg_count":    meta_out.get("digg_count", 0),
            "share_count":   meta_out.get("share_count", 0),
            "comment_count": meta_out.get("comment_count", 0),
            "method":        "checkpoint",
            "comments":      all_comments,
            "comments_count": len(all_comments),
            "batches":       batch_idx,
            "checkpoint":    {"batch_size": batch_size, "max_total": max_total, "batches": batch_idx},
        }

        if run_error:
            if all_comments:
                result["partial_error"] = run_error
            else:
                result["error"] = run_error

        try:
            result["sentiment_summary"] = self._summarize(all_comments, result)
        except Exception:
            result["sentiment_summary"] = {}
        try:
            ac = self._build_active_commenters(all_comments)
            result["active_commenters"] = ac
            result["active_commenters_count"] = len(ac)
        except Exception:
            result["active_commenters"] = []
            result["active_commenters_count"] = 0
        try:
            sl = sorted(all_comments, key=lambda x: x.get("like_count", 0), reverse=True)
            result["top_5_liked_comments"] = [{
                "rank": r, "username": c.get("username", ""), "nickname": c.get("nickname", ""),
                "text": c.get("text", "")[:300], "like_count": c.get("like_count", 0),
                "category": c.get("category", "NEUTRAL"), "sentiment": c.get("sentiment", ""),
            } for r, c in enumerate(sl[:5], 1)]
        except Exception:
            result["top_5_liked_comments"] = []

        return result