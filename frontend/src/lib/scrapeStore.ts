// lib/scrapeStore.ts
// Store status "sedang scraping" — PERSISTENT via localStorage, survive refresh.
//
// FIX v2.0:
//   ✅ Staleness check — job > 20 menit otomatis dianggap expired (tidak block selamanya)
//   ✅ begin() hanya bisa dipanggil SETELAH rehydrate() confirmed tidak ada job aktif
//   ✅ rehydrate() dicek setiap kali begin() dipanggil (bukan hanya saat mount)
//   ✅ Force-finish job expired sebelum begin() baru bisa masuk
//   ✅ getActive() expose kind sehingga halaman lain bisa lihat siapa yang sedang jalan

import type { JobKind } from "./types"

const STORAGE_KEY  = "tiktok_active_job_v2"
const MAX_AGE_MS   = 20 * 60 * 1000  // 20 menit — setelah ini job dianggap stale/hangus

export interface ActiveJob {
  jobId:     string
  kind:      JobKind
  label:     string
  startedAt: number  // Date.now()
}

interface State {
  active: ActiveJob | null
}

const state: State = { active: null }

type Listener = () => void
const listeners = new Set<Listener>()

function emit() {
  listeners.forEach(l => { try { l() } catch { /* ignore */ } })
}

// ── localStorage helpers (SSR-safe) ──────────────────────────────────────

function loadFromStorage(): ActiveJob | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as ActiveJob
    if (!parsed?.jobId || !parsed?.kind) return null
    return parsed
  } catch {
    return null
  }
}

function saveToStorage(job: ActiveJob | null) {
  if (typeof window === "undefined") return
  try {
    if (job) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(job))
    else      window.localStorage.removeItem(STORAGE_KEY)
  } catch { /* quota / privacy errors */ }
}

/**
 * Cek apakah job masih valid (belum expire).
 * Job yang terlalu lama (> MAX_AGE_MS) dianggap hangus — hapus otomatis.
 */
function isJobStale(job: ActiveJob): boolean {
  return Date.now() - job.startedAt > MAX_AGE_MS
}

// ── Hidrasi awal dari localStorage (saat module pertama dimuat di client) ──
if (typeof window !== "undefined") {
  const stored = loadFromStorage()
  if (stored && isJobStale(stored)) {
    // Job lama yang tidak pernah di-finish (crash / tab ditutup paksa)
    saveToStorage(null)
    state.active = null
  } else {
    state.active = stored
  }
}

// ────────────────────────────────────────────────────────────────────────

export const scrapeStore = {

  /**
   * Apakah ada job yang sedang berjalan (dan belum expire).
   */
  isBusy(): boolean {
    if (!state.active) return false
    if (isJobStale(state.active)) {
      // Expired di tengah jalan — bersihkan otomatis
      state.active = null
      saveToStorage(null)
      emit()
      return false
    }
    return true
  },

  /**
   * Job aktif saat ini (atau null jika tidak ada / expired).
   */
  getActive(): ActiveJob | null {
    if (!state.active) return null
    if (isJobStale(state.active)) {
      state.active = null
      saveToStorage(null)
      emit()
      return null
    }
    return { ...state.active }
  },

  /**
   * Mulai job baru.
   *
   * - Mengembalikan false jika sudah ada job aktif yang BELUM expired.
   * - Job expired otomatis dibersihkan sebelum job baru bisa masuk.
   * - Selalu re-baca localStorage sebelum set — guard race condition antar halaman.
   */
  begin(kind: JobKind, label: string, jobId: string): boolean {
    // Re-baca dari storage setiap kali — antar tab / antar halaman bisa tidak sinkron
    const stored = loadFromStorage()
    if (stored && !isJobStale(stored)) {
      // Ada job aktif yang valid dari sumber manapun (tab lain, halaman lain)
      state.active = stored
      return false
    }

    // Tidak ada, atau sudah expired — mulai job baru
    const job: ActiveJob = { jobId, kind, label, startedAt: Date.now() }
    state.active = job
    saveToStorage(job)
    emit()
    return true
  },

  /**
   * Tandai job selesai (sukses / gagal / dibatalkan).
   * Wajib dipanggil di finally block agar store tidak stuck.
   */
  finish() {
    state.active = null
    saveToStorage(null)
    emit()
  },

  /**
   * Re-sinkronisasi dari localStorage.
   * Dipanggil saat komponen mount untuk lihat apakah ada job aktif dari sesi sebelumnya.
   * Job yang expired langsung diabaikan dan dibersihkan.
   */
  rehydrate(): ActiveJob | null {
    const stored = loadFromStorage()
    if (stored && isJobStale(stored)) {
      saveToStorage(null)
      state.active = null
      emit()
      return null
    }
    state.active = stored
    emit()
    return state.active ? { ...state.active } : null
  },

  subscribe(listener: Listener): () => void {
    listeners.add(listener)
    return () => { listeners.delete(listener) }
  },
}