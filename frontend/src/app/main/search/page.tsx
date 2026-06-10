"use client"

// ══════════════════════════════════════════════════════════════════════════
// app/main/search/page.tsx
// TikTok Search Page — Hashtag | Keyword | Deep Search
// ══════════════════════════════════════════════════════════════════════════

import { useState, useEffect, useRef, useCallback } from "react"
import {
  Hash, Search, Zap, ChevronDown, ChevronUp,
  Download, RefreshCw, X, AlertCircle, Clock,
  Heart, MessageCircle, Share2, Play, Music2,
  CheckCircle, XCircle, Loader2, Sparkles,
  BarChart2, TrendingUp, ExternalLink, Filter,
  StopCircle, Trash2, Eye,
} from "lucide-react"
import {
  searchHashtag,
  searchKeyword,
  discoverHashtags,
  startDeepHashtagSearch,
  startDeepKeywordSearch,
  listDeepSearchJobs,
  getDeepSearchJob,
  cancelDeepSearchJob,
  deleteDeepSearchJob,
  getDeepSearchJobPosts,
  downloadSearchCsv,
} from "@/lib/api"
import type {
  SearchPost,
  HashtagSearchResult,
  KeywordSearchResult,
  DeepSearchJob,
  SuggestedHashtag,
} from "@/lib/types"
import { TikTokLogo } from "@/components/ui/TikTokLogo"

// ── Types ──────────────────────────────────────────────────────────────────

type SearchMode = "hashtag" | "keyword" | "deep"
type DeepMode   = "hashtag" | "keyword"

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtCount(n: number | undefined | null): string {
  const v = n ?? 0
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`
  if (v >= 1_000_000)     return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000)         return `${(v / 1_000).toFixed(1)}K`
  return v.toLocaleString("id-ID")
}

function fmtDuration(secs: number): string {
  if (!secs) return ""
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${m}:${s.toString().padStart(2, "0")}`
}

function relativeTime(isoOrTimestamp: string | number): string {
  let ts: number
  if (typeof isoOrTimestamp === "number") {
    ts = isoOrTimestamp * 1000
  } else {
    ts = new Date(isoOrTimestamp).getTime()
  }
  const diff = Date.now() - ts
  const day  = 86_400_000
  if (diff < day)       return "Hari ini"
  if (diff < 7 * day)   return `${Math.floor(diff / day)}h lalu`
  if (diff < 30 * day)  return `${Math.floor(diff / (7 * day))}mg lalu`
  if (diff < 365 * day) return `${Math.floor(diff / (30 * day))}bl lalu`
  return `${Math.floor(diff / (365 * day))}th lalu`
}

function statusColor(status: DeepSearchJob["status"]) {
  switch (status) {
    case "completed": return "text-emerald-400 bg-emerald-400/10 border-emerald-400/20"
    case "running":   return "text-ttcyan bg-ttcyan/10 border-ttcyan/20"
    case "queued":    return "text-yellow-400 bg-yellow-400/10 border-yellow-400/20"
    case "failed":    return "text-red-400 bg-red-400/10 border-red-400/20"
    case "cancelled": return "text-white/30 bg-white/5 border-white/10"
    default:          return "text-white/50"
  }
}

function statusIcon(status: DeepSearchJob["status"]) {
  switch (status) {
    case "completed": return <CheckCircle size={12} />
    case "running":   return <Loader2 size={12} className="animate-spin" />
    case "queued":    return <Clock size={12} />
    case "failed":    return <XCircle size={12} />
    case "cancelled": return <StopCircle size={12} />
    default:          return null
  }
}

// ── POPULAR HASHTAG CHIPS ──────────────────────────────────────────────────

const POPULAR_TAGS = [
  "fyp", "foryou", "viral", "trending",
  "kuliner", "exploreindonesia", "ootd",
  "travel", "beauty", "music",
]

// ══════════════════════════════════════════════════════════════════════════
// POST CARD COMPONENT
// ══════════════════════════════════════════════════════════════════════════

function PostCard({ post, index }: { post: SearchPost; index: number }) {
  const [imgErr, setImgErr] = useState(false)

  return (
    <div className="glass-card group relative overflow-hidden hover:border-ttcyan/30 transition-all duration-200">
      {/* Rank badge */}
      <div className="absolute top-3 left-3 z-10">
        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-black/60 text-white/60 backdrop-blur-sm">
          #{index + 1}
        </span>
      </div>

      {/* Thumbnail area */}
      <div className="relative bg-white/5 aspect-[9/14] overflow-hidden rounded-t-xl">
        {post.thumbnail_url && !imgErr ? (
          <img
            src={post.thumbnail_url}
            alt=""
            className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
            onError={() => setImgErr(true)}
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-gradient-to-b from-white/5 to-transparent">
            <Play size={28} className="text-white/20" />
            {post.duration > 0 && (
              <span className="text-xs text-white/30">{fmtDuration(post.duration)}</span>
            )}
          </div>
        )}

        {/* Duration overlay */}
        {post.duration > 0 && (
          <div className="absolute bottom-2 right-2 text-[10px] bg-black/70 text-white/80 px-1.5 py-0.5 rounded backdrop-blur-sm">
            {fmtDuration(post.duration)}
          </div>
        )}

        {/* Hover overlay: open video */}
        <a
          href={post.url}
          target="_blank"
          rel="noopener noreferrer"
          className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <div className="flex items-center gap-1.5 text-xs text-white font-medium bg-white/10 backdrop-blur-sm px-3 py-1.5 rounded-full border border-white/20">
            <ExternalLink size={12} /> Buka Video
          </div>
        </a>
      </div>

      {/* Content */}
      <div className="p-3">
        {/* Author */}
        <div className="flex items-center gap-1.5 mb-2">
          <div className="w-5 h-5 rounded-full bg-gradient-to-br from-ttred/40 to-ttcyan/40 flex items-center justify-center flex-shrink-0">
            <span className="text-[8px] text-white/80 font-bold">
              {(post.username?.[0] ?? "?").toUpperCase()}
            </span>
          </div>
          <span className="text-xs font-medium text-white/80 truncate">@{post.username}</span>
          {post.is_verified && (
            <CheckCircle size={10} className="text-ttcyan flex-shrink-0" />
          )}
        </div>

        {/* Caption */}
        {post.caption && (
          <p className="text-[11px] text-white/50 leading-relaxed line-clamp-2 mb-2">
            {post.caption}
          </p>
        )}

        {/* Hashtags */}
        {post.hashtags && post.hashtags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {post.hashtags.slice(0, 3).map((h, i) => (
              <span key={i} className="text-[10px] text-ttcyan/70 truncate max-w-[80px]">
                #{h}
              </span>
            ))}
            {post.hashtags.length > 3 && (
              <span className="text-[10px] text-white/30">+{post.hashtags.length - 3}</span>
            )}
          </div>
        )}

        {/* Music */}
        {post.music_title && (
          <div className="flex items-center gap-1 mb-2 text-[10px] text-white/30 truncate">
            <Music2 size={9} />
            <span className="truncate">{post.music_title}</span>
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-1 pt-2 border-t border-white/5">
          {[
            { icon: <Play size={9} />,           val: fmtCount(post.play_count),    color: "text-ttcyan" },
            { icon: <Heart size={9} />,           val: fmtCount(post.like_count),    color: "text-ttred" },
            { icon: <MessageCircle size={9} />,   val: fmtCount(post.comment_count), color: "text-white/50" },
            { icon: <Share2 size={9} />,           val: fmtCount(post.share_count),   color: "text-white/50" },
          ].map((s, i) => (
            <div key={i} className="flex flex-col items-center gap-0.5">
              <span className={`${s.color}`}>{s.icon}</span>
              <span className="text-[10px] text-white/60 font-medium">{s.val}</span>
            </div>
          ))}
        </div>

        {/* Source + time */}
        <div className="flex items-center justify-between mt-2">
          {post.search_source_tag && (
            <span className="text-[9px] text-white/25 truncate">
              #{post.search_source_tag.replace(/^hashtag_|^direct_/i, "")}
            </span>
          )}
          {post.create_time_iso && (
            <span className="text-[9px] text-white/25 ml-auto">
              {relativeTime(post.create_time_iso)}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// POSTS GRID
// ══════════════════════════════════════════════════════════════════════════

function PostsGrid({
  posts,
  onDownload,
  loading,
  filenameHint,
}: {
  posts: SearchPost[]
  onDownload: () => void
  loading: boolean
  filenameHint: string
}) {
  const [sortBy, setSortBy] = useState<"rank" | "likes" | "views" | "comments">("rank")
  const [filter, setFilter] = useState("")

  const sorted = [...posts]
    .filter(p =>
      !filter ||
      p.username?.toLowerCase().includes(filter.toLowerCase()) ||
      p.caption?.toLowerCase().includes(filter.toLowerCase()) ||
      p.hashtags?.some(h => h.toLowerCase().includes(filter.toLowerCase()))
    )
    .sort((a, b) => {
      switch (sortBy) {
        case "likes":    return (b.like_count ?? 0)    - (a.like_count ?? 0)
        case "views":    return (b.play_count ?? 0)    - (a.play_count ?? 0)
        case "comments": return (b.comment_count ?? 0) - (a.comment_count ?? 0)
        default:         return (a.rank ?? 0)          - (b.rank ?? 0)
      }
    })

  if (!posts.length) return null

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="glass-card p-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-white/60">
          <BarChart2 size={14} className="text-ttcyan" />
          <span className="font-medium text-white">{posts.length}</span> video ditemukan
        </div>

        {/* Filter */}
        <div className="flex-1 min-w-[160px] relative">
          <Filter size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-white/30" />
          <input
            type="text"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter username / caption / hashtag..."
            className="input-glass pl-8 py-1.5 text-xs w-full"
          />
          {filter && (
            <button onClick={() => setFilter("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60">
              <X size={12} />
            </button>
          )}
        </div>

        {/* Sort */}
        <div className="flex items-center gap-1">
          {(["rank", "likes", "views", "comments"] as const).map(s => (
            <button
              key={s}
              onClick={() => setSortBy(s)}
              className={`text-xs px-2.5 py-1 rounded-lg transition-all ${
                sortBy === s
                  ? "bg-ttcyan/20 text-ttcyan border border-ttcyan/30"
                  : "text-white/40 hover:text-white/70"
              }`}
            >
              {s === "rank" ? "Relevan" : s === "likes" ? "❤ Like" : s === "views" ? "▶ Views" : "💬 Komen"}
            </button>
          ))}
        </div>

        {/* Download */}
        <button
          onClick={onDownload}
          disabled={loading}
          className="btn-glass flex items-center gap-1.5 text-xs px-3 py-1.5 ml-auto"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
          CSV
        </button>
      </div>

      {filter && sorted.length === 0 && (
        <div className="text-center py-8 text-white/30 text-sm">
          Tidak ada post yang cocok dengan filter "<span className="text-white/50">{filter}</span>"
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
        {sorted.map((post, i) => (
          <PostCard key={post.video_id || i} post={post} index={i} />
        ))}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// DEEP SEARCH PROGRESS
// ══════════════════════════════════════════════════════════════════════════

function DeepSearchJobCard({
  job,
  onCancel,
  onDelete,
  onViewPosts,
  active,
}: {
  job: DeepSearchJob
  onCancel: (id: string) => void
  onDelete: (id: string) => void
  onViewPosts: (id: string) => void
  active: boolean
}) {
  const pct = job.progress?.percentage ?? 0

  return (
    <div className={`glass-card p-4 transition-all ${active ? "border-ttcyan/30" : ""}`}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium flex items-center gap-1 ${statusColor(job.status)}`}>
              {statusIcon(job.status)} {job.status.toUpperCase()}
            </span>
            <span className="text-[10px] text-white/30 bg-white/5 px-2 py-0.5 rounded-full">
              {job.mode === "hashtag" ? "#" : "🔍"} {job.mode}
            </span>
          </div>
          <p className="font-semibold text-sm text-white/90 truncate">
            {job.mode === "hashtag" ? "#" : ""}{job.query}
          </p>
          <p className="text-[10px] text-white/30 mt-0.5">
            ID: {job.job_id} · {job.created_at ? new Date(job.created_at).toLocaleString("id-ID") : ""}
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {job.status === "completed" && (
            <button
              onClick={() => onViewPosts(job.job_id)}
              className="text-xs px-2.5 py-1 rounded-lg bg-ttcyan/20 text-ttcyan border border-ttcyan/30 hover:bg-ttcyan/30 transition-colors flex items-center gap-1"
            >
              <Eye size={11} /> Lihat Posts
            </button>
          )}
          {(job.status === "running" || job.status === "queued") && (
            <button
              onClick={() => onCancel(job.job_id)}
              className="text-xs px-2 py-1 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors flex items-center gap-1"
            >
              <StopCircle size={11} /> Stop
            </button>
          )}
          {(job.status === "completed" || job.status === "failed" || job.status === "cancelled") && (
            <button
              onClick={() => onDelete(job.job_id)}
              className="text-xs p-1.5 rounded-lg text-white/30 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {(job.status === "running" || job.status === "queued") && (
        <div className="space-y-1.5">
          <div className="flex justify-between text-[10px] text-white/40">
            <span className="flex items-center gap-1.5">
              <Loader2 size={9} className="animate-spin text-ttcyan" />
              {job.progress?.current_hashtag
                ? `Sedang: #${job.progress.current_hashtag}`
                : "Menunggu..."}
            </span>
            <span>{pct}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-ttred to-ttcyan transition-all duration-500"
              style={{ width: `${Math.max(4, pct)}%` }}
            />
          </div>
          <div className="flex items-center gap-3 text-[10px] text-white/30">
            <span>📦 {job.progress?.total_posts ?? 0} post</span>
            <span>🔖 {job.progress?.hashtags_done ?? 0}/{job.progress?.hashtags_total ?? "?"} tag</span>
          </div>
        </div>
      )}

      {job.status === "completed" && (
        <div className="flex items-center gap-3 text-[11px] text-white/50 mt-1">
          <span className="flex items-center gap-1 text-emerald-400">
            <CheckCircle size={10} /> Selesai
          </span>
          <span>📦 {job.progress?.total_posts ?? "?"} post</span>
          {job.finished_at && (
            <span>🕒 {relativeTime(job.finished_at)}</span>
          )}
        </div>
      )}

      {job.status === "failed" && job.error && (
        <p className="text-[10px] text-red-400/70 mt-1 truncate">{job.error}</p>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ══════════════════════════════════════════════════════════════════════════

export default function TikTokSearchPage() {
  // Hanya tampilkan Deep Search pada UI — hashtag/keyword di-hide
  const [mode, setMode]         = useState<SearchMode>("deep")
  const [deepMode, setDeepMode] = useState<DeepMode>("hashtag")

  // Input state
  const [query, setQuery]             = useState("")
  const [maxPosts, setMaxPosts]       = useState(60)
  const [maxHashtags, setMaxHashtags] = useState(5)
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Deep search config
  const [maxRelated, setMaxRelated]   = useState(10)
  const [includeTop, setIncludeTop]   = useState(true)

  // Results
  const [posts, setPosts]             = useState<SearchPost[]>([])
  const [hashtagMeta, setHashtagMeta] = useState<Partial<HashtagSearchResult> | null>(null)
  const [keywordMeta, setKeywordMeta] = useState<Partial<KeywordSearchResult> | null>(null)
  const [suggested, setSuggested]     = useState<SuggestedHashtag[]>([])

  // Deep jobs
  const [deepJobs, setDeepJobs]             = useState<DeepSearchJob[]>([])
  const [deepJobsLoading, setDeepJobsLoading] = useState(false)
  const [activeDeepJobId, setActiveDeepJobId] = useState<string | null>(null)
  const deepPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // UI state
  const [loading, setLoading]   = useState(false)
  const [csvLoading, setCsvLoading] = useState(false)
  const [error, setError]       = useState("")
  const [warning, setWarning]   = useState("")

  // ── Load deep jobs on mount ─────────────────────────────────────────────

  const loadDeepJobs = useCallback(async () => {
    if (deepJobsLoading) return
    setDeepJobsLoading(true)
    try {
      const resp = await listDeepSearchJobs()
      if (resp.success) setDeepJobs(resp.data.jobs || [])
    } catch {
      // silent
    } finally {
      setDeepJobsLoading(false)
    }
  }, [deepJobsLoading])

  useEffect(() => {
    if (mode === "deep") loadDeepJobs()
  }, [mode]) // eslint-disable-line

  // ── Poll active deep job ───────────────────────────────────────────────

  useEffect(() => {
    if (!activeDeepJobId) return

    const poll = async () => {
      try {
        const resp = await getDeepSearchJob(activeDeepJobId)
        if (!resp.success) return

        const job = resp.data
        setDeepJobs(prev =>
          prev.map(j => (j.job_id === activeDeepJobId ? job : j))
        )

        if (["completed", "failed", "cancelled"].includes(job.status)) {
          setActiveDeepJobId(null)
          setLoading(false)
          if (job.status === "failed") {
            setError(`Deep search gagal: ${job.error || "unknown error"}`)
          }
          return
        }

        // Keep polling
        deepPollRef.current = setTimeout(poll, 3000)
      } catch {
        deepPollRef.current = setTimeout(poll, 5000)
      }
    }

    deepPollRef.current = setTimeout(poll, 2000)
    return () => {
      if (deepPollRef.current) clearTimeout(deepPollRef.current)
    }
  }, [activeDeepJobId])

  // ── Search handlers ────────────────────────────────────────────────────

  async function handleSearch() {
    const q = query.trim().replace(/^#/, "")
    if (!q) { setError("Masukkan hashtag atau keyword"); return }

    setError(""); setWarning(""); setLoading(true)
    setPosts([]); setHashtagMeta(null); setKeywordMeta(null)

    try {
      if (mode === "hashtag") {
        const resp = await searchHashtag(q, maxPosts)
        if (!resp.success) throw new Error(resp.message)
        const data = resp.data as HashtagSearchResult
        setPosts(data.posts || [])
        setHashtagMeta(data)
        // Also grab suggested from discover
        try {
          const disc = await discoverHashtags(q)
          if (disc.success) {
            setSuggested((disc.data as any)?.hashtags || [])
          }
        } catch { /* ok */ }

      } else if (mode === "keyword") {
        const resp = await searchKeyword(q, maxPosts, maxHashtags)
        if (!resp.success) throw new Error(resp.message)
        const data = resp.data as KeywordSearchResult
        setPosts(data.posts || [])
        setKeywordMeta(data)
        setSuggested(data.suggested_hashtags || [])
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Terjadi kesalahan")
    } finally {
      setLoading(false)
    }
  }

  async function handleDeepSearch() {
    const q = query.trim().replace(/^#/, "")
    if (!q) { setError("Masukkan hashtag atau keyword"); return }

    setError(""); setWarning(""); setLoading(true)

    try {
      let resp
      if (deepMode === "hashtag") {
        resp = await startDeepHashtagSearch(q, maxRelated, includeTop)
      } else {
        resp = await startDeepKeywordSearch(q, maxHashtags)
      }

      if (!resp.success) throw new Error(resp.message)

      const jobId = (resp.data as any).job_id
      const newJob: DeepSearchJob = {
        job_id:      jobId,
        mode:        deepMode,
        query:       q,
        status:      "queued",
        created_at:  new Date().toISOString(),
        started_at:  null,
        finished_at: null,
        error:       null,
        config:      {},
        progress: {
          total_posts:      0,
          hashtags_done:    0,
          hashtags_total:   deepMode === "hashtag" ? maxRelated : maxHashtags,
          current_hashtag:  null,
          percentage:       0,
        },
      }
      setDeepJobs(prev => [newJob, ...prev])
      setActiveDeepJobId(jobId)
      setWarning(`Deep search dimulai (Job ID: ${jobId})`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal memulai deep search")
      setLoading(false)
    }
  }

  async function handleViewJobPosts(jobId: string) {
    setLoading(true)
    setError("")
    setPosts([]); setHashtagMeta(null); setKeywordMeta(null)
    try {
      const resp = await getDeepSearchJobPosts(jobId)
      if (!resp.success) throw new Error(resp.message)
      setPosts((resp.data as any).posts || [])
      setWarning(`Menampilkan hasil deep search job: ${jobId}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal memuat posts")
    } finally {
      setLoading(false)
    }
  }

  async function handleCancelJob(jobId: string) {
    try {
      await cancelDeepSearchJob(jobId)
      if (activeDeepJobId === jobId) {
        setActiveDeepJobId(null)
        setLoading(false)
      }
      await loadDeepJobs()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal cancel job")
    }
  }

  async function handleDeleteJob(jobId: string) {
    try {
      await deleteDeepSearchJob(jobId)
      setDeepJobs(prev => prev.filter(j => j.job_id !== jobId))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal hapus job")
    }
  }

  async function handleDownloadCsv() {
    if (!posts.length) return
    setCsvLoading(true)
    try {
      const hint = mode === "hashtag"
        ? `tiktok_tag_${query.replace(/^#/, "")}`
        : `tiktok_kw_${query}`
      await downloadSearchCsv(posts, hint)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Download gagal")
    } finally {
      setCsvLoading(false)
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────

  const isDeep    = mode === "deep"
  const canSearch = !loading

  return (
    <div className="p-8 max-w-7xl">

      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-ttred/30 to-ttcyan/30 flex items-center justify-center border border-white/10">
          <Search size={20} className="text-white/80" />
        </div>
        <div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-display)" }}>
            TikTok Search
          </h1>
          <p className="text-sm text-white/40">Cari postingan via hashtag, keyword, atau deep search</p>
        </div>
      </div>

      {/* Mode Tabs: hanya Deep Search ditampilkan */}
      <div className="glass-card p-1 inline-flex mb-6 gap-1">
        <button
          onClick={() => { setMode("deep"); setError(""); setWarning("") }}
          className={`flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-medium transition-all bg-gradient-to-r from-ttred/20 to-ttcyan/20 text-white border border-ttcyan/20`}
        >
          🚀 Deep Search
        </button>
      </div>

      {/* Search Card */}
      <div className="glass-card p-6 mb-6">

        {/* Deep mode sub-toggle */}
        {isDeep && (
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-white/40 uppercase tracking-widest">Mode:</span>
            <div className="glass-card p-0.5 inline-flex gap-0.5">
              {(["hashtag", "keyword"] as DeepMode[]).map(dm => (
                <button
                  key={dm}
                  onClick={() => setDeepMode(dm)}
                  className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    deepMode === dm ? "bg-white/10 text-white" : "text-white/40 hover:text-white/60"
                  }`}
                >
                  {dm === "hashtag" ? "# Hashtag" : "🔍 Keyword"}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input */}
        <div className="mb-4">
          <label className="block text-xs text-white/50 mb-2 uppercase tracking-widest">
            {isDeep
              ? deepMode === "hashtag" ? "Hashtag (tanpa #)" : "Keyword"
              : mode === "hashtag" ? "Hashtag TikTok" : "Keyword Pencarian"}
          </label>
          <div className="relative">
            {(!isDeep && mode === "hashtag" || (isDeep && deepMode === "hashtag")) && (
              <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30 text-lg font-light select-none">
                #
              </span>
            )}
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && canSearch && (isDeep ? handleDeepSearch() : handleSearch())}
              disabled={loading}
              placeholder={
                isDeep
                  ? deepMode === "hashtag" ? "kuliner, fyp, viral..." : "makanan enak, ootd style..."
                  : mode === "hashtag" ? "kuliner, fyp, viral..." : "makanan enak jakarta, ootd style..."
              }
              className={`input-glass w-full ${
                (!isDeep && mode === "hashtag") || (isDeep && deepMode === "hashtag") ? "pl-9" : "pl-4"
              } py-3 text-base`}
            />
          </div>
        </div>

        {/* Popular hashtag chips (hashtag mode only) */}
        {(mode === "hashtag" || (isDeep && deepMode === "hashtag")) && (
          <div className="flex flex-wrap gap-2 mb-4">
            {POPULAR_TAGS.map(tag => (
              <button
                key={tag}
                onClick={() => setQuery(tag)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-all ${
                  query.replace(/^#/, "") === tag
                    ? "bg-ttcyan/20 border-ttcyan/40 text-ttcyan"
                    : "border-white/10 text-white/40 hover:border-white/20 hover:text-white/60"
                }`}
              >
                #{tag}
              </button>
            ))}
          </div>
        )}

        {/* Advanced settings toggle */}
        <button
          onClick={() => setShowAdvanced(v => !v)}
          className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white/60 transition-colors mb-3"
        >
          <Filter size={12} />
          Pengaturan lanjutan
          {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>

        {showAdvanced && (
          <div className="glass rounded-xl p-4 mb-4 space-y-3">
            {/* Max posts */}
            {!isDeep && (
              <div>
                <label className="block text-xs text-white/50 mb-2">
                  Max Posts: <span className="text-white/80">{maxPosts}</span>
                  <span className="text-white/30 ml-1">(max 300)</span>
                </label>
                <input
                  type="range" min={10} max={300} step={10} value={maxPosts}
                  onChange={e => setMaxPosts(Number(e.target.value))}
                  className="w-full accent-ttcyan h-1.5"
                />
              </div>
            )}

            {/* Max hashtags (keyword mode) */}
            {(mode === "keyword" || (isDeep && deepMode === "keyword")) && (
              <div>
                <label className="block text-xs text-white/50 mb-2">
                  Max Hashtags yang di-scrape: <span className="text-white/80">{maxHashtags}</span>
                </label>
                <input
                  type="range" min={1} max={10} step={1} value={maxHashtags}
                  onChange={e => setMaxHashtags(Number(e.target.value))}
                  className="w-full accent-ttcyan h-1.5"
                />
              </div>
            )}

            {/* Deep search specific */}
            {isDeep && deepMode === "hashtag" && (
              <>
                <div>
                  <label className="block text-xs text-white/50 mb-2">
                    Max Related Hashtags: <span className="text-white/80">{maxRelated}</span>
                  </label>
                  <input
                    type="range" min={3} max={20} step={1} value={maxRelated}
                    onChange={e => setMaxRelated(Number(e.target.value))}
                    className="w-full accent-ttred h-1.5"
                  />
                </div>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={includeTop}
                    onChange={e => setIncludeTop(e.target.checked)}
                    className="rounded bg-white/10 border-white/20 accent-ttcyan"
                  />
                  <span className="text-xs text-white/70">Include top posts dari hashtag utama</span>
                </label>
              </>
            )}
          </div>
        )}

        {/* CTA Button */}
        <button
          onClick={isDeep ? handleDeepSearch : handleSearch}
          disabled={!canSearch}
          className={`w-full flex items-center justify-center gap-2 py-3 rounded-2xl font-semibold text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
            isDeep
              ? "bg-gradient-to-r from-ttred/80 to-ttcyan/80 hover:from-ttred hover:to-ttcyan text-white"
              : "btn-tt"
          }`}
        >
          {loading ? (
            <><Loader2 size={16} className="animate-spin" /> {isDeep ? "Memulai..." : "Mencari..."}</>
          ) : isDeep ? (
            <><Zap size={16} /> Mulai Deep Search</>
          ) : (
            <><Search size={16} /> {mode === "hashtag" ? "Cari Hashtag" : "Cari Keyword"}</>
          )}
        </button>

        {/* Warning & Error */}
        {warning && (
          <div className="mt-3 flex items-center gap-2 text-yellow-300 text-xs glass rounded-xl px-3 py-2.5">
            <Clock size={13} className="flex-shrink-0" /> {warning}
          </div>
        )}
        {error && (
          <div className="mt-3 flex items-start gap-2 text-red-400 text-xs glass rounded-xl px-3 py-2.5">
            <AlertCircle size={13} className="flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Error</p>
              <p className="text-red-400/70 mt-0.5">{error}</p>
            </div>
          </div>
        )}
      </div>

      {/* ─── DEEP SEARCH JOBS LIST ────────────────────────────────────────── */}
      {mode === "deep" && (
        <div className="mb-6 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white/50 uppercase tracking-widest flex items-center gap-2">
              <Sparkles size={14} className="text-ttcyan" /> Deep Search Jobs
            </h2>
            <button
              onClick={loadDeepJobs}
              disabled={deepJobsLoading}
              className="btn-glass text-xs flex items-center gap-1.5 px-3 py-1.5"
            >
              <RefreshCw size={11} className={deepJobsLoading ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>

          {deepJobs.length === 0 && (
            <div className="glass-card p-8 text-center">
              <Zap size={28} className="text-white/10 mx-auto mb-3" />
              <p className="text-white/30 text-sm">Belum ada deep search job.</p>
              <p className="text-white/20 text-xs mt-1">Mulai search di atas untuk membuat job baru.</p>
            </div>
          )}

          {deepJobs.map(job => (
            <DeepSearchJobCard
              key={job.job_id}
              job={job}
              onCancel={handleCancelJob}
              onDelete={handleDeleteJob}
              onViewPosts={handleViewJobPosts}
              active={job.job_id === activeDeepJobId}
            />
          ))}
        </div>
      )}

      {/* ─── QUICK RESULTS META ────────────────────────────────────────────── */}
      {!isDeep && (hashtagMeta || keywordMeta) && (
        <div className="glass-card p-4 mb-5 flex flex-wrap items-center gap-x-6 gap-y-2">
          {hashtagMeta && (
            <>
              <div>
                <p className="text-lg font-bold text-white">
                  #{hashtagMeta.hashtag}
                </p>
                <p className="text-[10px] text-white/30">hashtag</p>
              </div>
              {hashtagMeta.challenge_info?.video_count ? (
                <div>
                  <p className="font-semibold text-ttcyan">{fmtCount(hashtagMeta.challenge_info.video_count)}</p>
                  <p className="text-[10px] text-white/30">total video</p>
                </div>
              ) : null}
              {hashtagMeta.challenge_info?.view_count ? (
                <div>
                  <p className="font-semibold text-ttcyan">{fmtCount(hashtagMeta.challenge_info.view_count)}</p>
                  <p className="text-[10px] text-white/30">total views</p>
                </div>
              ) : null}
              <div>
                <p className="font-semibold text-white">{hashtagMeta.total_fetched ?? posts.length}</p>
                <p className="text-[10px] text-white/30">berhasil diambil</p>
              </div>
              {hashtagMeta.method && (
                <div className="ml-auto">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-white/30 border border-white/10">
                    via {hashtagMeta.method}
                  </span>
                </div>
              )}
            </>
          )}
          {keywordMeta && (
            <>
              <div>
                <p className="text-lg font-bold text-white">"{keywordMeta.query}"</p>
                <p className="text-[10px] text-white/30">keyword</p>
              </div>
              <div>
                <p className="font-semibold text-white">{keywordMeta.total_fetched ?? posts.length}</p>
                <p className="text-[10px] text-white/30">post ditemukan</p>
              </div>
              {(keywordMeta.searched_hashtags?.length ?? 0) > 0 && (
                <div>
                  <p className="font-semibold text-ttcyan">{keywordMeta.searched_hashtags!.length}</p>
                  <p className="text-[10px] text-white/30">hashtag di-scrape</p>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ─── SUGGESTED HASHTAGS ────────────────────────────────────────────── */}
      {suggested.length > 0 && !isDeep && (
        <div className="glass-card p-4 mb-5">
          <p className="text-xs text-white/40 uppercase tracking-widest mb-3 flex items-center gap-1.5">
            <TrendingUp size={12} /> Hashtag Terkait
          </p>
          <div className="flex flex-wrap gap-2">
            {suggested.slice(0, 15).map((h, i) => (
              <button
                key={i}
                onClick={() => {
                  setQuery(h.name)
                  setMode("hashtag")
                }}
                className="text-xs px-3 py-1 rounded-full border border-white/10 text-white/50 hover:border-ttcyan/40 hover:text-ttcyan transition-all"
              >
                #{h.name}
                {h.video_count ? (
                  <span className="text-white/25 ml-1.5">{fmtCount(h.video_count)}</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ─── LOADING SPINNER ───────────────────────────────────────────────── */}
      {loading && !isDeep && (
        <div className="glass-card p-12 text-center mb-6">
          <div className="relative w-14 h-14 mx-auto mb-4">
            <TikTokLogo size={56} className="opacity-20" />
            <div className="absolute inset-0 animate-spin" style={{ animationDuration: "1.5s" }}>
              <div className="w-full h-full rounded-full border-2 border-transparent border-t-ttcyan border-r-ttred" />
            </div>
          </div>
          <p className="text-white/50 text-sm">
            {mode === "hashtag" ? `Mencari video untuk #${query}...` : `Mencari keyword "${query}"...`}
          </p>
          <p className="text-white/25 text-xs mt-1">Ini mungkin butuh 30–90 detik</p>
        </div>
      )}

      {/* ─── RESULTS GRID ───────────────────────────────────────────────────── */}
      {posts.length > 0 && (
        <PostsGrid
          posts={posts}
          onDownload={handleDownloadCsv}
          loading={csvLoading}
          filenameHint={`tiktok_${mode}_${query}`}
        />
      )}

      {/* ─── EMPTY STATE ────────────────────────────────────────────────────── */}
      {!loading && posts.length === 0 && !isDeep && (hashtagMeta || keywordMeta) && (
        <div className="glass-card p-10 text-center">
          <div className="w-14 h-14 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-4">
            <Search size={24} className="text-white/20" />
          </div>
          <p className="text-white/40 text-sm">Tidak ada post ditemukan</p>
          <p className="text-white/25 text-xs mt-1">
            Coba hashtag atau keyword lain, atau periksa session TikTok kamu
          </p>
        </div>
      )}

      {/* ─── INITIAL EMPTY (no search yet) ────────────────────────────────── */}
      {!loading && posts.length === 0 && !hashtagMeta && !keywordMeta && !isDeep && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-ttred/20 to-ttcyan/20 flex items-center justify-center mb-5 border border-white/10">
            <Hash size={36} className="text-white/30" />
          </div>
          <p className="text-white/40 text-base font-medium mb-2">
            {mode === "hashtag"
              ? "Masukkan hashtag untuk melihat postingan"
              : "Masukkan keyword untuk mencari video"}
          </p>
          <p className="text-white/20 text-sm">
            {mode === "hashtag"
              ? "Contoh: kuliner, exploreindonesia, ootd"
              : "Contoh: makanan enak jakarta, style ootd wanita"}
          </p>
          {/* Quick chips */}
          <div className="flex flex-wrap gap-2 justify-center mt-6 max-w-md">
            {POPULAR_TAGS.slice(0, 6).map(tag => (
              <button
                key={tag}
                onClick={() => { setQuery(tag); setMode("hashtag") }}
                className="text-sm px-3 py-1.5 rounded-full border border-white/10 text-white/40 hover:border-ttcyan/40 hover:text-ttcyan transition-all"
              >
                #{tag}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}