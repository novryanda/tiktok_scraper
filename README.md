# TikTok Scraper UI

Dashboard scraping & analisis sentimen TikTok. Strukturnya **paralel** dengan aplikasi IG Scraper kamu:

- **Backend**: FastAPI bridge (`backend/main.py`) yang memanggil engine TikTok kamu lewat **subprocess** (fresh browser per request).
- **Frontend**: Next.js 16 (App Router + Turbopack), tema gelap khas TikTok (cyan `#00F2EA` + merah `#FF0050`).
- **Engine**: file scraper TikTok kamu yang sudah ada (`tiktok_scraper.py`, `tiktok_profile_scraper.py`, dll) — **TIDAK diubah**, hanya dipanggil oleh bridge.

---

## 1. Arsitektur

```
┌────────────────┐     HTTP      ┌──────────────────┐   subprocess   ┌──────────────────────┐
│  Next.js (UI)  │ ───────────▶  │  FastAPI bridge  │ ────────────▶  │  Engine TikTok kamu  │
│  :3000         │ ◀───────────  │  main.py :8000   │ ◀────────────  │  (Playwright+Chrome) │
└────────────────┘   JSON resp   └──────────────────┘   JSON stdout  └──────────────────────┘
                                          │                                     │
                                          │  baca/tulis                         │  simpan
                                          ▼                                     ▼
                                  output_tiktok/  &  output_tiktok_profiles/  (file .json)
```

**Kenapa subprocess?** Engine TikTok membuka satu folder Chrome persistent context (`tiktok_chrome_real_profile`). Tiap request scrape dijalankan sebagai proses Python terpisah supaya tidak bentrok antar request — sama persis dengan pendekatan IG-mu.

---

## 2. Struktur folder

```
tiktok-scraper-ui/
├── .vscode/
│   └── settings.json        # fix Pylance (interpreter + extraPaths)
├── backend/
│   ├── main.py              # FastAPI bridge (semua endpoint + logging)
│   ├── requirements.txt     # fastapi, uvicorn, pydantic + deps engine
│   ├── pyrightconfig.json   # fix Pylance untuk import dari engine/
│   ├── setup-backend.bat    # setup otomatis (venv + install + chromium)
│   ├── run-backend.bat      # jalankan uvicorn
│   ├── .env.example         # konfigurasi bridge
│   └── engine/              # ← TARUH SEMUA FILE SCRAPER TIKTOK DI SINI
│       ├── __init__.py
│       └── (tiktok_scraper.py, tiktok_profile_scraper.py, dll)
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx            # root + font
│   │   │   ├── page.tsx              # redirect ke /main/scrapes
│   │   │   ├── globals.css           # tema TikTok (cyan/merah, glass)
│   │   │   └── main/
│   │   │       ├── layout.tsx        # sidebar + indikator session
│   │   │       ├── scrapes/page.tsx  # Scrape Video (single + batch)
│   │   │       ├── profiles/page.tsx # Scrape & track profil
│   │   │       ├── analytics/page.tsx# Agregat sentimen
│   │   │       ├── files/page.tsx    # Preview file output
│   │   │       └── settings/page.tsx # Login: paste cookie JSON
│   │   ├── components/
│   │   │   ├── ui/TikTokLogo.tsx     # logo glitch cyan/merah
│   │   │   ├── ui/StatCard.tsx
│   │   │   ├── features/SentimentChart.tsx
│   │   │   └── features/CommentList.tsx
│   │   └── lib/
│   │       ├── api.ts          # client ke bridge
│   │       ├── types.ts        # tipe sesuai output engine
│   │       └── scrapeStore.ts  # guard scrape ganda lintas-navigasi
│   ├── package.json
│   ├── tailwind.config.ts
│   └── .env.local.example
│
├── README.md
├── SETUP-BACKEND.md         # panduan fix Pylance + setup detail
└── PATCH-ENGINE-COOKIE.md   # cara aktifkan login via cookie di engine
```

---

## 3. Setup

### 3a. Letakkan engine TikTok

Pindahkan / salin SEMUA file engine TikTok kamu ke **`backend/engine/`**:
`tiktok_scraper.py`, `tiktok_profile_scraper.py`, `sentiment_analyzer_v2.py`,
`tiktok_slang_extension.py`, `tiktok_cookie_injector.py`,
`tiktok_session_manager.py`, plus folder `tiktok_chrome_real_profile/` (yang
sudah login) dan `session/`.

Bridge otomatis memakai `backend/engine/` (lihat `ENGINE_DIR` di `main.py`).
Kalau engine ada di tempat lain, set `TIKTOK_ENGINE_DIR` di `backend/.env`.

> Panduan lengkap fix Pylance + setup ada di **`SETUP-BACKEND.md`**.

### 3b. Backend

```bash
cd backend
pip install -r requirements.txt
# (engine punya requirement sendiri: playwright, transformers, torch, dll —
#  pastikan sudah terinstall di environment yang sama)
python main.py
```
Bridge jalan di `http://localhost:8000`. Cek `http://localhost:8000/docs` untuk Swagger.

**Cek koneksi engine:** buka `http://localhost:8000/api/health` — pastikan `engine_found: true`.

### 3c. Frontend

```bash
cd frontend
npm install            # kalau ada konflik peer-deps: npm install --legacy-peer-deps
cp .env.local.example .env.local
npm run dev
```
UI jalan di `http://localhost:3000`.

---

## 4. Login / Session TikTok (via UI Settings)

Login dilakukan dengan **paste cookie JSON** di halaman **Settings** (mirip app IG):

1. Login TikTok di browser biasa.
2. Install ekstensi **Cookie-Editor**, buka tiktok.com.
3. Cookie-Editor → **Export as JSON** (cookie tersalin).
4. Buka UI → **Settings** → paste di kotak → **Simpan Cookies**.

Cookie disimpan ke `engine/session/tt_session.json`. Indikator di sidebar jadi
hijau ("Cookie aktif & valid") kalau berhasil.

> **PENTING:** supaya cookie ini benar-benar dipakai engine saat scraping, kamu
> harus menerapkan patch kecil ke scraper (tambah `inject_cookies_sync`). Lihat
> **`PATCH-ENGINE-COOKIE.md`** — cuma beberapa baris per file.

Alternatif (cara lama): tetap bisa lewat `engine/tiktok_session_manager.py`.

---

## 5. Endpoint bridge

| Method | Path | Fungsi |
|--------|------|--------|
| GET  | `/api/health` | Status bridge + cek engine ditemukan |
| GET  | `/api/session` | Status login TikTok (via engine) |
| GET/POST/DELETE | `/api/cookies` | Cek / simpan / hapus cookie (paste dari Settings) |
| POST | `/api/scrape/video` | Scrape 1 video (`{url, max_comments}`) |
| POST | `/api/scrape/videos/batch` | Batch video (`{urls[], max_comments}`) |
| POST | `/api/scrape/profile` | Scrape profil (`{username}` — bisa URL) |
| GET  | `/api/files` | List file output |
| GET  | `/api/files/{name}` | Isi 1 file |
| GET  | `/api/profiles` | Profil ter-track (growth_tracking.json) |

---

## 6. Debugging

Semua diarahkan ke terminal **backend**, dengan log berlevel + emoji:

```
14:02:11 │ INFO    │ 🔍 POST /api/scrape/video url=https://... max=100
14:02:11 │ INFO    │ 🔍 [video] subprocess start → tmpXXXX.py (timeout 900s)
14:02:58 │ INFO    │    │ engine │ ✅ Video ID: 7411...
14:02:58 │ INFO    │    │ engine │ ✅ CDP berhasil: 100 komentar
14:02:59 │ INFO    │ 🔍 [video] subprocess selesai dalam 47.3s (returncode=0)
14:02:59 │ INFO    │ ✅ 💾 tersimpan: api_video_20260530_140259.json
```

**Poin penting:** seluruh `print()` dari engine kamu (semua `Fore.CYAN/GREEN/...`) di-echo ke log bridge dengan prefix `│ engine │`. Jadi kalau scrape gagal, alasannya kelihatan langsung di terminal backend — tidak perlu buka file log terpisah.

Kalau ada error, urutan cek:
1. `GET /api/health` → `engine_found` harus `true`. Kalau `false`, perbaiki `TIKTOK_ENGINE_DIR`.
2. Lihat blok `│ engine │` di log untuk pesan asli dari scraper.
3. `returncode != 0` → engine crash; pesan error muncul di baris-baris terakhir log.

---

## 7. Fitur UI

- **Scrape Video** — single & batch, slider max komentar (10–100), chart sentimen, **Top 5 komentar paling banyak like**, daftar komentar lengkap dengan badge kategori.
- **Profiles** — scrape profil (username/URL), kartu hasil (followers/likes/videos), daftar profil ter-track dari growth tracking.
- **Analytics** — agregat sentimen lintas video, bar chart, ranking video.
- **Output Files** — preview file video/profil/batch + top komentar.
- **Guard scrape ganda** — kalau satu scrape sedang jalan, halaman lain ikut terkunci (satu kunci global, karena engine berbagi satu Chrome profile). Pindah halaman lalu balik → muncul banner peringatan, scrape tidak diulang.

---

## 8. Catatan & batasan

- **Field data** mengikuti output engine TikTok kamu: video pakai `play_count`/`digg_count`/`video_id`, sentimen pakai `top_liked_comments`. Kalau struktur engine berubah, sesuaikan `frontend/src/lib/types.ts`.
- **Navigasi saat scrape jalan**: request `fetch` terputus saat pindah halaman, tapi engine tetap menyelesaikan scrape & menyimpan JSON → hasil selalu bisa dilihat di Output Files.
- **CAPTCHA**: ditangani engine (solve manual di browser). Karena `TIKTOK_HEADLESS=False`, browser terlihat saat scrape.
- **Timeout**: video 900s, profil 300s (atur di `.env` bila perlu).
```
