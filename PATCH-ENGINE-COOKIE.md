# 🍪 PATCH ENGINE — Aktifkan Login via Cookie (WAJIB)

Tujuan: `tiktok_scraper.py` & `tiktok_profile_scraper.py` memakai cookie hasil
paste di UI Settings (`engine/session/tt_session.json`), **bukan** hanya
mengandalkan folder `tiktok_chrome_real_profile/`.

Tanpa patch ini, cookie yang kamu paste di Settings **tersimpan tapi tidak
dipakai** engine. Patch ini cuma menambah beberapa baris, tidak menghapus apa pun.

> File `tiktok_cookie_injector.py` (yang sudah kamu punya) menyediakan
> `inject_cookies_sync()` dan `has_valid_session()`. Patch ini tinggal
> memanggilnya. Pastikan `tiktok_cookie_injector.py` ada di `backend/engine/`.

---

## 1. `tiktok_scraper.py` (class TikTokScraperV52)

### A. Tambah import (dekat import lain di atas)

```python
from tiktok_cookie_injector import inject_cookies_sync, has_valid_session
```

### B. Di method `_build_context()`, cari baris terakhir:

```python
        context.on("page", lambda page: page.add_init_script(stealth_script))
        return context
```

Ubah jadi:

```python
        context.on("page", lambda page: page.add_init_script(stealth_script))

        # ── COOKIE LOGIN: inject cookie dari session/tt_session.json ──
        try:
            if has_valid_session():
                n = inject_cookies_sync(context)
                print(Fore.GREEN + f"🍪 Inject {n} cookies dari session file")
        except Exception as e:
            print(Fore.YELLOW + f"⚠️  Cookie inject dilewati: {e}")

        return context
```

---

## 2. `tiktok_profile_scraper.py` (class TikTokProfileScraper)

### A. Tambah import

```python
from tiktok_cookie_injector import inject_cookies_sync, has_valid_session
```

### B. Di method `_build_context()`, cari:

```python
        context.on("page", lambda page: page.add_init_script(stealth_script))
        return context
```

Ubah jadi:

```python
        context.on("page", lambda page: page.add_init_script(stealth_script))

        # ── COOKIE LOGIN: inject cookie dari session/tt_session.json ──
        try:
            if has_valid_session():
                n = inject_cookies_sync(context)
                print(Fore.GREEN + f"🍪 Inject {n} cookies dari session file")
        except Exception as e:
            print(Fore.YELLOW + f"⚠️  Cookie inject dilewati: {e}")

        return context
```

---

## 3. (Opsional) Lewati pengecekan login keras

Engine kamu meng-`exit(1)` kalau `_is_logged_in()` gagal. Setelah cookie
ter-inject, biasanya login terdeteksi. Tapi kalau engine terlanjur exit sebelum
cookie sempat divalidasi, kamu bisa longgarkan: ubah `exit(1)` jadi `print(...)`
peringatan saja. (Tidak wajib — coba dulu tanpa ini.)

---

## 4. Cara Verifikasi

1. Jalankan backend: `run-backend.bat`
2. Buka UI → **Settings** → paste cookie JSON dari Cookie-Editor → **Simpan Cookies**
3. Status berubah jadi hijau "Cookie aktif & valid".
4. Cek cepat di terminal (folder `backend/engine/`):
   ```cmd
   ..\.venv\Scripts\activate
   python -c "import tiktok_cookie_injector as ci; print('valid:', ci.has_valid_session()); print('file:', ci.SESSION_FILE)"
   ```
   Harus `valid: True`.
5. Scrape video. Di log backend cari baris:
   ```
   │ engine │ 🍪 Inject 14 cookies dari session file
   ```
   Kalau muncul, cookie sudah dipakai. ✅

---

## Catatan

- **Folder `tiktok_chrome_real_profile/` tetap dipakai** sebagai tempat browser,
  tapi cookie-nya di-override dari session file. Jadi walau folder itu kosong,
  login tetap jalan dari cookie yang kamu paste.
- `has_valid_session()` mencegah error kalau session file belum ada — engine
  fallback ke perilaku lama (persistent context).
- Kalau cookie `sessionid` expired, scraping akan gagal/redirect login →
  export ulang cookie di UI Settings.
- Pastikan `tiktok_cookie_injector.py` membaca dari `engine/session/tt_session.json`.
  Bridge menulis ke lokasi itu, dan karena subprocess jalan dengan `cwd=engine/`,
  path `session/tt_session.json` di injector akan cocok.
