"""
tiktok_search_checkpoint.py
============================
Job manager untuk TikTok Deep Search.
Letakkan file ini di folder yang SAMA dengan tiktok_search_deep_endpoints.py
→ C:\\Users\\USER\\tiktok-scraper-ui\\backend\\engine\\tiktok_search_checkpoint.py

Menyimpan state tiap job ke file JSON di subfolder `tiktok_deep_jobs/`
sehingga job tetap ada walau server restart.

Alur:
  1. create_job()     → buat file state, jalankan worker di thread background
  2. get_job()        → baca state dari file (tanpa posts)
  3. get_job_posts()  → baca posts dari file terpisah (agar polling status ringan)
  4. cancel_job()     → set flag cancelled, worker akan berhenti
  5. delete_job()     → hapus file state + posts
  6. list_all_jobs()  → scan semua file state di folder
"""

import os
import json
import uuid
import time
import random
import threading
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any

# ── Folder penyimpanan state job ────────────────────────────────────────────
_HERE      = os.path.dirname(os.path.abspath(__file__))
_JOBS_DIR  = os.path.join(_HERE, "tiktok_deep_jobs")
_POSTS_DIR = os.path.join(_JOBS_DIR, "posts")

os.makedirs(_JOBS_DIR,  exist_ok=True)
os.makedirs(_POSTS_DIR, exist_ok=True)


# ── Status konstanta ─────────────────────────────────────────────────────────
class JobStatus:
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR     = "error"


# ── Path helpers ─────────────────────────────────────────────────────────────
def _state_path(job_id: str) -> str:
    return os.path.join(_JOBS_DIR, f"{job_id}.json")

def _posts_path(job_id: str) -> str:
    return os.path.join(_POSTS_DIR, f"{job_id}_posts.json")


# ── File I/O (thread-safe pakai lock per job_id) ──────────────────────────────
_locks: Dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()

def _get_lock(job_id: str) -> threading.Lock:
    with _locks_lock:
        if job_id not in _locks:
            _locks[job_id] = threading.Lock()
        return _locks[job_id]


def _read_state(job_id: str) -> Optional[dict]:
    path = _state_path(job_id)
    if not os.path.exists(path):
        return None
    with _get_lock(job_id):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


def _write_state(job_id: str, state: dict):
    path = _state_path(job_id)
    with _get_lock(job_id):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)


def _write_posts(job_id: str, posts: list):
    path = _posts_path(job_id)
    with _get_lock(job_id):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, default=str)


def _read_posts(job_id: str) -> list:
    path = _posts_path(job_id)
    if not os.path.exists(path):
        return []
    with _get_lock(job_id):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []


def _update_state(job_id: str, **kwargs):
    """Partial update — baca → merge → tulis."""
    state = _read_state(job_id) or {}
    state.update(kwargs)
    state["updated_at"] = datetime.now().isoformat()
    _write_state(job_id, state)


# ── Public API ────────────────────────────────────────────────────────────────

def create_job(mode: str, query: str, config: dict) -> str:
    """
    Buat job baru dan langsung jalankan worker di background thread.
    Return job_id.
    mode: "hashtag" | "keyword"
    """
    job_id = str(uuid.uuid4())[:12]
    now    = datetime.now().isoformat()

    state = {
        "job_id":        job_id,
        "platform":      "tiktok",
        "mode":          mode,
        "query":         query,
        "config":        config,
        "status":        JobStatus.PENDING,
        "created_at":    now,
        "updated_at":    now,
        "total_fetched": 0,
        "progress_log":  [],
        "searched_hashtags": [],
        "challenge_info":    {},
        "error":         None,
    }
    _write_state(job_id, state)

    t = threading.Thread(
        target=_run_worker,
        args=(job_id, mode, query, config),
        daemon=True,
        name=f"tiktok-deep-{job_id}",
    )
    t.start()

    return job_id


def get_job(job_id: str) -> Optional[dict]:
    """Baca state job (tanpa posts untuk efisiensi polling)."""
    return _read_state(job_id)


def get_job_posts(job_id: str) -> list:
    """Ambil posts job (hanya tersedia setelah completed)."""
    return _read_posts(job_id)


def cancel_job(job_id: str) -> bool:
    """Set status = cancelled. Worker akan berhenti di iterasi berikutnya."""
    state = _read_state(job_id)
    if not state:
        return False
    if state.get("status") in (JobStatus.COMPLETED, JobStatus.ERROR, JobStatus.CANCELLED):
        return False
    _update_state(job_id, status=JobStatus.CANCELLED)
    return True


def delete_job(job_id: str) -> bool:
    """Cancel + hapus file state dan posts."""
    cancel_job(job_id)
    deleted = False
    for path in (_state_path(job_id), _posts_path(job_id)):
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted = True
            except Exception:
                pass
    return deleted


def list_all_jobs() -> list:
    """
    Scan folder tiktok_deep_jobs/ → return ringkasan semua job
    (tanpa field posts agar response ringan).
    """
    jobs = []
    try:
        for fname in sorted(os.listdir(_JOBS_DIR), reverse=True):
            if not fname.endswith(".json"):
                continue
            job_id = fname[:-5]
            state  = _read_state(job_id)
            if not state:
                continue
            jobs.append({
                "job_id":            state.get("job_id"),
                "platform":          state.get("platform", "tiktok"),
                "mode":              state.get("mode"),
                "query":             state.get("query"),
                "status":            state.get("status"),
                "total_fetched":     state.get("total_fetched", 0),
                "searched_hashtags": state.get("searched_hashtags", []),
                "challenge_info":    state.get("challenge_info", {}),
                "created_at":        state.get("created_at"),
                "updated_at":        state.get("updated_at"),
                "error":             state.get("error"),
            })
    except Exception:
        pass
    return jobs


# ── Worker ────────────────────────────────────────────────────────────────────

def _is_cancelled(job_id: str) -> bool:
    state = _read_state(job_id)
    return (state or {}).get("status") == JobStatus.CANCELLED


def _log_progress(job_id: str, msg: str):
    state = _read_state(job_id) or {}
    log   = state.get("progress_log", [])
    log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    # Simpan hanya 50 baris terakhir agar file tidak bengkak
    if len(log) > 50:
        log = log[-50:]
    _update_state(job_id, progress_log=log)
    print(f"[TikTokDeepSearch:{job_id}] {msg}")


def _run_worker(job_id: str, mode: str, query: str, config: dict):
    """
    Worker utama yang berjalan di background thread.
    Import TikTokSearchScraper di sini (lazy) agar tidak blok startup FastAPI.
    """
    _update_state(job_id, status=JobStatus.RUNNING)
    _log_progress(job_id, f"Worker started — mode={mode} query='{query}'")

    try:
        from tiktok_search_scraper import TikTokSearchScraper  # lazy import

        with TikTokSearchScraper() as scraper:
            if mode == "hashtag":
                _worker_hashtag(job_id, query, config, scraper)
            elif mode == "keyword":
                _worker_keyword(job_id, query, config, scraper)
            else:
                raise ValueError(f"Mode tidak dikenal: {mode}")

    except Exception as e:
        traceback.print_exc()
        if not _is_cancelled(job_id):
            _update_state(job_id, status=JobStatus.ERROR, error=str(e))
            _log_progress(job_id, f"ERROR: {e}")


def _worker_hashtag(job_id: str, tag: str, config: dict, scraper):
    """
    Deep search hashtag TikTok:
      1. Scrape hashtag utama via Challenge API (max 300 posts)
      2. Expand ke related hashtags dari challenge_info
      3. Dedup & gabungkan semua posts
    """
    max_related = config.get("max_related_hashtags", 10)
    max_posts   = config.get("max_posts_per_hashtag", 300)

    seen:  set  = set()
    posts: list = []
    searched_tags: list = []

    def _add_posts(new_posts: list, source_tag: str) -> int:
        added = 0
        for p in new_posts:
            key = p.get("video_id", "")
            if not key or key in seen:
                continue
            seen.add(key)
            p["deep_source_tag"] = source_tag
            posts.append(p)
            added += 1
        return added

    # ── Step 1: scrape hashtag utama ──────────────────────────────
    if _is_cancelled(job_id):
        return

    _log_progress(job_id, f"Step 1: scraping #{tag} (max {max_posts} posts)...")

    result = scraper.search_hashtag(tag, max_posts=max_posts)
    added  = _add_posts(result.get("posts", []), tag)

    ch_info = result.get("challenge_info", {})
    searched_tags.append({
        "hashtag":     tag,
        "method":      result.get("method", ""),
        "fetched":     added,
        "video_count": ch_info.get("video_count", 0),
    })
    _update_state(
        job_id,
        total_fetched=len(posts),
        challenge_info=ch_info,
        searched_hashtags=searched_tags,
    )
    _log_progress(job_id, f"  #{tag}: {added} posts (challenge_id={ch_info.get('challenge_id', '-')})")

    if _is_cancelled(job_id):
        _finalize(job_id, posts)
        return

    # ── Step 2 (BARU): direct Search API sebagai safety net ──────
    # Ini handle kasus di mana search_hashtag() gagal karena
    # TikTok membedakan context hashtag vs keyword di API-nya
    if not _is_cancelled(job_id):
        _log_progress(job_id, f"Step 2: direct Search API '{tag}' (safety net)...")
        try:
            direct_posts = scraper.search_keyword(tag, max_posts=max_posts)
            added_direct = _add_posts(direct_posts.get("posts", []), f"direct_{tag[:20]}")
            if added_direct > 0:
                searched_tags.append({
                    "hashtag": f"[direct] {tag[:30]}",
                    "method":  "search_api",
                    "fetched": added_direct,
                })
                _log_progress(job_id, f"  +{added_direct} posts via direct search (total: {len(posts)})")
                _update_state(
                    job_id,
                    total_fetched=len(posts),
                    searched_hashtags=searched_tags,
                )
        except Exception as e:
            _log_progress(job_id, f"  ⚠️  Direct search gagal: {e}")

    # ── Step 3: expand ke related hashtags ────────────────────────
    # TikTok tidak punya "related hashtags" seperti IG, jadi kita pakai
    # discover endpoint untuk mencari hashtag serupa dari nama tag utama
    _log_progress(job_id, f"Step 3: discover related hashtags untuk '{tag}'...")

    try:
        disc = scraper.discover(tag)
        related_raw = disc.get("hashtags", [])
        # Exclude tag utama
        related = [
            h for h in related_raw
            if h.get("name", "").lower() != tag.lower()
        ][:max_related]
    except Exception as e:
        _log_progress(job_id, f"  ⚠️  Discover gagal: {e}")
        related = []

    _log_progress(job_id, f"  Expand ke {len(related)} related hashtags...")

    for i, ht in enumerate(related, 1):
        if _is_cancelled(job_id):
            break
        rname = ht.get("name", "").strip()
        if not rname:
            continue
        _log_progress(job_id, f"  [{i}/{len(related)}] #{rname}...")
        try:
            r2    = scraper.search_hashtag(rname, max_posts=100)
            added2 = _add_posts(r2.get("posts", []), rname)
            searched_tags.append({
                "hashtag": rname,
                "method":  r2.get("method", ""),
                "fetched": added2,
            })
            _log_progress(job_id, f"    +{added2} posts (total: {len(posts)})")
            _update_state(
                job_id,
                total_fetched=len(posts),
                searched_hashtags=searched_tags,
            )
        except Exception as e:
            _log_progress(job_id, f"    ⚠️  #{rname} gagal: {e}")
        time.sleep(random.uniform(2.0, 4.0))

    _finalize(job_id, posts)


def _worker_keyword(job_id: str, keyword: str, config: dict, scraper):
    """
    Deep search keyword TikTok:
      1. Discover hashtag relevan via suggest endpoint
      2. Scrape tiap hashtag + langsung via Search API
      3. Dedup & rank by likes
    """
    max_hashtags      = config.get("max_hashtags", 5)
    max_posts_per_tag = config.get("max_posts_per_hashtag", 150)

    seen:  set  = set()
    posts: list = []
    searched_tags: list = []

    def _add_posts(new_posts: list, source_tag: str) -> int:
        added = 0
        for p in new_posts:
            key = p.get("video_id", "")
            if not key or key in seen:
                continue
            seen.add(key)
            p["deep_source_tag"] = source_tag
            posts.append(p)
            added += 1
        return added

    # ── Step 1: discover hashtags relevan ─────────────────────────
    if _is_cancelled(job_id):
        return

    _log_progress(job_id, f"Step 1: discover hashtags untuk '{keyword}'...")

    try:
        disc = scraper.discover(keyword)
        candidate_tags = [h["name"] for h in disc.get("hashtags", []) if h.get("name")]
    except Exception as e:
        _log_progress(job_id, f"  ⚠️  Discover gagal: {e}")
        candidate_tags = []

    # Fallback jika discover kosong
    if not candidate_tags:
        import re
        fb = re.sub(r"\s+", "", keyword.strip()).lower()
        candidate_tags = [fb] if fb else []

    chosen = candidate_tags[:max_hashtags]
    _log_progress(job_id, f"  Hashtag dipilih: {chosen}")
    _update_state(job_id, searched_hashtags=searched_tags)

    # ── Step 2: scrape tiap hashtag ───────────────────────────────
    for i, tag in enumerate(chosen, 1):
        if _is_cancelled(job_id):
            break
        if not tag:
            continue
        _log_progress(job_id, f"Step 2 [{i}/{len(chosen)}]: #{tag} (max {max_posts_per_tag})...")
        try:
            r     = scraper.search_hashtag(tag, max_posts=max_posts_per_tag)
            added = _add_posts(r.get("posts", []), tag)
            searched_tags.append({
                "hashtag": tag,
                "method":  r.get("method", ""),
                "fetched": added,
            })
            _log_progress(job_id, f"  +{added} posts (total: {len(posts)})")
            _update_state(
                job_id,
                total_fetched=len(posts),
                searched_hashtags=searched_tags,
            )
        except Exception as e:
            _log_progress(job_id, f"  ⚠️  #{tag} gagal: {e}")
        if i < len(chosen):
            time.sleep(random.uniform(2.5, 5.0))

    # ── Step 3: direct Search API ─────────────────────────────────
    if not _is_cancelled(job_id):
        _log_progress(job_id, f"Step 3: direct Search API '{keyword}'...")
        try:
            direct_posts = scraper._fetch_via_search_api(keyword, max_posts_per_tag)
            added_direct = _add_posts(direct_posts, f"direct_{keyword[:20]}")
            searched_tags.append({
                "hashtag": f"[direct] {keyword[:30]}",
                "method":  "search_api",
                "fetched": added_direct,
            })
            _log_progress(job_id, f"  +{added_direct} posts via direct search (total: {len(posts)})")
            _update_state(
                job_id,
                total_fetched=len(posts),
                searched_hashtags=searched_tags,
            )
        except Exception as e:
            _log_progress(job_id, f"  ⚠️  Direct search gagal: {e}")

    # Sort by likes
    posts.sort(
        key=lambda x: (x.get("like_count", 0), x.get("play_count", 0)),
        reverse=True,
    )
    for idx, p in enumerate(posts, 1):
        p["rank"] = idx

    _finalize(job_id, posts)


def _finalize(job_id: str, posts: list):
    """Simpan posts ke file terpisah dan update status completed/cancelled."""
    _write_posts(job_id, posts)
    status = JobStatus.CANCELLED if _is_cancelled(job_id) else JobStatus.COMPLETED
    _update_state(job_id, status=status, total_fetched=len(posts))
    _log_progress(job_id, f"Selesai ({status}): {len(posts)} posts total")