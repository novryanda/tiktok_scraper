"use client"

import { useState, useEffect, useSyncExternalStore, useRef } from "react"
import { useRouter } from "next/navigation"
import { Users, Search, Loader2, AlertCircle, CheckCircle, Clock, Heart, Video } from "lucide-react"
import { listProfiles, scrapeProfile, pollJob } from "@/lib/api"
import type { TrackedProfile, ProfileData, ProfileResult, Job } from "@/lib/types"
import { TikTokLogo } from "@/components/ui/TikTokLogo"
import { scrapeStore } from "@/lib/scrapeStore"

function useScrapeStatus() {
  return useSyncExternalStore(
    scrapeStore.subscribe,
    () => scrapeStore.isBusy(),
    () => false,
  )
}

// ── Sanitize input: URL TikTok → username saja ──────────────────────────────
function sanitizeProfileInput(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return trimmed

  // Kalau berupa URL TikTok (http/https atau tiktok.com langsung)
  const urlMatch = trimmed.match(/tiktok\.com\/@([^/?&#\s]+)/i)
  if (urlMatch) return urlMatch[1]

  // Kalau sudah username (dengan atau tanpa @)
  return trimmed.replace(/^@+/, "")
}

export default function ProfilesPage() {
  const router = useRouter()

  const [profiles,     setProfiles]     = useState<TrackedProfile[]>([])
  const [loading,      setLoading]      = useState(true)
  const [input,        setInput]        = useState("")
  const [scraping,     setScraping]     = useState(false)
  const [scrapeResult, setScrapeResult] = useState<ProfileData | null>(null)
  const [error,        setError]        = useState("")
  const [warning,      setWarning]      = useState("")

  const globalBusy    = useScrapeStatus()
  const recoveredRef  = useRef(false)

  // ── Helpers ──────────────────────────────────────────────────────────────

  const reload = () =>
    listProfiles()
      .then(r => { if (r.success) setProfiles(r.data.users) })
      .catch(() => {})

  function applyProfileJob(job: Job<ProfileResult>) {
    if (job.status === "error") throw new Error(job.error || "Scrape profil gagal")
    const res  = job.result
    const prof = (res?.data ?? null) as ProfileData | null
    if (!prof || !prof.username) throw new Error(res?.error || "Data profil kosong")
    setScrapeResult(prof)
    reload()
  }

  // ── Mount: initial load + recovery ───────────────────────────────────────

  useEffect(() => {
    reload().finally(() => setLoading(false))

    if (recoveredRef.current) return
    recoveredRef.current = true

    const active = scrapeStore.rehydrate()
    if (!active) return

    if (active.kind === "profile") {
      setScraping(true)
      setWarning(`Melanjutkan scrape @${active.label}...`)

      pollJob<ProfileResult>(active.jobId, {
        onProgress: j => {
          if (j.status === "running")
            setWarning(`Sedang scrape @${active.label}... (boleh refresh, proses tetap jalan)`)
        },
      })
        .then(job => {
          applyProfileJob(job)
          setWarning("")
        })
        .catch((e: unknown) => {
          setError(e instanceof Error ? e.message : "Gagal melanjutkan scrape profil")
          setWarning("")
        })
        .finally(() => {
          setScraping(false)
          scrapeStore.finish()
        })
    } else {
      setWarning(`Sedang ada proses scraping lain (${active.kind}: ${active.label}). Tunggu selesai.`)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Scrape handler ────────────────────────────────────────────────────────

  async function handleScrape() {
    if (scraping || scrapeStore.isBusy()) {
      setWarning("Tunggu dulu — proses scraping sebelumnya belum selesai.")
      return
    }

    const raw = input.trim()
    if (!raw) { setError("Masukkan username atau URL TikTok"); return }

    // ── Sanitize: strip URL jadi username bersih ──
    const username = sanitizeProfileInput(raw)
    if (!username) { setError("Username tidak valid"); return }

    // Kalau user paste URL, update input field jadi username bersih
    if (username !== raw.replace(/^@+/, "")) {
      setInput(username)
    }

    setError("")
    setWarning("")
    setScrapeResult(null)
    setScraping(true)

    try {
      const resp = await scrapeProfile(username)
      if (!resp.success) throw new Error(resp.message)
      const jobId = resp.data.job_id

      if (!scrapeStore.begin("profile", username, jobId)) {
        setWarning("Tunggu dulu — proses scraping sebelumnya belum selesai.")
        setScraping(false)
        return
      }

      setWarning(`Sedang scrape @${username}... (boleh refresh, proses tetap jalan)`)

      const job = await pollJob<ProfileResult>(jobId, {
        onProgress: j => {
          if (j.status === "running")
            setWarning(`Sedang scrape @${username}... (boleh refresh, proses tetap jalan)`)
        },
      })

      applyProfileJob(job)
      setWarning("")

    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal scrape profil")
    } finally {
      setScraping(false)
      scrapeStore.finish()
    }
  }

  // ── Derived ───────────────────────────────────────────────────────────────

  const disabled   = scraping || globalBusy
  const activeJob  = scrapeStore.getActive()
  const busyVideo  = globalBusy && !scraping && activeJob?.kind !== "profile"

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-8 max-w-5xl">

      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <TikTokLogo size={36} />
        <div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-display)" }}>
            Profiles
          </h1>
          <p className="text-sm text-white/40">Track &amp; analisis akun TikTok</p>
        </div>
      </div>

      {/* Banner: ada scrape VIDEO yang sedang jalan */}
      {busyVideo && (
        <div className="glass-card p-4 mb-6 flex items-start gap-3 border border-yellow-500/20">
          <Clock size={18} className="text-yellow-400 flex-shrink-0 mt-0.5 animate-pulse" />
          <div className="flex-1">
            <p className="text-sm text-yellow-300 font-medium">
              Sedang scrape video: {activeJob?.label}
            </p>
            <p className="text-xs text-white/50 mt-0.5">
              Scrape profil tidak bisa dijalankan bersamaan. Tunggu sampai video selesai.
            </p>
            <button
              onClick={() => router.push("/main/files")}
              className="btn-glass text-xs mt-2"
            >
              Lihat Output Files
            </button>
          </div>
        </div>
      )}

      {/* Form scrape profil */}
      <div className="glass-card p-6 mb-6">
        <h2 className="font-semibold mb-4 text-sm uppercase tracking-widest text-white/50">
          Scrape Profil Baru
        </h2>

        <div className="flex gap-3">
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">@</span>
            <input
              type="text"
              value={input}
              disabled={disabled}
              onChange={e => setInput(e.target.value)}
              placeholder="username atau URL TikTok"
              className="input-glass pl-9 disabled:opacity-50"
              onKeyDown={e => e.key === "Enter" && !disabled && handleScrape()}
            />
          </div>
          <button
            onClick={handleScrape}
            disabled={disabled}
            className="btn-tt flex items-center gap-2 px-5 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {disabled
              ? <Loader2 size={16} className="animate-spin" />
              : <Search size={16} />}
            {scraping ? "Memproses..." : globalBusy ? "Menunggu..." : "Scrape"}
          </button>
        </div>

        {/* Warning */}
        {warning && (
          <div className="mt-3 flex items-center gap-2 text-yellow-300 text-sm glass rounded-xl px-4 py-2.5">
            <Clock size={14} className="flex-shrink-0" />
            {warning}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-3 flex items-start gap-2 text-red-400 text-sm glass rounded-xl px-4 py-2.5">
            <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Scrape gagal</p>
              <p className="text-red-400/70 text-xs mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Hasil scrape */}
        {scrapeResult && (
          <div className="mt-4 glass rounded-2xl p-5">
            <div className="flex items-start gap-4">
              <div className="w-16 h-16 rounded-full overflow-hidden glass flex items-center justify-center flex-shrink-0">
                {scrapeResult.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={scrapeResult.avatar_url}
                    alt={scrapeResult.username}
                    className="w-full h-full object-cover"
                    onError={e => { (e.target as HTMLImageElement).style.display = "none" }}
                  />
                ) : (
                  <Users size={24} className="text-white/30" />
                )}
              </div>

              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-bold text-lg">@{scrapeResult.username}</h3>
                  {scrapeResult.is_verified && (
                    <CheckCircle size={18} className="text-ttcyan" />
                  )}
                </div>
                <p className="text-white/60 text-sm mb-3">
                  {scrapeResult.display_name || "—"}
                </p>

                <div className="grid grid-cols-4 gap-3">
                  {[
                    { l: "Followers", v: scrapeResult.followers },
                    { l: "Following", v: scrapeResult.following },
                    { l: "Likes",     v: scrapeResult.total_likes },
                    { l: "Videos",    v: scrapeResult.total_videos },
                  ].map(x => (
                    <div key={x.l} className="glass rounded-xl p-3 text-center">
                      <p className="text-base font-bold tt-text">
                        {(x.v || 0).toLocaleString("id-ID")}
                      </p>
                      <p className="text-[11px] text-white/40">{x.l}</p>
                    </div>
                  ))}
                </div>

                {scrapeResult.bio && (
                  <p className="text-xs text-white/40 mt-3 leading-relaxed">
                    {scrapeResult.bio}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Tracked profiles list */}
      <div className="glass-card p-6">
        <h2
          className="font-semibold mb-4 flex items-center gap-2"
          style={{ fontFamily: "var(--font-display)" }}
        >
          <Users size={18} className="text-white/50" />
          Tracked Profiles
          {!loading && (
            <span className="text-white/30 font-normal text-sm">({profiles.length})</span>
          )}
        </h2>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="skeleton h-16 rounded-xl" />
            ))}
          </div>
        ) : profiles.length === 0 ? (
          <div className="text-center py-12 text-white/30 text-sm">
            <Users size={40} className="mx-auto mb-3 opacity-20" />
            <p>Belum ada profil yang di-track.</p>
            <p className="text-xs mt-1">Scrape profil di atas untuk memulai.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {profiles.map(p => (
              <div
                key={p.username}
                className="glass rounded-xl px-4 py-3.5 flex items-center gap-4 hover:bg-white/[0.07] transition-colors"
              >
                <div className="w-10 h-10 rounded-full glass flex items-center justify-center flex-shrink-0">
                  <Users size={16} className="text-white/40" />
                </div>
                <div className="flex-1 min-w-0">
                  <span className="font-semibold text-sm">@{p.username}</span>
                  <p className="text-xs text-white/30">{p.data_points} snapshot</p>
                </div>
                <div className="hidden md:flex items-center gap-6 text-xs">
                  <div className="text-center">
                    <p className="font-bold text-white/80">
                      {(p.followers || 0).toLocaleString("id-ID")}
                    </p>
                    <p className="text-white/30">followers</p>
                  </div>
                  <div className="text-center flex flex-col items-center">
                    <p className="font-bold text-white/80 flex items-center gap-1">
                      <Heart size={11} className="text-ttred" />
                      {(p.total_likes || 0).toLocaleString("id-ID")}
                    </p>
                    <p className="text-white/30">likes</p>
                  </div>
                  <div className="text-center flex flex-col items-center">
                    <p className="font-bold text-white/80 flex items-center gap-1">
                      <Video size={11} />
                      {(p.total_videos || 0).toLocaleString("id-ID")}
                    </p>
                    <p className="text-white/30">videos</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}