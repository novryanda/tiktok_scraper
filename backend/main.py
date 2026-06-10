# ============================================================
# main.py — FastAPI Bridge untuk TikTok Scraper UI
# ============================================================
# v3.5.1 — FIX BOOLEAN INJECTION + ANTI-CAPTCHA IMPROVEMENTS
#   ✅ Fix: py_bool() untuk semua boolean injection
#   ✅ Fix: _job_scrape_video_unified parameter passing
#   ✅ Fix: _scrape_video_unified_engine f-string boolean
#   ✅ Tambah: auto session refresh sebelum scrape
#   ✅ Tambah: better error handling untuk CAPTCHA/timeout
#   ✅ Tambah: checkpoint scraping (batch bertahap)
#   ✅ Fix: _estimate_checkpoint_timeout lebih longgar (max 3 jam)
#   ✅ Import TikTokScraperV58 tetap dipakai
#   ✅ Tambah: Deep search endpoints (tiktok_search_endpoints)
# ============================================================

import os
import sys
import re
import json
import time
import uuid
import logging
import tempfile
import threading
import subprocess
from datetime import datetime
from typing import List, Optional, Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Integrasi Deep Search TikTok ───────────────────────────────────────────
# File tiktok_search_endpoints.py berada di folder yang sama dengan main.py
from tiktok_search_endpoints import tiktok_search_router

# `tiktok_search_checkpoint` di-import secara lazy oleh endpoint terkait,
# tapi kita tetap import di sini untuk keperluan health endpoint.
try:
    from engine.tiktok_search_checkpoint import (
        create_job   as _search_create_job,
        list_all_jobs as _search_list_jobs,
        get_job      as _search_get_job,
    )
except Exception:
    _search_create_job = None
    _search_list_jobs = None
    _search_get_job = None

# ════════════════════════════════════════════════════════════════
# KONFIGURASI
# ════════════════════════════════════════════════════════════════

_HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.environ.get("TIKTOK_ENGINE_DIR", os.path.join(_HERE, "engine"))

# Temporary scripts di folder sistem (bukan di backend)
SCRIPT_TMP_DIR = os.path.join(tempfile.gettempdir(), "tiktok_scraper_tmp")
os.makedirs(SCRIPT_TMP_DIR, exist_ok=True)

OUTPUT_VIDEO_DIR   = os.path.join(ENGINE_DIR, "output_tiktok")
OUTPUT_PROFILE_DIR = os.path.join(ENGINE_DIR, "output_tiktok_profiles")

VIDEO_TIMEOUT   = int(os.environ.get("TIKTOK_VIDEO_TIMEOUT", "900"))
PROFILE_TIMEOUT = int(os.environ.get("TIKTOK_PROFILE_TIMEOUT", "300"))
CHECKPOINT_TIMEOUT = int(os.environ.get("TIKTOK_CHECKPOINT_TIMEOUT", "3600"))

JOB_TTL_SECONDS = int(os.environ.get("TIKTOK_JOB_TTL", "3600"))

# ── Anti-CAPTCHA: nama class scraper yang aktif ──────────────
SCRAPER_CLASS = os.environ.get("TIKTOK_SCRAPER_CLASS", "TikTokScraperV58")

os.makedirs(OUTPUT_VIDEO_DIR, exist_ok=True)
os.makedirs(OUTPUT_PROFILE_DIR, exist_ok=True)


# ════════════════════════════════════════════════════════════════
# HELPER — PYTHON BOOL LITERAL (CRITICAL FIX)
# ════════════════════════════════════════════════════════════════

def py_bool(val: bool) -> str:
    """
    Konversi Python bool ke string literal Python yang aman untuk
    di-inject ke dalam f-string subprocess script.

    MASALAH:
        json.dumps(True)  → "true"   ← Python tidak kenal 'true' (itu JSON/JS)
        json.dumps(False) → "false"  ← sama, NameError di subprocess

    SOLUSI:
        py_bool(True)  → "True"   ← Python literal yang valid
        py_bool(False) → "False"  ← Python literal yang valid
    """
    return "True" if val else "False"


# ════════════════════════════════════════════════════════════════
# ERROR PATTERNS
# ════════════════════════════════════════════════════════════════

FATAL_ERROR_PATTERNS = [
    "page.content: unable to retrieve content",
    "unable to retrieve content because the page is navigating",
    "frame was detached",
    "navigation failed",
    "net::err_",
    "redirect login",
    "session expired",
    "403 access denied",
    "navigasi gagal setelah",
    "tidak bisa extract video_id",
    "gagal inject cookies",
    "captcha",
    "verifikasi",
    "verification",
]


def _is_fatal_error(error_msg: str) -> bool:
    if not error_msg:
        return False
    low = error_msg.lower()
    return any(pat in low for pat in FATAL_ERROR_PATTERNS)


def _is_valid_scrape_result(data: dict) -> tuple[bool, str]:
    engine_error = str(data.get("error", "") or "")
    has_video_id = bool(data.get("video_id", ""))
    has_username = bool(data.get("username", ""))
    comments_cnt = data.get("comments_count", 0) or len(data.get("comments", []))

    if engine_error and _is_fatal_error(engine_error):
        return False, f"Fatal error: {engine_error[:200]}"

    if engine_error and not has_video_id:
        return False, f"Error tanpa video_id: {engine_error[:200]}"

    if engine_error and comments_cnt == 0 and not has_video_id:
        return False, f"Error tanpa data: {engine_error[:200]}"

    if not has_video_id and not has_username:
        reason = engine_error if engine_error else (
            "Tidak dapat mengambil data — halaman gagal dimuat atau session expired"
        )
        return False, reason

    return True, ""


# ════════════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tiktok-bridge")


def dbg(msg: str):  log.info("🔍 " + msg)
def ok(msg: str):   log.info("✅ " + msg)
def warn(msg: str): log.warning("⚠️  " + msg)
def err(msg: str):  log.error("❌ " + msg)


# ════════════════════════════════════════════════════════════════
# FASTAPI APP
# ════════════════════════════════════════════════════════════════

app = FastAPI(title="TikTok Scraper Bridge", version="3.5.1")

# CORS: default allow all (*) untuk kemudahan dev/personal deploy.
# Override via env: CORS_ORIGINS="https://mydomain.com,https://other.com"
_cors_env = os.environ.get("CORS_ORIGINS", "*")
_cors_origins: list[str] = ["*"] if _cors_env.strip() == "*" else [
    o.strip() for o in _cors_env.split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register deep search router ──────────────────────────────────────────
app.include_router(tiktok_search_router)


# ════════════════════════════════════════════════════════════════
# RESPONSE HELPERS
# ════════════════════════════════════════════════════════════════

def success(data: Any, message: str = "Success") -> Dict:
    return {
        "success": True,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "data": data,
    }


# ════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ════════════════════════════════════════════════════════════════

class VideoScrapeRequest(BaseModel):
    url: str
    max_comments: int = Field(default=100, ge=1, le=500)


class BatchVideoScrapeRequest(BaseModel):
    urls: List[str]
    max_comments: int = Field(default=100, ge=1, le=500)


class ProfileScrapeRequest(BaseModel):
    username: str


class UnifiedVideoScrapeRequest(BaseModel):
    url: str
    max_comments: int = Field(default=100, ge=1, le=500)
    include_replies: bool = True
    max_replies_per_comment: int = Field(default=20, ge=0, le=200)
    scrape_likers: bool = True
    max_likers: int = Field(default=500, ge=0, le=2000)


class CheckpointVideoScrapeRequest(BaseModel):
    url: str
    batch_size: int = Field(default=300, ge=20, le=1000)
    max_total: int = Field(default=2000, ge=20, le=20000)
    sort_type: int = Field(default=0, ge=0, le=5)
    cooldown_min: int = Field(default=10, ge=0, le=300)
    cooldown_max: int = Field(default=20, ge=0, le=600)
    analyze_sentiment: bool = True


class CookieSaveRequest(BaseModel):
    cookies_json: str
    username: Optional[str] = ""


# ════════════════════════════════════════════════════════════════
# JOB STORE (in-memory, thread-safe)
# ════════════════════════════════════════════════════════════════

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()

_engine_lock = threading.Lock()


def _new_job(kind: str, label: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id":      job_id,
            "kind":        kind,
            "label":       label,
            "status":      "queued",
            "created_at":  datetime.now().isoformat(),
            "started_at":  None,
            "finished_at": None,
            "result":      None,
            "error":       None,
            "saved_file":  None,
        }
    return job_id


def _update_job(job_id: str, **fields):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def _cleanup_old_jobs():
    now = time.time()
    with _jobs_lock:
        to_del = []
        for jid, j in _jobs.items():
            if j["status"] in ("done", "error") and j.get("finished_at"):
                try:
                    fin = datetime.fromisoformat(j["finished_at"]).timestamp()
                    if now - fin > JOB_TTL_SECONDS:
                        to_del.append(jid)
                except Exception:
                    pass
        for jid in to_del:
            del _jobs[jid]


def _run_job(job_id: str, fn, *args):
    _cleanup_old_jobs()
    _update_job(job_id, status="running", started_at=datetime.now().isoformat())
    dbg(f"[job {job_id}] menunggu engine lock...")
    with _engine_lock:
        dbg(f"[job {job_id}] mulai eksekusi")
        try:
            result = fn(*args)
            saved = result.get("_saved_file") if isinstance(result, dict) else None
            _update_job(
                job_id,
                status="done",
                finished_at=datetime.now().isoformat(),
                result=result,
                saved_file=saved,
            )
            ok(f"[job {job_id}] selesai")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()[-1500:]
            _update_job(
                job_id,
                status="error",
                finished_at=datetime.now().isoformat(),
                error=str(e),
            )
            err(f"[job {job_id}] gagal: {e}\n{tb}")


def _launch_job(kind: str, label: str, fn, *args) -> str:
    job_id = _new_job(kind, label)
    t = threading.Thread(target=_run_job, args=(job_id, fn, *args), daemon=True)
    t.start()
    return job_id


# ════════════════════════════════════════════════════════════════
# SUBPROCESS RUNNER
# ════════════════════════════════════════════════════════════════

def _run_python(script: str, timeout: int, tag: str) -> dict:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8", dir=SCRIPT_TMP_DIR
    ) as f:
        f.write(script)
        script_path = f.name

    dbg(f"[{tag}] subprocess → {os.path.basename(script_path)} (timeout {timeout}s)")
    t0 = time.time()
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=ENGINE_DIR,
            encoding="utf-8",
            env=env,
        )

        elapsed = time.time() - t0
        dbg(f"[{tag}] selesai {elapsed:.1f}s (rc={proc.returncode})")

        if proc.stderr and proc.stderr.strip():
            for line in proc.stderr.strip().splitlines()[-60:]:
                log.info("   │ stderr │ " + line)

        if proc.stdout and proc.stdout.strip():
            for line in proc.stdout.strip().splitlines()[-30:]:
                log.info("   │ stdout │ " + line)

        if proc.returncode != 0:
            tail = (proc.stderr or "")[-2000:]

            if "no module named 'emoji'" in tail.lower():
                raise RuntimeError(
                    "Library 'emoji' belum terinstall. "
                    "Jalankan: pip install emoji\n"
                    f"(Original error: {tail[-300:]})"
                )

            raise RuntimeError(f"Engine exit {proc.returncode}.\n{tail}")

        for line in reversed((proc.stdout or "").strip().splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

        raise RuntimeError(
            "Tidak ada JSON valid dari engine. "
            "Pastikan engine mencetak json.dumps(result) di akhir."
        )
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def _save_json(data: dict, filename: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    fp = os.path.join(output_dir, filename)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    ok(f"💾 tersimpan: {filename}")
    return filename


# ════════════════════════════════════════════════════════════════
# TOP-5 LIKED COMMENTS HELPER
# ════════════════════════════════════════════════════════════════

def extract_top5_liked(result: dict) -> list:
    comments = result.get("comments", [])
    if not comments:
        ss = result.get("sentiment_summary", {})
        top = ss.get("top_liked_comments", [])
        return top[:5] if top else []

    sorted_comments = sorted(comments, key=lambda c: c.get("like_count", 0), reverse=True)

    top5 = []
    for rank, c in enumerate(sorted_comments[:5], start=1):
        top5.append({
            "rank":           rank,
            "username":       c.get("username", ""),
            "nickname":       c.get("nickname", ""),
            "text":           c.get("text", "")[:300],
            "like_count":     c.get("like_count", 0),
            "category":       c.get("category", "NEUTRAL"),
            "sentiment":      c.get("sentiment", ""),
            "is_hate_speech": c.get("is_hate_speech", False),
            "is_toxic":       c.get("is_toxic", False),
        })
    return top5


def enrich_result_with_top5(result: dict) -> dict:
    top5 = extract_top5_liked(result)
    result["top_5_liked_comments"] = top5
    ss = result.get("sentiment_summary")
    if isinstance(ss, dict):
        if not ss.get("top_liked_comments"):
            ss["top_liked_comments"] = top5
    return result


# ════════════════════════════════════════════════════════════════
# ENGINE WRAPPERS
# ════════════════════════════════════════════════════════════════

def _scrape_video_engine(url: str, max_comments: int) -> dict:
    """
    Jalankan scrape video (comments only) via subprocess.
    """
    script = f"""
import sys, json, os
sys.path.insert(0, r'{ENGINE_DIR}')

try:
    from tiktok_scraper import {SCRAPER_CLASS}
except ImportError as e:
    print(json.dumps({{"error": f"Import error: {{e}}", "success": False}}, ensure_ascii=False))
    sys.exit(1)

try:
    with {SCRAPER_CLASS}() as scraper:
        result = scraper.scrape_post_comments({json.dumps(url)}, {int(max_comments)})
        print(json.dumps(result, ensure_ascii=False, default=str))
except Exception as e:
    import traceback
    print(json.dumps({{
        "error": str(e),
        "traceback": traceback.format_exc()[-1000:],
        "success": False,
        "comments": [],
        "comments_count": 0,
    }}, ensure_ascii=False, default=str))
"""
    return _run_python(script, VIDEO_TIMEOUT, "video")


def _scrape_video_unified_engine(
    url: str,
    max_comments: int,
    include_replies: bool,
    max_replies_per_comment: int,
    scrape_likers: bool,
    max_likers: int,
) -> dict:
    """
    Jalankan scrape video unified (comments + likers) via subprocess.

    CRITICAL FIX v3.5.1: Boolean DI-INJECT sebagai Python literal (True/False),
    BUKAN json.dumps() yang menghasilkan "true"/"false" (JSON/JS lowercase)
    yang menyebabkan NameError: name 'true' is not defined di subprocess.
    """
    # PASTIKAN boolean benar-benar Python bool, bukan string
    include_replies_bool = bool(include_replies)
    scrape_likers_bool = bool(scrape_likers)

    script = f"""
import sys, json, os
sys.path.insert(0, r'{ENGINE_DIR}')

try:
    from tiktok_scraper import {SCRAPER_CLASS}
except ImportError as e:
    print(json.dumps({{"error": f"Import error: {{e}}", "success": False}}, ensure_ascii=False))
    sys.exit(1)

try:
    with {SCRAPER_CLASS}() as scraper:
        result = scraper.scrape_post_unified(
            {json.dumps(url)},
            {int(max_comments)},
            {py_bool(include_replies_bool)},
            {int(max_replies_per_comment)},
            {py_bool(scrape_likers_bool)},
            {int(max_likers)},
        )
        print(json.dumps(result, ensure_ascii=False, default=str))
except Exception as e:
    import traceback
    print(json.dumps({{
        "error": str(e),
        "traceback": traceback.format_exc()[-1000:],
        "success": False,
        "comments": [],
        "comments_count": 0,
        "likers": [],
        "likers_count": 0,
    }}, ensure_ascii=False, default=str))
"""
    return _run_python(script, VIDEO_TIMEOUT, "video-unified")


def _estimate_checkpoint_timeout(max_total: int, batch_size: int) -> int:
    """
    Estimasi timeout untuk checkpoint scraping.
    Formula lebih longgar mengakomodasi rate-limit, cooldown antar batch,
    dan kemungkinan CAPTCHA.
    """
    bs = max(1, batch_size)
    batches = max(1, -(-max_total // bs))      # ceil
    per_batch = (bs / 20) * 6 + 60             # paginasi + rate-limit + cooldown
    est = int(180 + batches * per_batch)
    # Minimal 15 menit, maksimal 3 jam
    return min(max(est, 900), 10800)


def _scrape_video_checkpoint_engine(
    url: str, batch_size: int, max_total: int, sort_type: int,
    cooldown_min: int, cooldown_max: int, analyze_sentiment: bool,
) -> dict:
    script = f"""
import sys, json, os
sys.path.insert(0, r'{ENGINE_DIR}')

try:
    from tiktok_scraper import {SCRAPER_CLASS}
except ImportError as e:
    print(json.dumps({{"error": f"Import error: {{e}}", "success": False}}, ensure_ascii=False))
    sys.exit(1)

try:
    with {SCRAPER_CLASS}() as scraper:
        result = scraper.scrape_all_checkpointed(
            {json.dumps(url)},
            batch_size={int(batch_size)},
            max_total={int(max_total)},
            analyze_sentiment={py_bool(analyze_sentiment)},
            sort_type={int(sort_type)},
            cooldown_min={int(cooldown_min)},
            cooldown_max={int(cooldown_max)},
        )
        print(json.dumps(result, ensure_ascii=False, default=str))
except Exception as e:
    import traceback
    print(json.dumps({{
        "error": str(e),
        "traceback": traceback.format_exc()[-1000:],
        "success": False,
        "comments": [],
        "comments_count": 0,
    }}, ensure_ascii=False, default=str))
"""
    timeout = _estimate_checkpoint_timeout(max_total, batch_size)
    return _run_python(script, timeout, "video-checkpoint")


def _scrape_profile_engine(username: str) -> dict:
    script = f"""
import sys, json
sys.path.insert(0, r'{ENGINE_DIR}')

try:
    from tiktok_profile_scraper import TikTokProfileScraper
except ImportError as e:
    print(json.dumps({{"error": f"Import error: {{e}}", "success": False}}, ensure_ascii=False))
    sys.exit(1)

try:
    with TikTokProfileScraper() as scraper:
        result = scraper.scrape_profile({json.dumps(username)})
        if result.get("success") and result.get("data"):
            try:
                scraper.save_tracking_data(result["data"])
            except Exception as te:
                print("TRACKING_WARN: " + str(te), file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, default=str))
except Exception as e:
    import traceback
    print(json.dumps({{
        "error": str(e),
        "traceback": traceback.format_exc()[-1000:],
        "success": False,
    }}, ensure_ascii=False, default=str))
"""
    return _run_python(script, PROFILE_TIMEOUT, "profile")


def check_session() -> dict:
    """
    Cek apakah session TikTok valid: periksa tt_session.json (cookie mode)
    ATAU chrome persistent profile.
    """
    script = f"""
import sys, json, os
sys.path.insert(0, r'{ENGINE_DIR}')

result = {{
    "valid": False,
    "mode": "none",
    "cookie_file_exists": False,
    "chrome_profile_exists": False,
    "info": {{}}
}}

# --- cek cookie injector ---
try:
    from tiktok_cookie_injector import has_valid_session, get_session_info
    cookie_valid = has_valid_session()
    result["cookie_file_exists"] = cookie_valid
    if cookie_valid:
        result["valid"] = True
        result["mode"] = "cookie_injection"
        try:
            result["info"] = get_session_info()
        except Exception:
            result["info"] = {{}}
except Exception as e:
    result["cookie_injector_error"] = str(e)

# --- cek chrome profile (fallback) ---
chrome_profile = os.path.join(os.getcwd(), "tiktok_chrome_real_profile")
profile_exists = os.path.exists(chrome_profile) and bool(os.listdir(chrome_profile))
result["chrome_profile_exists"] = profile_exists

if not result["valid"] and profile_exists:
    result["valid"] = True
    result["mode"] = "chrome_profile"

print(json.dumps(result, ensure_ascii=False, default=str))
"""
    return _run_python(script, 30, "session")


# ════════════════════════════════════════════════════════════════
# JOB BODIES
# ════════════════════════════════════════════════════════════════

def _job_scrape_video(url: str, max_comments: int) -> dict:
    result = _scrape_video_engine(url, max_comments)

    is_valid, reason = _is_valid_scrape_result(result)
    if not is_valid:
        raise RuntimeError(f"Engine error: {reason}")

    result = enrich_result_with_top5(result)
    fn = f"api_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    _save_json(result, fn, OUTPUT_VIDEO_DIR)
    result["_saved_file"] = fn
    return result


def _job_scrape_video_unified(
    url: str,
    max_comments: int,
    include_replies: bool,
    max_replies_per_comment: int,
    scrape_likers: bool,
    max_likers: int,
) -> dict:
    """
    FIX v3.5.1: Pastikan parameter boolean diteruskan sebagai Python bool,
    bukan string. Nilai sudah di-validate oleh Pydantic di endpoint,
    jadi aman langsung dipakai.
    """
    # EXPLICIT CAST ke bool untuk keamanan
    result = _scrape_video_unified_engine(
        url,
        max_comments,
        bool(include_replies),        # ← EXPLICIT bool
        max_replies_per_comment,
        bool(scrape_likers),          # ← EXPLICIT bool
        max_likers,
    )

    is_valid, reason = _is_valid_scrape_result(result)
    if not is_valid:
        raise RuntimeError(f"Engine error: {reason}")

    result = enrich_result_with_top5(result)
    fn = f"api_video_unified_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    _save_json(result, fn, OUTPUT_VIDEO_DIR)
    result["_saved_file"] = fn
    return result


def _job_scrape_video_checkpoint(
    url: str, batch_size: int, max_total: int, sort_type: int,
    cooldown_min: int, cooldown_max: int, analyze_sentiment: bool,
) -> dict:
    result = _scrape_video_checkpoint_engine(
        url, batch_size, max_total, sort_type,
        cooldown_min, cooldown_max, bool(analyze_sentiment),
    )
    is_valid, reason = _is_valid_scrape_result(result)
    if not is_valid:
        raise RuntimeError(f"Engine error: {reason}")
    result = enrich_result_with_top5(result)
    fn = f"api_video_checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    _save_json(result, fn, OUTPUT_VIDEO_DIR)
    result["_saved_file"] = fn
    return result


def _job_scrape_batch(urls: list, max_comments: int) -> dict:
    results = []

    for i, url in enumerate(urls, 1):
        dbg(f"[batch {i}/{len(urls)}] {url[:60]}")

        data = None
        final_error = None
        is_success = False

        for attempt in range(1, 3):
            try:
                raw_data = _scrape_video_engine(url, max_comments)
                is_valid, reason = _is_valid_scrape_result(raw_data)

                if is_valid:
                    data = enrich_result_with_top5(raw_data)
                    is_success = True
                    final_error = None
                    break
                else:
                    final_error = reason
                    engine_err = str(raw_data.get("error", "") or "").lower()

                    is_nav_error = (
                        "navigating" in engine_err
                        or "unable to retrieve content" in engine_err
                        or "frame was detached" in engine_err
                    )

                    if is_nav_error and attempt < 2:
                        warn(f"[batch {i}] Navigation error attempt {attempt}, retry dalam 15s...")
                        time.sleep(15)
                        continue
                    else:
                        warn(f"[batch {i}] Gagal: {reason[:100]}")
                        break

            except Exception as e:
                final_error = str(e)
                warn(f"[batch {i}] Exception attempt {attempt}: {e}")
                if attempt < 2:
                    time.sleep(10)
                    continue
                break

        status_icon = "✅" if is_success else "❌"
        ok(f"[batch {i}] {status_icon} {url[:50]}")

        results.append({
            "url":     url,
            "success": is_success,
            "data":    data if is_success else None,
            "error":   final_error if not is_success else None,
        })

        # ── jeda antar video dalam batch untuk hindari CAPTCHA ──
        if i < len(urls):
            inter_delay = int(os.environ.get("TIKTOK_BATCH_COOLDOWN_MIN", "60"))
            dbg(f"[batch] jeda {inter_delay}s antar video...")
            time.sleep(inter_delay)

    summary = {
        "total":   len(urls),
        "success": sum(1 for r in results if r["success"]),
        "failed":  sum(1 for r in results if not r["success"]),
        "results": results,
    }
    fn = f"api_batch_videos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    _save_json(summary, fn, OUTPUT_VIDEO_DIR)
    summary["_saved_file"] = fn
    return summary


def _job_scrape_profile(username: str) -> dict:
    _stripped = username.strip()
    _m = re.search(r'tiktok\.com/@([^/?&#\s]+)', _stripped, re.IGNORECASE)
    if _m:
        _stripped = _m.group(1)
        dbg(f"Profile: URL → username extracted: {_stripped}")
    elif _stripped.startswith('@'):
        _stripped = _stripped.lstrip('@')
        dbg(f"Profile: @ stripped → {_stripped}")

    result = _scrape_profile_engine(_stripped)
    uname = (result.get("data") or {}).get("username") or result.get("username", "user")
    fn = f"api_profile_{uname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    _save_json(result, fn, OUTPUT_PROFILE_DIR)
    result["_saved_file"] = fn
    return result


# ════════════════════════════════════════════════════════════════
# ENDPOINTS — JOB SYSTEM
# ════════════════════════════════════════════════════════════════

@app.get("/api/jobs")
def list_jobs():
    _cleanup_old_jobs()
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)
        light = [{
            "job_id":      j["job_id"],
            "kind":        j["kind"],
            "label":       j["label"],
            "status":      j["status"],
            "created_at":  j["created_at"],
            "started_at":  j["started_at"],
            "finished_at": j["finished_at"],
            "saved_file":  j["saved_file"],
            "error":       j["error"],
        } for j in jobs]
    return success({"jobs": light, "count": len(light)})


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    j = _get_job(job_id)
    if not j:
        raise HTTPException(404, "Job tidak ditemukan (mungkin sudah kedaluwarsa)")
    return success(j)


# ════════════════════════════════════════════════════════════════
# ENDPOINTS — HEALTH & SESSION
# ════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    video_files = [f for f in os.listdir(OUTPUT_VIDEO_DIR) if f.endswith(".json")] \
        if os.path.isdir(OUTPUT_VIDEO_DIR) else []
    profile_files = [f for f in os.listdir(OUTPUT_PROFILE_DIR) if f.endswith(".json")] \
        if os.path.isdir(OUTPUT_PROFILE_DIR) else []

    # cek file engine search
    search_engine_files = {
        "tiktok_search_scraper.py":    os.path.exists(os.path.join(ENGINE_DIR, "tiktok_search_scraper.py")),
        "tiktok_search_checkpoint.py": os.path.exists(os.path.join(ENGINE_DIR, "tiktok_search_checkpoint.py")),
    }

    engine_files = {
        "tiktok_scraper.py":         os.path.exists(os.path.join(ENGINE_DIR, "tiktok_scraper.py")),
        "tiktok_profile_scraper.py": os.path.exists(os.path.join(ENGINE_DIR, "tiktok_profile_scraper.py")),
        "tiktok_cookie_injector.py": os.path.exists(os.path.join(ENGINE_DIR, "tiktok_cookie_injector.py")),
        "sentiment_analyzer_v2.py":  os.path.exists(os.path.join(ENGINE_DIR, "sentiment_analyzer_v2.py")),
        **search_engine_files,
    }

    # hitung active deep-search jobs
    try:
        deep_jobs = _search_list_jobs()
        active_deep = sum(1 for j in deep_jobs if j.get("status") in ("running", "queued"))
    except Exception:
        active_deep = 0

    return success({
        "status":             "running",
        "version":            "3.5.1",
        "platform":           "tiktok",
        "scraper_class":      SCRAPER_CLASS,
        "engine_dir":         ENGINE_DIR,
        "script_tmp_dir":     SCRIPT_TMP_DIR,
        "engine_files":       engine_files,
        "output_video_dir":   OUTPUT_VIDEO_DIR,
        "output_profile_dir": OUTPUT_PROFILE_DIR,
        "video_files":        len(video_files),
        "profile_files":      len(profile_files),
        "active_jobs":        sum(1 for j in _jobs.values() if j["status"] in ("queued", "running")),
        "active_deep_search_jobs": active_deep,
    }, "TikTok bridge healthy")


@app.get("/api/session")
def session_status():
    try:
        result = check_session()
        return success(result, "Session checked")
    except Exception as e:
        err(f"session check gagal: {e}")
        return success({"valid": False, "error": str(e)}, "Session check failed")


# ════════════════════════════════════════════════════════════════
# ENDPOINTS — SCRAPE
# ════════════════════════════════════════════════════════════════

@app.post("/api/scrape/video")
def api_scrape_video(req: VideoScrapeRequest):
    dbg(f"POST /api/scrape/video url={req.url[:60]} max={req.max_comments}")
    job_id = _launch_job("single", req.url, _job_scrape_video, req.url, req.max_comments)
    return success({"job_id": job_id, "status": "queued"}, "Scrape video dimulai")


@app.post("/api/scrape/video/unified")
def api_scrape_video_unified(req: UnifiedVideoScrapeRequest):
    dbg(
        f"POST /api/scrape/video/unified url={req.url[:60]} max={req.max_comments} "
        f"replies={req.include_replies} max_replies={req.max_replies_per_comment} "
        f"likers={req.scrape_likers} max_likers={req.max_likers}"
    )
    job_id = _launch_job(
        "unified",
        req.url,
        _job_scrape_video_unified,
        req.url,
        req.max_comments,
        bool(req.include_replies),
        req.max_replies_per_comment,
        bool(req.scrape_likers),
        req.max_likers,
    )
    return success({"job_id": job_id, "status": "queued"}, "Scrape video unified dimulai")


@app.post("/api/scrape/video/checkpoint")
def api_scrape_video_checkpoint(req: CheckpointVideoScrapeRequest):
    dbg(f"POST /api/scrape/video/checkpoint url={req.url[:60]} batch={req.batch_size} total={req.max_total}")
    job_id = _launch_job(
        "checkpoint", req.url, _job_scrape_video_checkpoint,
        req.url, req.batch_size, req.max_total, req.sort_type,
        req.cooldown_min, req.cooldown_max, bool(req.analyze_sentiment),
    )
    return success({"job_id": job_id, "status": "queued"}, "Scrape checkpoint dimulai")


@app.post("/api/scrape/videos/batch")
def api_scrape_videos_batch(req: BatchVideoScrapeRequest):
    urls = [u.strip() for u in req.urls if u.strip()]
    if not urls:
        raise HTTPException(400, "Daftar URL kosong")
    dbg(f"POST /api/scrape/videos/batch n={len(urls)} max={req.max_comments}")
    job_id = _launch_job("batch", f"{len(urls)} URL", _job_scrape_batch, urls, req.max_comments)
    return success({"job_id": job_id, "status": "queued"}, "Scrape batch dimulai")


@app.post("/api/scrape/profile")
def api_scrape_profile(req: ProfileScrapeRequest):
    dbg(f"POST /api/scrape/profile username={req.username}")
    job_id = _launch_job("profile", req.username, _job_scrape_profile, req.username)
    return success({"job_id": job_id, "status": "queued"}, "Scrape profil dimulai")


# ════════════════════════════════════════════════════════════════
# ENDPOINTS — TOP 5 LIKED
# ════════════════════════════════════════════════════════════════

@app.get("/api/scrape/video/top5")
def get_top5_from_latest():
    import glob
    pattern = os.path.join(OUTPUT_VIDEO_DIR, "api_video_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        raise HTTPException(404, "Belum ada hasil scrape video")
    with open(files[0], "r", encoding="utf-8") as f:
        data = json.load(f)
    top5 = data.get("top_5_liked_comments") or extract_top5_liked(data)
    return success({
        "file":                  os.path.basename(files[0]),
        "video_id":              data.get("video_id", ""),
        "username":              data.get("username", ""),
        "top_5_liked_comments":  top5,
    }, "Top 5 liked comments")


@app.get("/api/scrape/video/top5/{filename}")
def get_top5_from_file(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Nama file tidak valid")
    fp = os.path.join(OUTPUT_VIDEO_DIR, filename)
    if not os.path.isfile(fp):
        raise HTTPException(404, f"File {filename} tidak ditemukan")
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    top5 = data.get("top_5_liked_comments") or extract_top5_liked(data)
    return success({
        "file":                 filename,
        "video_id":             data.get("video_id", ""),
        "username":             data.get("username", ""),
        "top_5_liked_comments": top5,
    }, "Top 5 liked comments")


# ════════════════════════════════════════════════════════════════
# ENDPOINTS — OUTPUT FILES
# ════════════════════════════════════════════════════════════════

@app.get("/api/files")
def list_files():
    files = []
    for d, kind in ((OUTPUT_VIDEO_DIR, "video"), (OUTPUT_PROFILE_DIR, "profile")):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not name.endswith(".json"):
                continue
            fp = os.path.join(d, name)
            try:
                st = os.stat(fp)
                files.append({
                    "name":     name,
                    "kind":     kind,
                    "size":     st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                })
            except OSError:
                pass
    files.sort(key=lambda x: x["modified"], reverse=True)
    return success({"files": files, "count": len(files)})


@app.get("/api/files/{filename}")
def get_file(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Nama file tidak valid")
    for d in (OUTPUT_VIDEO_DIR, OUTPUT_PROFILE_DIR):
        fp = os.path.join(d, filename)
        if os.path.isfile(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)
    raise HTTPException(404, "File tidak ditemukan")


# ════════════════════════════════════════════════════════════════
# ENDPOINTS — PROFILES LIST
# ════════════════════════════════════════════════════════════════

@app.get("/api/profiles")
def list_profiles():
    tracking_file = os.path.join(OUTPUT_PROFILE_DIR, "growth_tracking.json")
    users = []
    if os.path.isfile(tracking_file):
        try:
            with open(tracking_file, "r", encoding="utf-8") as f:
                tracking = json.load(f)
            for username, data in tracking.items():
                history = data.get("history", [])
                latest = history[-1] if history else {}
                users.append({
                    "username":     username,
                    "followers":    latest.get("followers", 0),
                    "following":    latest.get("following", 0),
                    "total_likes":  latest.get("total_likes", 0),
                    "total_videos": latest.get("total_videos", 0),
                    "data_points":  len(history),
                    "last_tracked": data.get("last_tracked", ""),
                })
            users.sort(key=lambda x: x.get("last_tracked", ""), reverse=True)
        except Exception as e:
            warn(f"baca tracking gagal: {e}")
    return success({"users": users, "count": len(users)})


# ════════════════════════════════════════════════════════════════
# ENDPOINTS — ANALYTICS
# ════════════════════════════════════════════════════════════════

@app.get("/api/analytics")
def get_analytics():
    import glob

    videos = []
    total_comments = 0
    agg = {"positive": 0, "negative": 0, "neutral": 0, "humor": 0, "toxic": 0, "hate": 0}

    video_pattern = os.path.join(OUTPUT_VIDEO_DIR, "*.json")
    for fp in glob.glob(video_pattern):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict) and data.get("video_id"):
                videos.append(data)
                total_comments += data.get("comments_count", 0)
                ss = data.get("sentiment_summary")
                if ss:
                    agg["positive"] += ss.get("positive_count", 0)
                    agg["negative"] += ss.get("negative_count", 0)
                    agg["neutral"]  += ss.get("neutral_count", 0)
                    agg["humor"]    += ss.get("humor_count", 0)
                    agg["toxic"]    += ss.get("toxic_count", 0)
                    agg["hate"]     += ss.get("hate_speech_count", 0)

            elif isinstance(data, dict) and isinstance(data.get("results"), list):
                for r in data["results"]:
                    if r.get("success") and r.get("data"):
                        v = r["data"]
                        videos.append(v)
                        total_comments += v.get("comments_count", 0)
                        ss = v.get("sentiment_summary")
                        if ss:
                            agg["positive"] += ss.get("positive_count", 0)
                            agg["negative"] += ss.get("negative_count", 0)
                            agg["neutral"]  += ss.get("neutral_count", 0)
                            agg["humor"]    += ss.get("humor_count", 0)
                            agg["toxic"]    += ss.get("toxic_count", 0)
                            agg["hate"]     += ss.get("hate_speech_count", 0)
        except Exception as e:
            warn(f"skip file {os.path.basename(fp)}: {e}")

    videos.sort(key=lambda x: x.get("comments_count", 0), reverse=True)
    positive_pct = round(agg["positive"] / total_comments * 100) if total_comments > 0 else 0

    return success({
        "total_videos":        len(videos),
        "total_comments":      total_comments,
        "sentiment":           agg,
        "positive_percentage": positive_pct,
        "top_videos":          videos[:20],
    }, "Analytics loaded")


# ════════════════════════════════════════════════════════════════
# ENDPOINTS — COOKIES
# ════════════════════════════════════════════════════════════════

SESSION_DIR  = os.path.join(ENGINE_DIR, "session")
SESSION_FILE = os.path.join(SESSION_DIR, "tt_session.json")
REQUIRED_COOKIES = {"sessionid"}


@app.post("/api/cookies")
def save_cookies(req: CookieSaveRequest):
    dbg("POST /api/cookies")
    raw = (req.cookies_json or "").strip()
    if not raw:
        raise HTTPException(400, "Cookie JSON kosong")

    try:
        cookies = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"JSON tidak valid: {e}")

    if not isinstance(cookies, list) or len(cookies) == 0:
        raise HTTPException(400, "Harus array cookies dari Cookie-Editor")

    names = {c.get("name", "") for c in cookies if isinstance(c, dict)}
    missing = REQUIRED_COOKIES - names
    if missing:
        raise HTTPException(400, f"Cookie wajib tidak ada: {', '.join(missing)}")

    tiktok_cookies = [
        c for c in cookies
        if isinstance(c, dict) and "tiktok.com" in str(c.get("domain", "")).lower()
    ] or cookies

    os.makedirs(SESSION_DIR, exist_ok=True)
    payload = {
        "platform":  "tiktok",
        "username":  (req.username or "").lstrip("@"),
        "note":      "saved_from_ui_settings",
        "saved_at":  datetime.now().isoformat(),
        "cookies":   tiktok_cookies,
    }
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    ok(f"🍪 {len(tiktok_cookies)} cookies tersimpan")
    return success({
        "saved":          True,
        "total_cookies":  len(tiktok_cookies),
        "has_sessionid":  "sessionid" in names,
    }, f"{len(tiktok_cookies)} cookies tersimpan")


@app.get("/api/cookies")
def cookies_status():
    if not os.path.isfile(SESSION_FILE):
        return success({"valid": False, "exists": False}, "Belum ada cookie")
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        names = {c.get("name") for c in cookies}

        sessionid_expiry = None
        for c in cookies:
            if c.get("name") == "sessionid":
                sessionid_expiry = c.get("expirationDate") or c.get("expires")
                break

        return success({
            "valid":              REQUIRED_COOKIES.issubset(names),
            "exists":             True,
            "total_cookies":      len(cookies),
            "username":           data.get("username", ""),
            "saved_at":           data.get("saved_at", ""),
            "sessionid_expiry":   sessionid_expiry,
        }, "Cookie ditemukan")
    except Exception as e:
        return success({"valid": False, "exists": True, "error": str(e)}, "Cookie rusak")


@app.delete("/api/cookies")
def delete_cookies():
    if os.path.isfile(SESSION_FILE):
        os.remove(SESSION_FILE)
        return success({"deleted": True}, "Cookie dihapus")
    return success({"deleted": False}, "Tidak ada cookie")


# ════════════════════════════════════════════════════════════════
# ENDPOINT — SESSION REFRESH
# ════════════════════════════════════════════════════════════════

@app.post("/api/session/refresh")
def refresh_session():
    """
    Paksa re-inject cookies dari tt_session.json ke persistent chrome profile.
    """
    script = f"""
import sys, json, os
sys.path.insert(0, r'{ENGINE_DIR}')

try:
    from tiktok_cookie_injector import has_valid_session, get_session_info
    if not has_valid_session():
        print(json.dumps({{"success": False, "error": "tt_session.json tidak ada atau tidak valid"}}))
        sys.exit(0)

    from playwright.sync_api import sync_playwright
    persistent_profile = os.path.join(os.getcwd(), "tiktok_cookie_profile_persistent")
    os.makedirs(persistent_profile, exist_ok=True)

    from tiktok_cookie_injector import inject_cookies_sync

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            persistent_profile,
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            locale="id-ID",
            timezone_id="Asia/Jakarta",
        )
        n = inject_cookies_sync(ctx)
        ctx.close()

    info = get_session_info()
    print(json.dumps({{"success": True, "injected_cookies": n, "info": info}}, default=str))
except Exception as e:
    import traceback
    print(json.dumps({{"success": False, "error": str(e), "traceback": traceback.format_exc()[-500:]}}))
"""
    try:
        result = _run_python(script, 60, "session-refresh")
        if result.get("success"):
            ok("Session refresh berhasil")
            return success(result, "Cookie berhasil di-inject ulang ke persistent profile")
        else:
            return success(result, "Session refresh gagal — lihat field error")
    except Exception as e:
        err(f"Session refresh exception: {e}")
        raise HTTPException(500, f"Session refresh gagal: {e}")


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    print("=" * 64)
    print("  TIKTOK SCRAPER BRIDGE v3.5.1 (FastAPI + Job System + Checkpoint + Deep Search)")
    print(f"  Engine dir    : {ENGINE_DIR}")
    print(f"  Scraper class : {SCRAPER_CLASS}")
    print(f"  Tmp scripts   : {SCRIPT_TMP_DIR}")
    print(f"  Scraper OK    : {os.path.exists(os.path.join(ENGINE_DIR, 'tiktok_scraper.py'))}")
    print(f"  Session OK    : {os.path.exists(SESSION_FILE)}")
    print("  URL           : http://localhost:8001")
    print("  Docs          : http://localhost:8001/docs")
    print("=" * 64)

    use_reload = os.environ.get("UVICORN_RELOAD", "False").lower() == "true"

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=use_reload,
        reload_dirs=[_HERE] if use_reload else None,
    )