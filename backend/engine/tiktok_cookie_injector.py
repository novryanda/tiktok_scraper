# tiktok_cookie_injector.py
import os
import json
import time
from typing import List, Dict, Optional

_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(_FILE_DIR, "session")
SESSION_FILE = os.path.join(SESSION_DIR, "tt_session.json")
REQUIRED_COOKIES = {"sessionid", "sessionid_ss", "ttwid"}  # perkuat requirement
PREFERRED_COOKIES = {"tt_csrf_token", "sid_tt", "tt_chain_token"}

_SAMESITE_MAP = {
    "no_restriction": "None",
    "unspecified": "Lax",
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
}

def load_raw_cookies() -> List[Dict]:
    if not os.path.exists(SESSION_FILE):
        raise FileNotFoundError(f"Session file tidak ditemukan: {SESSION_FILE}")
    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    cookies = data.get("cookies", [])
    if not cookies:
        raise ValueError("Tidak ada cookies dalam session file.")
    return cookies

def has_valid_session() -> bool:
    try:
        cookies = load_raw_cookies()
    except Exception:
        return False
    names = {c.get("name") for c in cookies}
    return REQUIRED_COOKIES.issubset(names)

def get_session_info() -> Dict:
    try:
        cookies = load_raw_cookies()
    except Exception as e:
        return {"valid": False, "error": str(e)}
    names = {c.get("name") for c in cookies}
    has_required = REQUIRED_COOKIES.issubset(names)
    return {
        "valid": has_required,
        "total_cookies": len(cookies),
        "cookie_names": sorted(names),
        "missing_required": list(REQUIRED_COOKIES - names),
    }

def to_playwright_cookies(cookies: List[Dict]) -> List[Dict]:
    out = []
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        domain = c.get("domain", ".tiktok.com")
        if domain and not domain.startswith(".") and "tiktok.com" in domain:
            domain = "." + domain.lstrip(".")
        pw = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": c.get("path", "/"),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", True)),
            "sameSite": _SAMESITE_MAP.get(str(c.get("sameSite", "unspecified")).lower(), "Lax"),
        }
        exp = c.get("expirationDate")
        pw["expires"] = float(exp) if exp is not None else -1
        out.append(pw)
    return out

def inject_cookies_sync(context) -> int:
    cookies = load_raw_cookies()
    pw_cookies = to_playwright_cookies(cookies)
    context.add_cookies(pw_cookies)
    print(f"🍪 Injected {len(pw_cookies)} cookies")
    return len(pw_cookies)

def save_session(cookies: List[Dict], username: str = "", note: str = "") -> str:
    os.makedirs(SESSION_DIR, exist_ok=True)
    data = {
        "platform": "tiktok",
        "username": username,
        "note": note,
        "saved_at": __import__("datetime").datetime.now().isoformat(),
        "cookies": cookies,
    }
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return SESSION_FILE

def delete_session() -> bool:
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
        return True
    return False