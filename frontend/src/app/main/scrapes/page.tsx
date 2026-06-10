"use client"

import { useState, useEffect, useSyncExternalStore, useRef } from "react"
import { useRouter } from "next/navigation"
import {
  Search, Link2, Loader2, AlertCircle, ChevronDown, ChevronUp,
  Plus, Trash2, CheckCircle, XCircle, Clock, Music2, Trophy,
  Users, Heart, MessageCircle, UserCheck, UserX, Star,
} from "lucide-react"
import { scrapeVideoUnified, scrapeVideos, scrapeVideoCheckpoint, pollJob } from "@/lib/api"
import type { VideoResult, SentimentSummary, BatchItem, BatchScrapeData, Liker, ActiveCommenter } from "@/lib/types"
import { StatCard }       from "@/components/ui/StatCard"
import { SentimentChart } from "@/components/features/SentimentChart"
import { CommentList }    from "@/components/features/CommentList"
import { TikTokLogo }     from "@/components/ui/TikTokLogo"
import { scrapeStore }    from "@/lib/scrapeStore"

type Mode = "single" | "batch"
type ScrapeType = "unified" | "checkpoint"

function useScrapeStatus() {
  return useSyncExternalStore(
    scrapeStore.subscribe,
    () => scrapeStore.isBusy(),
    () => false,
  )
}

// ── Safe helpers ──────────────────────────────────────────────────────────

function safeCommentsCount(result: VideoResult): number {
  if (typeof result.comments_count === "number") return result.comments_count
  if (Array.isArray(result.comments)) return result.comments.length
  return 0
}

function getTopLikedComments(s: SentimentSummary) {
  return Array.isArray(s?.top_liked_comments) ? s.top_liked_comments : []
}

function computeTop5Liked(result: VideoResult) {
  if (Array.isArray((result as any).top_5_liked_comments) && (result as any).top_5_liked_comments.length > 0) {
    return (result as any).top_5_liked_comments
  }
  const ss = result.sentiment_summary
  if (ss) {
    const topLiked = getTopLikedComments(ss)
    if (topLiked.length > 0) return topLiked.slice(0, 5)
  }
  if (Array.isArray(result.comments) && result.comments.length > 0) {
    const sorted = [...result.comments].sort((a, b) => (b.like_count ?? 0) - (a.like_count ?? 0))
    return sorted.slice(0, 5).map((c, i) => ({
      rank:       i + 1,
      username:   c.username,
      nickname:   c.nickname ?? c.username,
      text:       c.text,
      like_count: c.like_count ?? 0,
      category:   c.category  ?? "NEUTRAL",
      sentiment:  c.sentiment ?? "",
    }))
  }
  return []
}

// ── Category style helper ─────────────────────────────────────────────────

function categoryStyle(cat: string) {
  switch (cat) {
    case "POSITIVE":    return "bg-green-500/15 text-green-400"
    case "NEGATIVE":    return "bg-red-500/15 text-red-400"
    case "HUMOR":       return "bg-purple-500/15 text-purple-400"
    case "HATE_SPEECH": return "bg-red-600/20 text-red-300"
    case "TOXIC":       return "bg-yellow-500/15 text-yellow-400"
    default:            return "bg-white/10 text-white/50"
  }
}

function categoryLabel(cat: string) {
  switch (cat) {
    case "POSITIVE":    return "😊 Positif"
    case "NEGATIVE":    return "😞 Negatif"
    case "HUMOR":       return "😂 Humor"
    case "HATE_SPEECH": return "🚨 Hate"
    case "TOXIC":       return "⚠️ Toxic"
    default:            return "😐 Netral"
  }
}

const RANK_ICONS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

// ── Top 5 liked comments component ────────────────────────────────────────

interface Top5Props {
  comments: Array<{
    rank:       number
    username:   string
    text:       string
    like_count: number
    category?:  string
    sentiment?: string
  }>
  title?: string
}

function Top5LikedComments({ comments, title = "🏆 Top 5 Komentar (Like Terbanyak)" }: Top5Props) {
  if (!comments || comments.length === 0) {
    return (
      <div className="glass-card p-6">
        <h3 className="font-semibold mb-3 text-sm uppercase tracking-widest text-white/50">{title}</h3>
        <p className="text-white/30 text-sm text-center py-4">
          Belum ada data like — normal untuk DOM mode
        </p>
      </div>
    )
  }

  return (
    <div className="glass-card p-6">
      <div className="flex items-center gap-2 mb-5">
        <Trophy size={18} className="text-yellow-400" />
        <h3 className="font-semibold text-sm uppercase tracking-widest text-white/50">{title}</h3>
      </div>
      <div className="space-y-4">
        {comments.map((c, i) => (
          <div
            key={i}
            className={`relative rounded-2xl p-4 border transition-all ${
              i === 0 ? "border-yellow-500/30 bg-yellow-500/5"  :
              i === 1 ? "border-slate-400/20 bg-slate-400/5"   :
              i === 2 ? "border-amber-700/20 bg-amber-700/5"   :
                        "border-white/5 bg-white/[0.02]"
            }`}
          >
            <div className="flex items-start gap-3">
              <span className="text-2xl flex-shrink-0 mt-0.5 select-none">
                {RANK_ICONS[i] ?? `#${i + 1}`}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="font-semibold text-sm text-white/90">@{c.username}</span>
                  {c.category && (
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${categoryStyle(c.category)}`}>
                      {categoryLabel(c.category)}
                    </span>
                  )}
                </div>
                <p className="text-sm text-white/60 leading-relaxed break-words">{c.text}</p>
              </div>
              <div className="flex-shrink-0 text-right">
                <p className="text-ttred font-bold text-base">
                  ❤ {(c.like_count ?? 0).toLocaleString("id-ID")}
                </p>
                <p className="text-[10px] text-white/30">likes</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Likers List Component ─────────────────────────────────────────────────

function LikersList({ likers }: { likers: Liker[] }) {
  const [showAll, setShowAll] = useState(false)
  const display = showAll ? likers : likers.slice(0, 20)

  if (!likers || likers.length === 0) {
    return (
      <div className="glass-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Heart size={18} className="text-ttred" />
          <h3 className="font-semibold text-sm uppercase tracking-widest text-white/50">Likers</h3>
        </div>
        <p className="text-white/30 text-sm text-center py-4">Tidak ada data likers</p>
      </div>
    )
  }

  return (
    <div className="glass-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Heart size={18} className="text-ttred" />
          <h3 className="font-semibold text-sm uppercase tracking-widest text-white/50">
            Likers ({likers.length})
          </h3>
        </div>
        {likers.length > 20 && (
          <button
            onClick={() => setShowAll(!showAll)}
            className="text-xs text-white/40 hover:text-white/70 transition-colors"
          >
            {showAll ? "Tampilkan lebih sedikit" : `Tampilkan ${likers.length - 20} lainnya`}
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {display.map((liker, idx) => (
          <div key={liker.user_id || idx} className="flex items-center gap-2 bg-white/5 rounded-lg p-2">
            <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center overflow-hidden flex-shrink-0">
              {liker.avatar_url ? (
                <img src={liker.avatar_url} alt="" className="w-full h-full object-cover" />
              ) : (
                <Users size={14} className="text-white/30" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-white/80 truncate">@{liker.username}</p>
              <div className="flex items-center gap-1">
                {liker.is_verified && <CheckCircle size={10} className="text-ttcyan" />}
                {liker.is_private && <UserX size={10} className="text-white/30" />}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Active Commenters Component ───────────────────────────────────────────

function ActiveCommenters({ commenters }: { commenters: ActiveCommenter[] }) {
  if (!commenters || commenters.length === 0) {
    return (
      <div className="glass-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Users size={18} className="text-ttcyan" />
          <h3 className="font-semibold text-sm uppercase tracking-widest text-white/50">Komentator Teraktif</h3>
        </div>
        <p className="text-white/30 text-sm text-center py-4">Belum ada data</p>
      </div>
    )
  }

  return (
    <div className="glass-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Users size={18} className="text-ttcyan" />
        <h3 className="font-semibold text-sm uppercase tracking-widest text-white/50">
          Komentator Teraktif ({commenters.length})
        </h3>
      </div>
      <div className="space-y-3">
        {commenters.slice(0, 10).map((c, idx) => (
          <div key={c.username} className="flex items-center justify-between p-3 rounded-xl bg-white/5">
            <div className="flex items-center gap-3">
              <span className="text-xs font-bold text-white/40 w-6">#{idx + 1}</span>
              <div>
                <p className="font-medium text-sm">@{c.username}</p>
                <div className="flex items-center gap-3 text-xs text-white/40 mt-0.5">
                  <span className="flex items-center gap-1">
                    <MessageCircle size={10} /> {c.comment_count}
                  </span>
                  <span className="flex items-center gap-1">
                    <Heart size={10} /> {c.reply_count} reply
                  </span>
                  <span className="flex items-center gap-1">
                    <Star size={10} /> {c.total_likes} likes
                  </span>
                </div>
              </div>
            </div>
            <div className="text-right">
              <span className={`text-xs px-2 py-0.5 rounded-full ${categoryStyle(c.dominant_category)}`}>
                {categoryLabel(c.dominant_category)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ════════════════════════════════════════════════════════════════════════

export default function ScrapeVideoPage() {
  const router = useRouter()

  const [mode,        setMode]        = useState<Mode>("single")
  const [scrapeType,  setScrapeType]  = useState<ScrapeType>("unified")
  const [url,         setUrl]         = useState("")
  const [batchUrls,   setBatchUrls]   = useState<string[]>(["", ""])
  const [maxComments, setMaxComments] = useState(100)
  const [includeReplies, setIncludeReplies] = useState(true)
  const [maxReplies, setMaxReplies] = useState(20)
  const [scrapeLikers, setScrapeLikers] = useState(true)
  const [maxLikers, setMaxLikers] = useState(500)
  const [checkpointBatchSize, setCheckpointBatchSize] = useState(200)    // ← FIX: lebih kecil
  const [checkpointMaxTotal,  setCheckpointMaxTotal]  = useState(1000)   // ← FIX: lebih realistis

  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState("")
  const [warning,     setWarning]     = useState("")

  const [result,       setResult]       = useState<VideoResult | null>(null)
  const [showComments, setShowComments] = useState(false)

  const [batchResults, setBatchResults] = useState<BatchItem[] | null>(null)
  const [batchSummary, setBatchSummary] = useState<{ total: number; success: number; failed: number } | null>(null)
  const [openComments, setOpenComments] = useState<number | null>(null)

  const globalBusy   = useScrapeStatus()
  const recoveredRef = useRef(false)

  function applyBatch(data: BatchScrapeData) {
    setBatchResults(data.results || [])
    setBatchSummary({
      total:   data.total   ?? (data.results?.length || 0),
      success: data.success ?? (data.results?.filter(r => r.success).length  || 0),
      failed:  data.failed  ?? (data.results?.filter(r => !r.success).length || 0),
    })
  }

  // ── Recovery job aktif setelah refresh ───────────────────────────────────
  useEffect(() => {
    if (recoveredRef.current) return
    recoveredRef.current = true

    const active = scrapeStore.rehydrate()
    if (!active) return

    if (active.kind === "single") {
      setMode("single")
      setLoading(true)
      setWarning("Melanjutkan scrape video yang sedang berjalan...")

      // ✅ PERBAIKAN: timeout 2 jam untuk semua job single (termasuk checkpoint)
      pollJob<VideoResult>(active.jobId, {
        timeoutMs: 2 * 60 * 60 * 1000,
        onProgress: j => {
          if (j.status === "running")
            setWarning("Sedang scraping... (boleh refresh, proses tetap jalan)")
        },
      })
        .then(job => {
          if (job.status === "error") throw new Error(job.error || "Scrape gagal")
          if (job.result) { setResult(job.result); setShowComments(false) }
          setWarning("")
        })
        .catch((e: unknown) => setError(e instanceof Error ? e.message : "Gagal melanjutkan scrape"))
        .finally(() => { setLoading(false); scrapeStore.finish() })

    } else if (active.kind === "batch") {
      setMode("batch")
      setLoading(true)
      setWarning("Melanjutkan batch scrape yang sedang berjalan...")

      pollJob<BatchScrapeData>(active.jobId, {
        onProgress: j => {
          if (j.status === "running")
            setWarning("Batch berjalan... (boleh refresh, proses tetap jalan)")
        },
      })
        .then(job => {
          if (job.status === "error") throw new Error(job.error || "Batch gagal")
          if (job.result) applyBatch(job.result)
          setWarning("")
        })
        .catch((e: unknown) => setError(e instanceof Error ? e.message : "Gagal melanjutkan batch"))
        .finally(() => { setLoading(false); scrapeStore.finish() })

    } else {
      setWarning(`Sedang ada scrape profil (${active.label}). Tunggu selesai.`)
    }
  }, [])

  // ── Scrape handler ────────────────────────────────────────────────────────

  async function handleScrape() {
    if (scrapeStore.isBusy()) {
      setWarning("Tunggu dulu — proses scraping sebelumnya belum selesai.")
      return
    }

    const target     = mode === "single" ? url.trim() : ""
    const validBatch = batchUrls.filter(u => u.trim())

    if (mode === "single" && !target)          { setError("Masukkan URL video TikTok"); return }
    if (mode === "batch"  && validBatch.length === 0) { setError("Masukkan minimal 1 URL"); return }

    setError(""); setWarning("")
    setResult(null); setBatchResults(null); setBatchSummary(null); setOpenComments(null)
    setLoading(true)

    try {
      if (mode === "single") {
        let resp
        if (scrapeType === "checkpoint") {
          resp = await scrapeVideoCheckpoint(target, checkpointBatchSize, checkpointMaxTotal)
        } else {
          resp = await scrapeVideoUnified(target, maxComments, includeReplies, maxReplies, scrapeLikers, maxLikers)
        }
        if (!resp.success) throw new Error(resp.message)
        const jobId = resp.data.job_id

        if (!scrapeStore.begin("single", target, jobId)) {
          setWarning("Tunggu dulu — proses scraping sebelumnya belum selesai.")
          setLoading(false)
          return
        }

        // ✅ PERBAIKAN: timeout 2 jam untuk checkpoint, default untuk lainnya
        const job = await pollJob<VideoResult>(jobId, {
          timeoutMs: scrapeType === "checkpoint" ? 2 * 60 * 60 * 1000 : undefined,
          onProgress: j => {
            if (j.status === "running")
              setWarning("Sedang scraping... (boleh refresh, proses tetap jalan)")
          },
        })
        if (job.status === "error") throw new Error(job.error || "Scrape gagal")
        if (job.result) { setResult(job.result); setShowComments(false) }
        setWarning("")

      } else {
        // Batch mode hanya support comments saja (sederhana)
        const resp = await scrapeVideos(validBatch, maxComments)
        if (!resp.success) throw new Error(resp.message)
        const jobId = resp.data.job_id

        if (!scrapeStore.begin("batch", `${validBatch.length} URL`, jobId)) {
          setWarning("Tunggu dulu — proses scraping sebelumnya belum selesai.")
          setLoading(false)
          return
        }

        const job = await pollJob<BatchScrapeData>(jobId, {
          onProgress: j => {
            if (j.status === "running")
              setWarning("Batch berjalan... (boleh refresh, proses tetap jalan)")
          },
        })
        if (job.status === "error") throw new Error(job.error || "Batch gagal")
        if (job.result) applyBatch(job.result)
        setWarning("")
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Terjadi kesalahan tidak diketahui")
    } finally {
      setLoading(false)
      scrapeStore.finish()
    }
  }

  const s          = result?.sentiment_summary
  const disabled   = loading || globalBusy
  const activeJob  = scrapeStore.getActive()
  const busyProfile = globalBusy && !loading && activeJob?.kind === "profile"
  const busyOther   = globalBusy && !loading && !busyProfile

  return (
    <div className="p-8 max-w-5xl">

      <div className="flex items-center gap-3 mb-8">
        <TikTokLogo size={36} />
        <div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-display)" }}>
            Scrape Video
          </h1>
          <p className="text-sm text-white/40">Ambil komentar, likers, dan analisis sentimen dari TikTok</p>
        </div>
      </div>

      {busyProfile && (
        <div className="glass-card p-4 mb-6 flex items-start gap-3 border border-yellow-500/20">
          <Clock size={18} className="text-yellow-400 flex-shrink-0 mt-0.5 animate-pulse" />
          <div className="flex-1">
            <p className="text-sm text-yellow-300 font-medium">Sedang scrape profil: @{activeJob?.label}</p>
            <p className="text-xs text-white/50 mt-0.5">Scrape video tidak bisa dijalankan bersamaan. Tunggu sampai profil selesai.</p>
            <button onClick={() => router.push("/main/profiles")} className="btn-glass text-xs mt-2">Lihat halaman Profiles</button>
          </div>
        </div>
      )}

      {busyOther && (
        <div className="glass-card p-4 mb-6 flex items-start gap-3 border border-yellow-500/20">
          <Clock size={18} className="text-yellow-400 flex-shrink-0 mt-0.5 animate-pulse" />
          <div className="flex-1">
            <p className="text-sm text-yellow-300 font-medium">Scraping masih berjalan</p>
            <p className="text-xs text-white/50 mt-0.5">Hasil otomatis tersimpan — cek di Output Files.</p>
            <button onClick={() => router.push("/main/files")} className="btn-glass text-xs mt-2">Lihat Output Files</button>
          </div>
        </div>
      )}

      {/* Mode toggle */}
      <div className="glass-card p-1 inline-flex mb-6 gap-1">
        {(["single", "batch"] as Mode[]).map(m => (
          <button
            key={m}
            onClick={() => !disabled && setMode(m)}
            disabled={disabled}
            className={`px-5 py-2 rounded-xl text-sm font-medium transition-all ${
              mode === m ? "bg-white/10 text-white" : "text-white/40 hover:text-white/70"
            } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            {m === "single" ? "🔗 Single URL" : "📋 Batch URLs"}
          </button>
        ))}
      </div>

      {/* Scrape Type selector (hanya untuk single mode) */}
      {mode === "single" && (
        <div className="glass-card p-1 inline-flex mb-6 gap-1 ml-4">
          {(["unified", "checkpoint"] as ScrapeType[]).map(t => (
            <button
              key={t}
              onClick={() => !disabled && setScrapeType(t)}
              disabled={disabled}
              className={`px-5 py-2 rounded-xl text-sm font-medium transition-all ${
                scrapeType === t ? "bg-ttcyan/20 text-ttcyan border border-ttcyan/30" : "text-white/40 hover:text-white/70"
              } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
            >
              {t === "unified" ? "🚀 Unified (Comments + Likers)" : "📦 Checkpoint (Banyak Komentar)"}
            </button>
          ))}
        </div>
      )}

      {/* Input card */}
      <div className="glass-card p-6 mb-6">
        {mode === "single" ? (
          <div className="mb-4">
            <label className="block text-xs text-white/50 mb-2 uppercase tracking-widest">URL Video TikTok</label>
            <div className="relative">
              <Link2 size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
              <input
                type="url"
                value={url}
                disabled={disabled}
                onChange={e => setUrl(e.target.value)}
                placeholder="https://www.tiktok.com/@user/video/123..."
                className="input-glass pl-11"
                onKeyDown={e => e.key === "Enter" && !disabled && handleScrape()}
              />
            </div>
          </div>
        ) : (
          <div className="mb-4">
            <label className="block text-xs text-white/50 mb-2 uppercase tracking-widest">Daftar URL</label>
            <div className="space-y-2">
              {batchUrls.map((u, i) => (
                <div key={i} className="flex gap-2">
                  <div className="relative flex-1">
                    <Link2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
                    <input
                      type="url"
                      value={u}
                      disabled={disabled}
                      onChange={e => {
                        const copy = [...batchUrls]
                        copy[i] = e.target.value
                        setBatchUrls(copy)
                      }}
                      placeholder={`URL #${i + 1}`}
                      className="input-glass pl-10 text-sm"
                    />
                  </div>
                  {batchUrls.length > 1 && (
                    <button
                      onClick={() => !disabled && setBatchUrls(batchUrls.filter((_, idx) => idx !== i))}
                      disabled={disabled}
                      className="glass rounded-xl p-2.5 text-white/40 hover:text-ttred transition-colors disabled:opacity-50"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
              <button
                onClick={() => !disabled && setBatchUrls([...batchUrls, ""])}
                disabled={disabled}
                className="btn-glass flex items-center gap-2 text-sm w-full justify-center disabled:opacity-50"
              >
                <Plus size={14} /> Tambah URL
              </button>
            </div>
          </div>
        )}

        {/* Kontrol parameter scraping */}
        <div className="flex flex-wrap gap-6 mb-4">
          {scrapeType !== "checkpoint" && (
            <div className="flex-1 min-w-[150px]">
              <label className="block text-xs text-white/50 mb-2 uppercase tracking-widest">
                Max Komentar: <span className="text-white/80 normal-case">{maxComments}</span>
              </label>
              <input
                type="range" min={10} max={500} step={10} value={maxComments}
                disabled={disabled}
                onChange={e => setMaxComments(Number(e.target.value))}
                className="w-full accent-ttcyan h-1.5"
              />
            </div>
          )}

          {scrapeType === "checkpoint" && (
            <>
              <div className="flex-1 min-w-[150px]">
                <label className="block text-xs text-white/50 mb-2 uppercase tracking-widest">
                  Batch Size: <span className="text-white/80 normal-case">{checkpointBatchSize}</span>
                </label>
                <input
                  type="range" min={100} max={500} step={50} value={checkpointBatchSize}
                  disabled={disabled}
                  onChange={e => setCheckpointBatchSize(Number(e.target.value))}
                  className="w-full accent-ttcyan h-1.5"
                />
              </div>
              <div className="flex-1 min-w-[150px]">
                <label className="block text-xs text-white/50 mb-2 uppercase tracking-widest">
                  Max Total: <span className="text-white/80 normal-case">{checkpointMaxTotal.toLocaleString("id-ID")}</span>
                </label>
                <input
                  type="range" min={300} max={2000} step={100} value={checkpointMaxTotal}   // ← FIX: max 2000
                  disabled={disabled}
                  onChange={e => setCheckpointMaxTotal(Number(e.target.value))}
                  className="w-full accent-ttred h-1.5"
                />
              </div>
              <p className="w-full text-xs text-white/40">
                📦 Mode checkpoint mengambil komentar batch-per-batch dengan cooldown antar batch (lebih lambat tapi tahan CAPTCHA, bisa tembus jauh di atas 500).
              </p>
            </>
          )}

          {scrapeType === "unified" && (
            <>
              <div className="flex-1 min-w-[150px]">
                <label className="block text-xs text-white/50 mb-2 uppercase tracking-widest">
                  Max Likers: <span className="text-white/80 normal-case">{maxLikers}</span>
                </label>
                <input
                  type="range" min={50} max={2000} step={50} value={maxLikers}
                  disabled={disabled}
                  onChange={e => setMaxLikers(Number(e.target.value))}
                  className="w-full accent-ttred h-1.5"
                />
              </div>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={scrapeLikers}
                    onChange={e => setScrapeLikers(e.target.checked)}
                    disabled={disabled}
                    className="rounded bg-white/10 border-white/20"
                  />
                  <span className="text-sm text-white/70">Scrape Likers</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={includeReplies}
                    onChange={e => setIncludeReplies(e.target.checked)}
                    disabled={disabled}
                    className="rounded bg-white/10 border-white/20"
                  />
                  <span className="text-sm text-white/70">Include Replies</span>
                </label>
              </div>
            </>
          )}
        </div>

        <button
          onClick={handleScrape}
          disabled={disabled}
          className="btn-tt flex items-center gap-2 px-6 py-3 w-full justify-center disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {disabled ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
          {loading ? "Memproses..." : globalBusy ? "Menunggu..." : "Scrape"}
        </button>

        {warning && (
          <div className="mt-4 flex items-center gap-2 text-yellow-300 text-sm glass rounded-xl px-4 py-3">
            <Clock size={16} className="flex-shrink-0" /> {warning}
          </div>
        )}
        {error && (
          <div className="mt-4 flex items-start gap-2 text-red-400 text-sm glass rounded-xl px-4 py-3">
            <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Scrape gagal</p>
              <p className="text-red-400/70 text-xs mt-0.5">{error}</p>
              <p className="text-white/30 text-xs mt-2">
                Pastikan: session/tt_session.json valid, URL benar, browser tidak headless
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Loading spinner */}
      {loading && (
        <div className="glass-card p-12 text-center mb-6">
          <div className="relative w-16 h-16 mx-auto mb-4">
            <TikTokLogo size={64} className="opacity-30" />
            <div className="absolute inset-0 animate-spin-slow">
              <div className="w-full h-full rounded-full border-2 border-transparent border-t-ttcyan" />
            </div>
          </div>
          <p className="text-white/60 text-sm">Sedang scraping TikTok...</p>
          <p className="text-white/30 text-xs mt-1">Boleh refresh halaman — proses tetap berjalan di server</p>
        </div>
      )}

      {/* ════════ HASIL SINGLE ════════ */}
      {result && s && (
        <div className="space-y-6">

          <div className="glass-card p-6">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h2 className="font-semibold text-lg">@{result.username || "unknown"}</h2>
                <p className="text-xs text-white/40 mt-0.5 flex items-center gap-1 flex-wrap">
                  {result.music_title && <><Music2 size={11} /> {result.music_title} · </>}
                  via {result.method || "—"}
                  {(result as any).batches ? ` · ${(result as any).batches} batch` : ""}
                  {result.likers_method && ` · likers: ${result.likers_method}`}
                </p>
              </div>
              <a href={result.url} target="_blank" rel="noopener noreferrer" className="btn-glass text-xs flex items-center gap-1.5">
                <Link2 size={12} /> Buka Video
              </a>
            </div>
            {result.description && (
              <p className="text-sm text-white/50 leading-relaxed line-clamp-3 border-l-2 border-white/10 pl-3">
                {result.description}
              </p>
            )}
            {result.hashtags && result.hashtags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {result.hashtags.slice(0, 8).map((h, i) => (
                  <span key={i} className="text-[11px] px-2 py-0.5 rounded-full bg-ttcyan/10 text-ttcyan">#{h}</span>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Views"    value={result.play_count}         color="cyan"   />
            <StatCard label="Likes"    value={result.digg_count}         color="red"    />
            <StatCard label="Komentar" value={safeCommentsCount(result)} color="white"  />
            <StatCard label="Shares"   value={result.share_count}        color="purple" />
          </div>

          {/* Top 5 liked comments */}
          <Top5LikedComments comments={computeTop5Liked(result)} />

          {/* Likers (hanya untuk unified & checkpoint juga bisa punya likers jika engine mendukung) */}
          {result.likers && <LikersList likers={result.likers} />}

          {/* Active Commenters */}
          {result.active_commenters && result.active_commenters.length > 0 && (
            <ActiveCommenters commenters={result.active_commenters} />
          )}

          {/* Sentiment chart + detail */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="glass-card p-6">
              <h3 className="font-semibold mb-4 text-sm uppercase tracking-widest text-white/50">Distribusi Sentimen</h3>
              <SentimentChart summary={s} />
            </div>
            <div className="glass-card p-6">
              <h3 className="font-semibold mb-4 text-sm uppercase tracking-widest text-white/50">Detail Sentimen</h3>
              <div className="space-y-3">
                {[
                  { label: "😊 Positif", count: s.positive_count,    pct: s.positive_percentage,    color: "#22c55e" },
                  { label: "😞 Negatif", count: s.negative_count,    pct: s.negative_percentage,    color: "#f87171" },
                  { label: "😐 Netral",  count: s.neutral_count,     pct: s.neutral_percentage,     color: "#94a3b8" },
                  { label: "😂 Humor",   count: s.humor_count,       pct: s.humor_percentage,       color: "#818cf8" },
                  { label: "⚠️ Toxic",   count: s.toxic_count,       pct: s.toxic_percentage,       color: "#fde047" },
                  { label: "🚨 Hate",    count: s.hate_speech_count, pct: s.hate_percentage,        color: "#ef4444" },
                ].map(item => (
                  <div key={item.label}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-white/70">{item.label}</span>
                      <span className="text-white/50">{item.count} ({item.pct}%)</span>
                    </div>
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${item.pct}%`, background: item.color }} />
                    </div>
                  </div>
                ))}
              </div>
              {s.sarcasm_count > 0 && (
                <p className="text-xs text-white/40 mt-4">
                  🎭 Sarkasme: {s.sarcasm_count} ({s.sarcasm_percentage}%) &nbsp;
                  🙏 Doa: {s.wellwish_count} ({s.wellwish_percentage}%)
                </p>
              )}
            </div>
          </div>

          {/* Semua komentar toggle */}
          <div className="glass-card p-6">
            <button
              onClick={() => setShowComments(v => !v)}
              className="w-full flex items-center justify-between font-semibold text-sm"
            >
              <span>💬 Semua Komentar ({safeCommentsCount(result)})</span>
              {showComments ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
            {showComments && (
              <div className="mt-4">
                <CommentList comments={result.comments} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ════════ HASIL BATCH (tidak berubah) ════════ */}
      {batchResults && batchSummary && (
        <div className="space-y-5">
          <div className="glass-card p-5 flex items-center gap-6">
            <div>
              <p className="text-2xl font-bold tt-text">{batchSummary.success}/{batchSummary.total}</p>
              <p className="text-xs text-white/40">video berhasil</p>
            </div>
            <div className="flex items-center gap-2 text-sm text-emerald-400"><CheckCircle size={16} /> {batchSummary.success} sukses</div>
            {batchSummary.failed > 0 && <div className="flex items-center gap-2 text-sm text-red-400"><XCircle size={16} /> {batchSummary.failed} gagal</div>}
          </div>

          {batchResults.map((item, idx) => {
            const d = item.data
            const ss = d?.sentiment_summary
            const isOpen = openComments === idx
            if (!item.success || !d) {
              return (
                <div key={idx} className="glass-card p-5 border border-red-500/20">
                  <div className="flex items-center gap-2 text-red-400 text-sm"><XCircle size={16} /><span className="font-medium">Gagal</span></div>
                  <p className="text-xs text-white/40 mt-1 break-all">{item.url}</p>
                  {item.error && <p className="text-xs text-red-400/70 mt-1">{item.error}</p>}
                </div>
              )
            }
            const top5Batch = computeTop5Liked(d)
            return (
              <div key={idx} className="glass-card p-5 space-y-4">
                <div className="flex items-start justify-between">
                  <div className="min-w-0"><h3 className="font-semibold">@{d.username || "unknown"}</h3><p className="text-xs text-white/40 mt-0.5">via {d.method || "—"}</p></div>
                  <a href={d.url} target="_blank" rel="noopener noreferrer" className="btn-glass text-xs flex items-center gap-1.5"><Link2 size={12} /> Buka</a>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    { label: "Views",   value: d.play_count  ?? 0, color: "text-ttcyan"    },
                    { label: "Likes",   value: d.digg_count  ?? 0, color: "text-ttred"     },
                    { label: "Positif", value: (ss?.positive_percentage ?? 0) + "%", color: "text-emerald-400" },
                    { label: "Negatif", value: (ss?.negative_percentage ?? 0) + "%", color: "text-red-400"     },
                  ].map(stat => (
                    <div key={stat.label} className="glass rounded-xl p-3 text-center">
                      <p className={`text-lg font-bold ${stat.color}`}>{typeof stat.value === "number" ? stat.value.toLocaleString("id-ID") : stat.value}</p>
                      <p className="text-[11px] text-white/40">{stat.label}</p>
                    </div>
                  ))}
                </div>
                {ss && ss.total_comments > 0 && <SentimentChart summary={ss} />}
                <Top5LikedComments comments={top5Batch} title={`🏆 Top ${top5Batch.length} Komentar (Like Terbanyak)`} />
                {Array.isArray(d.comments) && d.comments.length > 0 && (
                  <div>
                    <button onClick={() => setOpenComments(isOpen ? null : idx)} className="w-full flex items-center justify-between text-sm font-medium">
                      <span>💬 Semua Komentar ({safeCommentsCount(d)})</span>
                      {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                    {isOpen && <div className="mt-3"><CommentList comments={d.comments} /></div>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}