# ============================================================
# TIKTOK SLANG EXTENSION untuk SentimentAnalyzerV2
# ============================================================
# Modul ini meng-extend kamus di sentiment_analyzer_v2.py dengan
# slang khas TikTok Indonesia (FYP-era, Gen Z, brainrot, dll).
#
# CARA PAKAI:
#   from sentiment_analyzer_v2 import SentimentAnalyzerV2
#   from tiktok_slang_extension import patch_analyzer_for_tiktok
#
#   analyzer = SentimentAnalyzerV2(mode="hybrid")
#   patch_analyzer_for_tiktok(analyzer)   # mutate kamus in-place
#
# Yang ditambahkan:
#   - Slang TikTok positif: "slay", "real", "core", "fr fr", "no cap"...
#   - Slang TikTok negatif: "cringe", "ick", "mid", "flop", "L"...
#   - Hate slang Gen Z: "ratio", "skill issue" (context-dependent, hati2)
#   - Sarcasm pattern TikTok: "POV:", "tell me you X without telling me"
#   - Wellwish TikTok: "rooting for you", "we love to see it"
# ============================================================

import re

# ---------- POSITIVE TIKTOK ----------
TIKTOK_POSITIVE = {
    # Gen-Z affirmation
    "slay", "slayed", "slaying", "slayy", "slayyy",
    "real", "fr", "fr fr", "frfr", "no cap", "nocap",
    "based", "valid", "iconic", "legendary", "goated", "goat",
    "ate", "ate that", "served", "serving",
    "vibes", "vibey", "good vibes", "main character",
    "bestie", "queen", "king", "icon",
    "core memory", "obsessed", "im obsessed",
    "literally perfect", "chef kiss",
    # Indo TikTok positif
    "auto fyp", "fyp dong", "masuk fyp",
    "wajib coba", "wajib nonton", "skor 10",
    "gokil parah", "sumpah keren", "edit nya gilaa",
    "kreatif banget", "bikin nagih", "viral nih", "trending",
    "kontennya bagus", "anjay bagus", "anjay keren",
    "konten daging", "konten berbobot",
    # Apresiasi
    "respect", "salute", "hormat", "applause", "tepuk tangan",
    "we stan", "stan", "stan loyal",
    # Emoji-words (people type these literally)
    "fire", "lit", "lit banget", "🔥", "hyped",
}

# ---------- NEGATIVE TIKTOK ----------
TIKTOK_NEGATIVE = {
    # Gen-Z negative
    "cringe", "cringy", "cringe banget", "cringeworthy",
    "ick", "the ick", "kasih ick",
    "mid", "mid af", "average banget",
    "flop", "flopped", "flop era",
    "boring", "snooze", "yawn", "ngantukin",
    "tone deaf", "tonedeaf",
    "delulu", "delusional",
    "cap", "thats cap", "kebohongan",
    "yikes", "oof", "rip",
    "akhlak", "akhlak tercela",  # netizen Indo style
    # Indo TikTok negatif
    "gak fyp gak fyp", "kontennya garing", "garing banget",
    "ngapain sih", "buang waktu", "buang kuota",
    "skip skip", "next aja", "auto skip",
    "edit nya kasar", "kontennya gak jelas",
    "konten sampah", "konten kosong", "konten micin",
    "dislike", "down vote", "report",
    # Pop-criticism
    "overrated", "overhyped", "over-rated",
    "drama doang", "settingan", "drama settingan",
    "pencitraan doang", "pansos", "panjat sosial",
    "clout chaser", "cari clout",
    "wannabe", "kw super", "kw aja",
    "biasa aja", "ga ada feel", "ga relatable",
}

# ---------- HATE / SLUR TIKTOK ----------
# HATI-HATI: "ratio" & "L" itu konteks-dependent. Kita tetap mark sebagai
# negative TIKTOK (bukan hate), karena sebenarnya cuma diss bukan slur.
# Kita TAMBAH ke negative set, BUKAN ke hate set.
TIKTOK_HATE = {
    # Slur tambahan Indo TikTok yang sering muncul (tetap mark hate)
    "anjeng", "anjeeng", "anjenk",
    "bgsd", "bgsdt",
    "tlol", "tll", "tololll",
    "kontolodon",
    "ngehe", "ngehek",
    # Slur EN yang sering muncul di komen TikTok Indo
    "shit", "fuck", "fucking", "fckin", "f*ck", "f*cking",
    "stfu", "kys",  # "kill yourself" — toxic banget
    "wtf", "wth",   # umumnya bukan hate, tapi escalator ke toxic
}

# ---------- TOXIC TIKTOK ----------
TIKTOK_TOXIC = {
    "ratio", "ratio ed", "ratio plus L",
    "L", "you took the L", "ambil L", "you fell off",
    "fell off", "udah ga relevan",
    "skill issue", "git gud", "git good",
    "touch grass", "kena nyata", "hidup di realita",
    "ok boomer", "ok zoomer",
    "go cry about it", "nangis aja sana",
    "stay mad", "tetap marah aja",
    "copium", "hopium", "kopium",
    "wibu kacau", "wibu akut", "wibu sampah",
    "halu akut", "halu tingkat dewa",
    "kebanyakan tiktok",
    "ga ada otak", "otak udang",
}

# ---------- HUMOR TIKTOK ----------
TIKTOK_HUMOR = {
    "lmaooo", "lmaoo", "lmfao", "lmfaoo",
    "i cant", "im dead", "im dying", "im deceased",
    "im wheezing", "wheezing",
    "ngakak guling", "ngakak parah", "ngakak banget",
    "wkkwkw", "wkkwk", "ckckck", "cmiwww",
    "kocag", "kocag bgt",
    "anjirr lucu", "anjirrr",
    "speechless", "no words",
    "hilarious", "halu lucu",
    "auto ngakak", "ngakak auto",
    "💀", "☠️",  # death emoji jadi humor di TikTok
    "ded", "im ded",
}

# ---------- SARCASM PATTERN TIKTOK ----------
# Pattern khas TikTok: POV format, "tell me", "no one", "the way"
TIKTOK_SARCASM_PATTERNS = [
    # "POV: when X happens" — biasanya ironis kalau diakhiri 💀😭🙃
    re.compile(r'\bpov\s*:.*[💀😭🙃😬]', re.I),
    # "tell me you X without telling me you X" — sindiran
    re.compile(r'\btell\s+me\s+you\b.*\bwithout\s+telling\s+me\b', re.I),
    # "the way X" + emoji negatif → sarkasme observatif
    re.compile(r'\bthe\s+way\b.*[💀😭🙃]', re.I),
    # "no one:" / "literally no one:" — setup sarkasme
    re.compile(r'\b(no\s+one|literally\s+no\s+one)\s*:', re.I),
    # "ratio + L + Y" combo (diss combo TikTok klasik)
    re.compile(r'\bratio\b.*\bL\b', re.I),
    # "we love a X" + konteks negatif
    re.compile(r'\bwe\s+love\s+(a|to\s+see)\b.*\?', re.I),
    # "this aint it chief" — sindiran halus
    re.compile(r"\bthis\s+ain'?t\s+it\b", re.I),
    # Indo: "wajar sih kalo X" + tanda tanya
    re.compile(r'\bwajar\s+sih\s+kalo\b.*\?', re.I),
    # Indo: "konten daging" sarkasme — kalau diikuti emoji negatif
    re.compile(r'\b(konten\s+daging|konten\s+berbobot)\b.*[💀😭🙃]', re.I),
    # "ya gimana ya" — ekspresi pasrah sarkastik Indo
    re.compile(r'\bya\s+gimana\s+ya\b', re.I),
    # "auto fyp" + emoji negatif → sarkasme
    re.compile(r'\bauto\s+fyp\b.*[💀🙃😭]', re.I),
    # "pinter banget" + emoji 💀😂 → sarkasme
    re.compile(r'\bpinter\s+(banget|sekali|amat)\b.*[💀😂🤣]', re.I),
    # "next presiden" / "next menteri" — sarkasme politik Gen Z
    re.compile(r'\bnext\s+(presiden|menteri|gubernur|walikota)\b', re.I),
]

# ---------- WELLWISH PATTERN TIKTOK ----------
TIKTOK_WELLWISH_PATTERNS = [
    re.compile(r"\brooting\s+for\s+you\b", re.I),
    re.compile(r"\bwe\s+love\s+to\s+see\s+it\b(?!.*\?)", re.I),
    re.compile(r"\bso\s+proud\s+of\b", re.I),
    re.compile(r"\byou\s+deserve\s+(it|this|everything)\b", re.I),
    re.compile(r"\bbangga\s+banget\b", re.I),
    re.compile(r"\bsemangat\s+terus\b", re.I),
    re.compile(r"\bjangan\s+menyerah\b", re.I),
]


def patch_analyzer_for_tiktok(analyzer) -> None:
    """
    Mutate kamus dan pattern di SentimentAnalyzerV2 instance
    agar paham slang TikTok.

    DIPANGGIL SEKALI saat init scraper.
    """
    # Lazy-import biar nggak circular
    from sentiment_analyzer_v2 import (
        POSITIVE_ID,
        NEGATIVE_ID,
        HATE_WORDS_ID,
        TOXIC_WORDS_ID,
        HUMOR_WORDS_ID,
        SARCASM_PATTERNS,
        WELLWISH_PATTERNS,
    )

    # Extend kamus (set operation — duplicate auto-handled)
    POSITIVE_ID.update(TIKTOK_POSITIVE)
    NEGATIVE_ID.update(TIKTOK_NEGATIVE)
    HATE_WORDS_ID.update(TIKTOK_HATE)
    TOXIC_WORDS_ID.update(TIKTOK_TOXIC)
    HUMOR_WORDS_ID.update(TIKTOK_HUMOR)

    # Extend regex pattern list (mutate list in place)
    for p in TIKTOK_SARCASM_PATTERNS:
        if p not in SARCASM_PATTERNS:
            SARCASM_PATTERNS.append(p)

    for p in TIKTOK_WELLWISH_PATTERNS:
        if p not in WELLWISH_PATTERNS:
            WELLWISH_PATTERNS.append(p)

    # Re-bind ke instance kalau analyzer cache referensi
    # (di kode loe SentimentAnalyzerV2 baca langsung dari module global,
    #  jadi update di atas sudah cukup. Tapi kita verify safety:)
    print(f"   ✅ TikTok slang extension applied: "
          f"+{len(TIKTOK_POSITIVE)} pos / "
          f"+{len(TIKTOK_NEGATIVE)} neg / "
          f"+{len(TIKTOK_HUMOR)} humor / "
          f"+{len(TIKTOK_SARCASM_PATTERNS)} sarcasm patterns")