"""
tiktok_search_endpoints.py
===========================
FastAPI Router untuk TikTok Search (hashtag & keyword).
FIX: sys.path.insert(0, ENGINE_DIR) ditambahkan ke SEMUA generated script
     agar module tiktok_search_scraper & tiktok_search_checkpoint bisa diimport
     meskipun script dijalankan dari cwd=ENGINE_DIR.
"""

import io
import csv
import os
import sys
import json
import time
import traceback
from datetime import datetime
from typing import List, Optional, Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ============================================================================
# PATH CONFIGURATION
# ============================================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.environ.get("TIKTOK_ENGINE_DIR", os.path.join(_HERE, "engine"))
ENGINE_DIR = os.path.abspath(ENGINE_DIR)  # pastikan absolut

# Pastikan folder engine ada
if not os.path.isdir(ENGINE_DIR):
    raise RuntimeError(f"Folder engine tidak ditemukan: {ENGINE_DIR}")

_OUTPUT_VIDEO_DIR = os.path.join(ENGINE_DIR, "output_tiktok")
os.makedirs(_OUTPUT_VIDEO_DIR, exist_ok=True)

tiktok_search_router = APIRouter()

# ============================================================================
# HELPER
# ============================================================================

def _local_save_json(data: dict, filename: str) -> str:
    os.makedirs(_OUTPUT_VIDEO_DIR, exist_ok=True)
    fp = os.path.join(_OUTPUT_VIDEO_DIR, filename)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return filename

def _success(data: Any, message: str = "Success"):
    return {
        "success":   True,
        "message":   message,
        "timestamp": datetime.now().isoformat(),
        "data":      data,
    }

def _failure(message: str, data: Optional[dict] = None):
    return {
        "success":   False,
        "message":   message,
        "timestamp": datetime.now().isoformat(),
        "data":      data or {},
    }

def _sanitize(name: str) -> str:
    import re
    return re.sub(r'[^A-Za-z0-9._-]', '_', name) or "unknown"

# ============================================================================
# REQUEST MODELS
# ============================================================================

class DiscoverRequest(BaseModel):
    query: str

class SearchHashtagRequest(BaseModel):
    hashtag: str
    max_posts: int = 60

class SearchKeywordRequest(BaseModel):
    keyword: str
    max_posts: int    = 60
    max_hashtags: int = 5

class DeepHashtagRequest(BaseModel):
    hashtag: str
    max_related_hashtags: int = 10
    include_top: bool = True

class DeepKeywordRequest(BaseModel):
    keyword: str
    max_hashtags: int = 8

class DownloadSearchCsvRequest(BaseModel):
    posts: List[Any] = []
    filename_hint: str = "tiktok_search"

# ============================================================================
# SUBPROCESS RUNNER (FIXED: tambah sys.path.insert ke semua script)
# ============================================================================

# FIX: Script tmp disimpan di dalam _HERE (folder backend), tapi dijalankan
#      dengan cwd=ENGINE_DIR. Python TIDAK otomatis menambahkan cwd ke sys.path
#      saat menggunakan subprocess.run() — berbeda dengan menjalankan script
#      langsung dari terminal. Solusi: inject sys.path.insert(0, ENGINE_DIR)
#      di awal setiap generated script agar import module dari engine/ berhasil.

# Path aman ENGINE_DIR untuk diinjeksikan ke dalam f-string (escape backslash Windows)
_ENGINE_DIR_ESCAPED = ENGINE_DIR.replace("\\", "\\\\")

# Header boilerplate yang WAJIB ada di setiap generated script
_SCRIPT_HEADER = f"""import sys, os
# FIX: tambahkan engine dir ke sys.path agar module bisa diimport
_engine_dir = r'{ENGINE_DIR}'
if _engine_dir not in sys.path:
    sys.path.insert(0, _engine_dir)
os.chdir(_engine_dir)  # pastikan cwd = engine dir
"""

def _run_search_subprocess(script: str, timeout: int, tag: str) -> dict:
    """
    Jalankan script Python, return parsed JSON dari stdout.

    FIX v2: Setiap script yang di-generate sekarang diawali dengan
    _SCRIPT_HEADER yang berisi sys.path.insert(0, ENGINE_DIR) sehingga
    'from tiktok_search_scraper import ...' selalu berhasil meskipun
    script tmp-file ada di folder lain (_tmp_search/).
    """
    import subprocess
    import tempfile

    SCRIPT_TMP_DIR = os.path.join(_HERE, "_tmp_search")
    os.makedirs(SCRIPT_TMP_DIR, exist_ok=True)

    # Gabungkan header path-fix + script asli
    full_script = _SCRIPT_HEADER + "\n" + script

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8", dir=SCRIPT_TMP_DIR
    ) as f:
        f.write(full_script)
        script_path = f.name

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=ENGINE_DIR,                 # cwd=ENGINE_DIR tetap dipakai
            encoding="utf-8",
            env=env,
        )

        if proc.stderr:
            for line in proc.stderr.strip().splitlines()[-40:]:
                print(f"[{tag}] stderr: {line}")

        if proc.returncode != 0:
            tail = (proc.stderr or "")[-1500:]
            raise RuntimeError(f"Search engine exit {proc.returncode}.\n{tail}")

        # Ambil JSON dari stdout (scan dari baris terakhir ke atas)
        for line in reversed(proc.stdout.strip().splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

        raise RuntimeError("Tidak ada JSON valid dari search engine.")
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass

# ============================================================================
# WRAPPERS
# ============================================================================

def _run_discover(query: str) -> dict:
    # NOTE: TIDAK perlu sys.path.insert di sini — sudah ada di _SCRIPT_HEADER
    script = f"""
import json
from tiktok_search_scraper import TikTokSearchScraper
with TikTokSearchScraper() as scraper:
    result = scraper.discover({json.dumps(query)})
    print(json.dumps(result, ensure_ascii=False, default=str))
"""
    return _run_search_subprocess(script, timeout=120, tag="tt-discover")

def _run_search_hashtag(hashtag: str, max_posts: int) -> dict:
    script = f"""
import json
from tiktok_search_scraper import TikTokSearchScraper
with TikTokSearchScraper() as scraper:
    result = scraper.search_hashtag(
        {json.dumps(hashtag)},
        max_posts={int(max_posts)},
    )
    print(json.dumps(result, ensure_ascii=False, default=str))
"""
    timeout = max(180, 120 + (max_posts // 10) * 15)
    return _run_search_subprocess(script, timeout=timeout, tag="tt-hashtag")

def _run_search_keyword(keyword: str, max_posts: int, max_hashtags: int) -> dict:
    script = f"""
import json
from tiktok_search_scraper import TikTokSearchScraper
with TikTokSearchScraper() as scraper:
    result = scraper.search_keyword(
        {json.dumps(keyword)},
        max_posts={int(max_posts)},
        max_hashtags={int(max_hashtags)},
    )
    print(json.dumps(result, ensure_ascii=False, default=str))
"""
    timeout = max(300, 120 + max_hashtags * 90)
    return _run_search_subprocess(script, timeout=timeout, tag="tt-keyword")

# ============================================================================
# CSV
# ============================================================================

SEARCH_CSV_FIELDS = [
    "rank", "source", "search_source_tag",
    "video_id", "url", "username", "full_name", "is_verified",
    "caption", "hashtags",
    "like_count", "comment_count", "share_count", "play_count", "collect_count",
    "duration", "music_title",
    "create_time_iso",
]

def _posts_to_csv_rows(posts: list) -> list:
    rows = []
    for p in posts:
        rows.append({
            "rank":              p.get("rank", ""),
            "source":            p.get("source", ""),
            "search_source_tag": p.get("search_source_tag", ""),
            "video_id":          p.get("video_id", ""),
            "url":               p.get("url", ""),
            "username":          p.get("username", ""),
            "full_name":         p.get("full_name", ""),
            "is_verified":       p.get("is_verified", False),
            "caption":           p.get("caption", ""),
            "hashtags":          "|".join(p.get("hashtags", []) or []),
            "like_count":        p.get("like_count", 0),
            "comment_count":     p.get("comment_count", 0),
            "share_count":       p.get("share_count", 0),
            "play_count":        p.get("play_count", 0),
            "collect_count":     p.get("collect_count", 0),
            "duration":          p.get("duration", 0),
            "music_title":       p.get("music_title", ""),
            "create_time_iso":   p.get("create_time_iso", ""),
        })
    return rows

def _rows_to_csv_bytes(rows: list, fieldnames: list) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")

# ============================================================================
# ENDPOINTS
# ============================================================================

@tiktok_search_router.post("/api/search/discover")
def search_discover(req: DiscoverRequest):
    q = (req.query or "").strip()
    if not q:
        return _failure("Query kosong")
    try:
        result = _run_discover(q)
        if not result.get("success"):
            return _failure(result.get("error") or "Discover gagal", result)
        return _success(result, f"{len(result.get('hashtags', []))} hashtag ditemukan")
    except Exception as e:
        traceback.print_exc()
        return _failure(f"Discover error: {str(e)}")

@tiktok_search_router.post("/api/search/hashtag")
def search_hashtag_endpoint(req: SearchHashtagRequest):
    max_posts = max(1, min(req.max_posts, 300))
    try:
        result = _run_search_hashtag(req.hashtag, max_posts)
        if result.get("success"):
            fn = f"tt_search_tag_{_sanitize(result.get('hashtag', 'tag'))}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            _local_save_json(result, fn)
            result["_meta"] = {"saved_file": fn}
            return _success(result, f"#{result.get('hashtag')}: {result.get('total_fetched', 0)} video")
        return _failure(result.get("error") or "Pencarian hashtag gagal", result)
    except Exception as e:
        traceback.print_exc()
        return _failure(f"Hashtag search error: {str(e)}")

@tiktok_search_router.post("/api/search/keyword")
def search_keyword_endpoint(req: SearchKeywordRequest):
    max_posts    = max(1, min(req.max_posts, 300))
    max_hashtags = max(1, min(req.max_hashtags, 10))
    try:
        result = _run_search_keyword(req.keyword, max_posts, max_hashtags)
        if result.get("success"):
            fn = f"tt_search_kw_{_sanitize(req.keyword)[:40]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            _local_save_json(result, fn)
            result["_meta"] = {"saved_file": fn}
            return _success(result, f"'{req.keyword}': {result.get('total_fetched', 0)} video")
        return _failure(result.get("error") or "Pencarian keyword gagal", result)
    except Exception as e:
        traceback.print_exc()
        return _failure(f"Keyword search error: {str(e)}")

@tiktok_search_router.post("/api/download/search-csv")
def download_search_csv(req: DownloadSearchCsvRequest):
    rows = _posts_to_csv_rows(req.posts)
    data = _rows_to_csv_bytes(rows, SEARCH_CSV_FIELDS)
    fname = _sanitize(f"{req.filename_hint}_videos.csv")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )

# ============================================================================
# DEEP SEARCH (background jobs)
# ============================================================================

@tiktok_search_router.post("/api/search/deep/hashtag")
def deep_search_hashtag(req: DeepHashtagRequest):
    q = (req.hashtag or "").strip().lstrip("#")
    if not q:
        return _failure("Hashtag kosong")
    try:
        # FIX: tambah engine dir ke sys.path sebelum import lazy
        if ENGINE_DIR not in sys.path:
            sys.path.insert(0, ENGINE_DIR)
        from tiktok_search_checkpoint import create_job
        config = {
            "max_related_hashtags": req.max_related_hashtags,
            "include_top":          req.include_top,
        }
        job_id = create_job(mode="hashtag", query=q, config=config)
        return _success({"job_id": job_id, "mode": "hashtag", "query": q})
    except Exception as e:
        traceback.print_exc()
        return _failure(f"Deep search error: {str(e)}")

@tiktok_search_router.post("/api/search/deep/keyword")
def deep_search_keyword(req: DeepKeywordRequest):
    q = (req.keyword or "").strip()
    if not q:
        return _failure("Keyword kosong")
    try:
        if ENGINE_DIR not in sys.path:
            sys.path.insert(0, ENGINE_DIR)
        from tiktok_search_checkpoint import create_job
        config = {"max_hashtags": req.max_hashtags}
        job_id = create_job(mode="keyword", query=q, config=config)
        return _success({"job_id": job_id, "mode": "keyword", "query": q})
    except Exception as e:
        traceback.print_exc()
        return _failure(f"Deep search error: {str(e)}")

@tiktok_search_router.get("/api/search/deep/jobs")
def list_deep_jobs():
    try:
        if ENGINE_DIR not in sys.path:
            sys.path.insert(0, ENGINE_DIR)
        from tiktok_search_checkpoint import list_all_jobs
        jobs = list_all_jobs()
        return _success({"jobs": jobs, "count": len(jobs)})
    except Exception as e:
        return _failure(f"List jobs error: {str(e)}")

@tiktok_search_router.get("/api/search/deep/jobs/{job_id}")
def get_deep_job(job_id: str):
    try:
        if ENGINE_DIR not in sys.path:
            sys.path.insert(0, ENGINE_DIR)
        from tiktok_search_checkpoint import get_job
        state = get_job(job_id)
        if not state:
            return _failure(f"Job {job_id} tidak ditemukan")
        return _success(state)
    except Exception as e:
        return _failure(f"Get job error: {str(e)}")

@tiktok_search_router.get("/api/search/deep/jobs/{job_id}/posts")
def get_deep_job_posts(job_id: str):
    try:
        if ENGINE_DIR not in sys.path:
            sys.path.insert(0, ENGINE_DIR)
        from tiktok_search_checkpoint import get_job_posts, get_job
        state = get_job(job_id)
        if not state:
            return _failure(f"Job {job_id} tidak ditemukan")
        posts = get_job_posts(job_id)
        return _success({"posts": posts, "total": len(posts)})
    except Exception as e:
        return _failure(f"Get posts error: {str(e)}")

@tiktok_search_router.post("/api/search/deep/jobs/{job_id}/cancel")
def cancel_deep_job(job_id: str):
    try:
        if ENGINE_DIR not in sys.path:
            sys.path.insert(0, ENGINE_DIR)
        from tiktok_search_checkpoint import cancel_job
        ok = cancel_job(job_id)
        return _success({"job_id": job_id, "cancelled": ok})
    except Exception as e:
        return _failure(f"Cancel error: {str(e)}")

@tiktok_search_router.delete("/api/search/deep/jobs/{job_id}")
def delete_deep_job(job_id: str):
    try:
        if ENGINE_DIR not in sys.path:
            sys.path.insert(0, ENGINE_DIR)
        from tiktok_search_checkpoint import delete_job
        ok = delete_job(job_id)
        return _success({"job_id": job_id, "deleted": ok})
    except Exception as e:
        return _failure(f"Delete error: {str(e)}")