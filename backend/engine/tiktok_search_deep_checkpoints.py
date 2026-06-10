"""
tiktok_search_deep_endpoints.py
================================
Endpoint FastAPI untuk TikTok Deep Search dengan checkpoint backend.

Cara pakai di main.py (tiktok_api_server.py):
    from tiktok_search_deep_endpoints import tiktok_deep_search_router
    app.include_router(tiktok_deep_search_router)
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import traceback
from datetime import datetime

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiktok_search_checkpoint as sc

tiktok_deep_search_router = APIRouter(
    prefix="/api/search/deep",
    tags=["TikTok Deep Search"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ok(data: dict, msg: str = "OK"):
    return {
        "success":   True,
        "message":   msg,
        "timestamp": datetime.now().isoformat(),
        "data":      data,
    }

def _fail(msg: str):
    return {
        "success":   False,
        "message":   msg,
        "timestamp": datetime.now().isoformat(),
        "data":      {},
    }


# ── Models ─────────────────────────────────────────────────────────────────────

class TikTokDeepHashtagRequest(BaseModel):
    hashtag:              str
    max_related_hashtags: int  = 10
    max_posts_per_hashtag: int = 300


class TikTokDeepKeywordRequest(BaseModel):
    keyword:               str
    max_hashtags:          int = 5
    max_posts_per_hashtag: int = 150


# ── Endpoints ──────────────────────────────────────────────────────────────────

@tiktok_deep_search_router.post("/hashtag")
def tiktok_deep_search_hashtag(req: TikTokDeepHashtagRequest):
    """
    Mulai deep search hashtag TikTok.
    Scrape hashtag utama + expand ke related hashtags via discover.
    Return job_id untuk di-polling via GET /api/search/deep/jobs/{job_id}.
    """
    tag = req.hashtag.strip().lstrip("#").lower()
    if not tag:
        return _fail("Hashtag kosong")
    try:
        config = {
            "max_related_hashtags":  req.max_related_hashtags,
            "max_posts_per_hashtag": req.max_posts_per_hashtag,
        }
        job_id = sc.create_job("hashtag", tag, config)
        return _ok(
            {"job_id": job_id, "mode": "hashtag", "query": tag},
            f"TikTok deep search #{tag} dimulai (job: {job_id})",
        )
    except Exception as e:
        traceback.print_exc()
        return _fail(f"Gagal memulai job: {e}")


@tiktok_deep_search_router.post("/keyword")
def tiktok_deep_search_keyword(req: TikTokDeepKeywordRequest):
    """
    Mulai deep search keyword TikTok.
    Discover hashtag relevan → scrape tiap hashtag + direct Search API.
    Return job_id untuk di-polling.
    """
    kw = req.keyword.strip()
    if not kw:
        return _fail("Keyword kosong")
    try:
        config = {
            "max_hashtags":          req.max_hashtags,
            "max_posts_per_hashtag": req.max_posts_per_hashtag,
        }
        job_id = sc.create_job("keyword", kw, config)
        return _ok(
            {"job_id": job_id, "mode": "keyword", "query": kw},
            f"TikTok deep search '{kw}' dimulai (job: {job_id})",
        )
    except Exception as e:
        traceback.print_exc()
        return _fail(f"Gagal memulai job: {e}")


@tiktok_deep_search_router.get("/jobs")
def list_tiktok_deep_jobs():
    """Daftar semua TikTok deep search jobs (ringkasan tanpa posts)."""
    try:
        jobs = sc.list_all_jobs()
        return _ok({"jobs": jobs, "count": len(jobs)})
    except Exception as e:
        return _fail(str(e))


@tiktok_deep_search_router.get("/jobs/{job_id}")
def get_tiktok_deep_job(job_id: str):
    """
    Status + progres job.
    Saat masih running: total_fetched terupdate tiap batch.
    Saat completed: total_fetched = jumlah final.
    """
    state = sc.get_job(job_id)
    if not state:
        return _fail(f"Job '{job_id}' tidak ditemukan")
    return _ok(
        state,
        f"Job {job_id}: {state.get('status')} ({state.get('total_fetched', 0)} posts)",
    )


@tiktok_deep_search_router.get("/jobs/{job_id}/posts")
def get_tiktok_deep_job_posts(job_id: str):
    """
    Ambil HANYA posts dari job yang sudah completed.
    Endpoint terpisah agar tidak membebani polling status.
    """
    state = sc.get_job(job_id)
    if not state:
        return _fail(f"Job '{job_id}' tidak ditemukan")
    if state.get("status") != sc.JobStatus.COMPLETED:
        return _fail(f"Job belum selesai (status: {state.get('status')})")
    posts = sc.get_job_posts(job_id)
    return _ok({"posts": posts or [], "total": len(posts or [])})


@tiktok_deep_search_router.post("/jobs/{job_id}/cancel")
def cancel_tiktok_deep_job(job_id: str):
    """Cancel job yang sedang berjalan. Posts yang sudah terkumpul akan disimpan."""
    ok = sc.cancel_job(job_id)
    if ok:
        return _ok({"job_id": job_id, "cancelled": True}, "Job dibatalkan")
    return _fail(f"Job '{job_id}' tidak ditemukan atau sudah selesai")


@tiktok_deep_search_router.delete("/jobs/{job_id}")
def delete_tiktok_deep_job(job_id: str):
    """Hapus job beserta file state dan posts."""
    ok = sc.delete_job(job_id)
    if ok:
        return _ok({"job_id": job_id, "deleted": True}, "Job dihapus")
    return _fail(f"Job '{job_id}' tidak ditemukan")