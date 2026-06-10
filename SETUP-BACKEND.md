# 🔧 Cara Fix Error & Setup Backend TikTok

## Kenapa Muncul Error `reportMissingImports`?

Error itu **bukan error di kode kamu** — itu cuma VS Code (Pylance) yang belum
menemukan package Python. Penyebabnya:

1. **fastapi, uvicorn, pydantic** belum di-`pip install`
2. **tiktok_scraper, tiktok_cookie_injector, dll** ada di folder `engine/`, jadi
   Pylance bingung mencarinya

Kedua masalah ini hilang setelah setup di bawah (sudah disiapkan
`pyrightconfig.json` + `.vscode/settings.json` yang menunjuk ke `engine/`).

---

## 📁 Struktur File yang Benar

Semua kode Python masuk ke folder `backend/`:

```
tiktok-scraper-ui/
├── .vscode/settings.json             ← fix Pylance global
├── backend/
│   ├── main.py                       ← FastAPI bridge (sudah dibuatkan)
│   ├── requirements.txt              ← semua dependencies
│   ├── pyrightconfig.json            ← fix Pylance (extraPaths: engine)
│   ├── setup-backend.bat             ← setup otomatis
│   ├── run-backend.bat               ← jalankan backend
│   ├── .env                          ← (salin dari .env.example)
│   │
│   └── engine/                       ← PINDAHKAN SEMUA FILE SCRAPER TIKTOK KE SINI
│       ├── __init__.py
│       ├── tiktok_scraper.py             ← (file kamu — TikTokScraperV52)
│       ├── tiktok_profile_scraper.py     ← (file kamu — TikTokProfileScraper)
│       ├── sentiment_analyzer_v2.py      ← (file kamu — IndoBERT)
│       ├── tiktok_slang_extension.py     ← (file kamu)
│       ├── tiktok_cookie_injector.py     ← (file kamu)
│       ├── tiktok_session_manager.py     ← (file kamu)
│       ├── tiktok_growth_visualizer.py   ← (opsional)
│       └── .env                          ← config engine (HEADLESS, SENTIMENT_MODE)
│
└── frontend/                         ← Next.js
```

---

## 🚀 Langkah Setup (Windows)

### 1. Pindahkan file scraper ke `backend/engine/`

Copy semua file `.py` scraper TikTok kamu (tiktok_scraper.py,
tiktok_profile_scraper.py, tiktok_cookie_injector.py, tiktok_session_manager.py,
sentiment_analyzer_v2.py, tiktok_slang_extension.py, dll) ke dalam folder
`backend/engine/`.

> Jangan lupa folder `tiktok_chrome_real_profile/` (profil Chrome yang sudah
> login) dan `session/` juga harus ada di `backend/engine/` agar engine
> menemukannya, karena engine memakai `os.getcwd()` dan bridge menjalankan
> subprocess dengan `cwd=engine/`.

### 2. Jalankan setup otomatis

Double-click **`setup-backend.bat`** ATAU manual:

```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 3. Pilih Python Interpreter di VS Code

Setelah venv dibuat, error Pylance hilang dengan cara:

1. Tekan `Ctrl + Shift + P`
2. Ketik: **Python: Select Interpreter**
3. Pilih: `.\backend\.venv\Scripts\python.exe`

Sekarang fastapi, uvicorn, pydantic, dan modul-modul di `engine/` semua
**terdeteksi** ✅ (didukung `pyrightconfig.json` dengan `extraPaths: ["engine"]`).

### 4. Login session TikTok

UI tidak menangani login. Lakukan lewat session manager engine:

```cmd
cd backend\engine
..\.venv\Scripts\activate
python tiktok_session_manager.py
```
Pilih menu **[1]** (paste cookies dari Cookie-Editor) atau **[6]** (login via
browser). Session tersimpan di `engine/session/tt_session.json`.

### 5. Jalankan backend

Double-click **`run-backend.bat`** ATAU:

```cmd
cd backend
.venv\Scripts\activate
uvicorn main:app --reload --port 8001
```

Buka: http://localhost:8001/docs → muncul Swagger API docs.
Cek juga http://localhost:8001/api/health → pastikan `engine_found: true`.

### 6. Jalankan frontend (terminal baru)

```cmd
cd frontend
npm install
npm run dev
```

Buka: http://localhost:3000

---

## ⚠️ Penting: Import di Engine TETAP JALAN

File scraper TikTok kamu saling import begini:
```python
from sentiment_analyzer_v2 import SentimentAnalyzerV2
from tiktok_slang_extension import patch_analyzer_for_tiktok
from tiktok_cookie_injector import inject_cookies_sync
```

Karena sekarang semua ada dalam folder `engine/` yang sama, **import ini tetap
jalan TANPA perlu diubah** — bridge menjalankan subprocess dengan `cwd=engine/`
dan `sys.path` menunjuk ke `engine/` (sudah diatur otomatis di `main.py`).

---

## 🎯 Arsitektur (Lebih Simpel dari versi Flask)

File `tiktok_api_server.py` lama kamu pakai **Flask**. Versi ini menggantinya
dengan **FastAPI bridge** — 2 proses saja (Next.js + FastAPI):

```
Browser (:3000) → FastAPI (:8000) → subprocess → engine/tiktok_scraper.py
```

FastAPI memanggil scraper langsung via subprocess (fresh browser per request).
Tidak perlu Flask server terpisah. Semua `print()` dari engine di-echo ke log
FastAPI dengan prefix `│ engine │` supaya gampang debug.

---

## 🌐 Untuk Deploy Nanti

- **Backend**: deploy `backend/` ke VPS / Railway / Render
  - Set `TIKTOK_HEADLESS=True` di `engine/.env` (server tidak punya display)
  - Jalankan: `uvicorn main:app --host 0.0.0.0 --port 8000`
- **Frontend**: deploy `frontend/` ke Vercel
  - Set env `NEXT_PUBLIC_API_URL` ke URL backend production

> ⚠️ Catatan: Playwright butuh Chromium di server. Untuk deploy, pertimbangkan
> Docker dengan base image `mcr.microsoft.com/playwright/python`.
> TikTok juga lebih agresif soal anti-bot di IP datacenter — siapkan proxy
> residensial (`TIKTOK_PROXY`) bila perlu.

---

## 🩺 Kalau Masih Error

| Gejala | Cek |
|--------|-----|
| `/api/health` → `engine_found: false` | File `tiktok_scraper.py` belum ada di `backend/engine/` |
| Pylance merah di `import fastapi` | Belum pilih interpreter `.venv` (langkah 3) |
| Pylance merah di `import tiktok_scraper` | `pyrightconfig.json` / `.vscode/settings.json` belum aktif → reload VS Code |
| Scrape gagal | Lihat log backend, cari baris `│ engine │` untuk pesan asli engine |
| `Session expired` | Login ulang via `tiktok_session_manager.py` |
| Browser tidak muncul | `TIKTOK_HEADLESS` masih `True` di `engine/.env` |
