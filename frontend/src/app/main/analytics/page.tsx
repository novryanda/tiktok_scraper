"use client"

import { useState, useEffect } from "react"
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell,
} from "recharts"
import { BarChart3, RefreshCw, MessageSquare, Film, Loader2 } from "lucide-react"
import { listOutputFiles, getOutputFile } from "@/lib/api"
import type { VideoResult, SentimentSummary, OutputFile } from "@/lib/types"

// ── Local types ───────────────────────────────────────────────

type SentimentAgg = {
  positive: number
  negative: number
  neutral: number
  humor: number
  toxic: number
  hate: number
}

type AnalyticsData = {
  total_videos: number
  total_comments: number
  sentiment: SentimentAgg
  positive_percentage: number
  top_videos: VideoResult[]
}

// ── Type guard ────────────────────────────────────────────────
// FIX: tidak pakai `obj.followers === undefined` karena VideoResult
// tidak punya field followers — guard berdasarkan field yang PASTI ada
function isVideoResult(obj: unknown): obj is VideoResult {
  if (!obj || typeof obj !== "object") return false
  const o = obj as Record<string, unknown>
  // VideoResult pasti punya video_id (string) atau username (string)
  // dan TIDAK punya field "followers" (itu ProfileResult)
  // dan TIDAK punya field "results" berupa array (itu BatchResult)
  const hasVideoField =
    typeof o.video_id === "string" ||
    typeof o.username === "string" ||
    typeof o.description === "string"
  const isProfile = typeof o.followers === "number"
  const isBatch = Array.isArray(o.results)
  return hasVideoField && !isProfile && !isBatch
}

// ── Extract videos dari satu file output ──────────────────────
function extractVideos(fileData: unknown): VideoResult[] {
  if (!fileData || typeof fileData !== "object") return []
  const data = fileData as Record<string, unknown>

  // Batch: { total, success, results: [{ url, success, data }] }
  if (Array.isArray(data.results)) {
    return (data.results as unknown[])
      .filter(
        (r): r is { success: boolean; data: unknown } =>
          typeof r === "object" &&
          r !== null &&
          (r as Record<string, unknown>).success === true &&
          (r as Record<string, unknown>).data !== undefined
      )
      .map((r) => r.data)
      .filter(isVideoResult)
  }

  // Profile (punya followers number) → bukan video, skip
  if (typeof data.followers === "number") return []

  // Single video
  if (isVideoResult(fileData)) return [fileData]

  return []
}

// ── Hitung comments_count dengan safe fallback ────────────────
// FIX: comments_count bisa undefined di data lama sebelum fix backend
function safeCommentsCount(v: VideoResult): number {
  if (typeof v.comments_count === "number") return v.comments_count
  if (Array.isArray(v.comments)) return v.comments.length
  return 0
}

// ── Aggregate semua video jadi satu AnalyticsData ─────────────
function aggregateVideos(videos: VideoResult[]): AnalyticsData {
  const totalComments = videos.reduce((s, v) => s + safeCommentsCount(v), 0)

  // Weighted sentiment berdasarkan total komentar per video
  const summaries = videos
    .map((v) => v.sentiment_summary)
    .filter((s): s is SentimentSummary => !!s)

  const sentTotal = summaries.reduce((s, c) => s + (c.total_comments || 0), 0)

  const EMPTY_AGG: SentimentAgg = {
    positive: 0, negative: 0, neutral: 0,
    humor: 0, toxic: 0, hate: 0,
  }

  const sentiment: SentimentAgg =
    sentTotal > 0
      ? {
          positive: Math.round(
            (summaries.reduce((s, c) => s + (c.positive_count || 0), 0) / sentTotal) * 100
          ),
          negative: Math.round(
            (summaries.reduce((s, c) => s + (c.negative_count || 0), 0) / sentTotal) * 100
          ),
          neutral: Math.round(
            (summaries.reduce((s, c) => s + (c.neutral_count || 0), 0) / sentTotal) * 100
          ),
          humor: Math.round(
            (summaries.reduce((s, c) => s + (c.humor_count || 0), 0) / sentTotal) * 100
          ),
          toxic: Math.round(
            (summaries.reduce((s, c) => s + (c.toxic_count || 0), 0) / sentTotal) * 100
          ),
          hate: Math.round(
            (summaries.reduce((s, c) => s + (c.hate_speech_count || 0), 0) / sentTotal) * 100
          ),
        }
      : EMPTY_AGG

  const topVideos = [...videos]
    .sort((a, b) => safeCommentsCount(b) - safeCommentsCount(a))
    .slice(0, 5)

  return {
    total_videos: videos.length,
    total_comments: totalComments,
    sentiment,
    positive_percentage: sentiment.positive,
    top_videos: topVideos,
  }
}

// ── Chart data type ───────────────────────────────────────────
type ChartEntry = { name: string; value: number; color: string }

// ── Component ─────────────────────────────────────────────────
export default function AnalyticsPage() {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const filesResp = await listOutputFiles()
      if (!filesResp.success) {
        setError(filesResp.message || "Gagal memuat daftar file")
        return
      }

      // Filter file video TikTok, abaikan profile
      const videoFiles: OutputFile[] = filesResp.data.files
        .filter(
          (f: OutputFile) =>
            (f.name.startsWith("api_video") ||
              f.name.startsWith("api_batch") ||
              f.name.startsWith("tiktok_")) &&
            !f.name.includes("profile")
        )
        .slice(0, 20)

      const rawFiles = await Promise.all(
        videoFiles.map((f: OutputFile) =>
          getOutputFile(f.name).catch(() => null)
        )
      )

      // FIX: filter null dulu sebelum extractVideos
      const videos: VideoResult[] = rawFiles
        .filter((f): f is NonNullable<typeof f> => f !== null)
        .flatMap(extractVideos)

      if (videos.length === 0) {
        setData(null)
        return
      }

      setData(aggregateVideos(videos))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Terjadi kesalahan")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const chartData: ChartEntry[] = data
    ? [
        { name: "Positif", value: data.sentiment.positive, color: "#22c55e" },
        { name: "Negatif", value: data.sentiment.negative, color: "#f87171" },
        { name: "Netral",  value: data.sentiment.neutral,  color: "#94a3b8" },
        { name: "Humor",   value: data.sentiment.humor,    color: "#818cf8" },
        { name: "Toxic",   value: data.sentiment.toxic,    color: "#fde047" },
        { name: "Hate",    value: data.sentiment.hate,     color: "#ef4444" },
      ]
    : []

  // ── Render ─────────────────────────────────────────────────
  return (
    <div className="p-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <BarChart3 size={32} className="text-ttcyan" />
          <div>
            <h1
              className="text-2xl font-bold"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Analytics
            </h1>
            <p className="text-sm text-white/40">
              Agregat sentimen dari semua video ter-scrape
            </p>
          </div>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="btn-glass flex items-center gap-2 text-sm"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="glass-card p-4 mb-6 border border-red-500/30 bg-red-500/10">
          <p className="text-red-400 text-sm">❌ {error}</p>
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <Loader2 size={32} className="animate-spin mx-auto mb-3 text-ttcyan" />
            <p className="text-white/40 text-sm">Memuat data analytics...</p>
          </div>
        </div>
      ) : !data || data.total_videos === 0 ? (
        /* Empty state */
        <div className="glass-card p-12 text-center text-white/30">
          <BarChart3 size={48} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">
            Belum ada data video. Scrape dulu di halaman Scrape Video.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="glass-card p-5 flex items-center gap-4">
              <Film size={28} className="text-ttcyan" />
              <div>
                <p className="text-2xl font-bold">{data.total_videos}</p>
                <p className="text-xs text-white/40">video dianalisis</p>
              </div>
            </div>
            <div className="glass-card p-5 flex items-center gap-4">
              <MessageSquare size={28} className="text-ttred" />
              <div>
                <p className="text-2xl font-bold">
                  {data.total_comments.toLocaleString("id-ID")}
                </p>
                <p className="text-xs text-white/40">total komentar</p>
              </div>
            </div>
            <div className="glass-card p-5 flex items-center gap-4">
              <span className="text-3xl">😊</span>
              <div>
                <p className="text-2xl font-bold text-emerald-400">
                  {data.positive_percentage}%
                </p>
                <p className="text-xs text-white/40">positif keseluruhan</p>
              </div>
            </div>
          </div>

          {/* Bar Chart */}
          <div className="glass-card p-6">
            <h3 className="font-semibold mb-4 text-sm uppercase tracking-widest text-white/50">
              Distribusi Sentimen Agregat
            </h3>
            <div style={{ width: "100%", height: 320 }}>
              <ResponsiveContainer width="100%" height={320} debounce={50}>
                <BarChart data={chartData}>
                  <XAxis
                    dataKey="name"
                    tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(255,255,255,0.04)" }}
                    contentStyle={{
                      background: "rgba(0,0,0,0.85)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 12,
                      fontSize: 12,
                      color: "#fff",
                    }}
                    formatter={(value: number) => [`${value}%`, ""]}
                  />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]} animationDuration={800}>
                    {chartData.map((d, i) => (
                      <Cell key={i} fill={d.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Breakdown bars */}
          <div className="glass-card p-6">
            <h3 className="font-semibold mb-4 text-sm uppercase tracking-widest text-white/50">
              Breakdown Sentimen
            </h3>
            <div className="space-y-3">
              {chartData.map((item) => (
                <div key={item.name}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-white/70">{item.name}</span>
                    <span className="text-white/50">{item.value}%</span>
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{ width: `${item.value}%`, background: item.color }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Videos */}
          <div className="glass-card p-6">
            <h3 className="font-semibold mb-4 text-sm uppercase tracking-widest text-white/50">
              Video Teratas (komentar terbanyak)
            </h3>
            <div className="space-y-2">
              {data.top_videos.map((v, i) => {
                // FIX: safe access semua field — video lama mungkin tidak punya semua field
                const cc = safeCommentsCount(v)
                const posPct = v.sentiment_summary?.positive_percentage ?? 0
                const label = v.username
                  ? `@${v.username}`
                  : v.video_id
                    ? `ID: ${v.video_id}`
                    : `Video #${i + 1}`
                const sub = v.description || v.url || ""

                return (
                  <div
                    key={i}
                    className="glass rounded-xl px-4 py-3 flex items-center justify-between gap-4"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{label}</p>
                      {sub && (
                        <p className="text-xs text-white/40 truncate">{sub}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-4 text-xs flex-shrink-0">
                      <span className="text-white/60">
                        {cc.toLocaleString("id-ID")} 💬
                      </span>
                      <span className="text-emerald-400">
                        {posPct}% 😊
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}