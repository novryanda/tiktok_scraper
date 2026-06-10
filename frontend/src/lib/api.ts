// lib/api.ts — Komunikasi ke FastAPI Bridge TikTok (Job System v3 + Search)

import type {
  ApiResponse,
  VideoResult,
  ProfileResult,
  OutputFile,
  TrackedProfile,
  BatchScrapeData,
  TopLikedComment,
  JobStartResponse,
  Job,
  JobSummary,
  SearchPost,
  DiscoverResult,
  HashtagSearchResult,
  KeywordSearchResult,
  DeepSearchJob,
  DeepJobPostsResult,
  DeepSearchStartResponse,
} from "./types"

// Jika NEXT_PUBLIC_API_URL di-set (dev lokal), pakai nilainya.
// Jika kosong (Docker / production), pakai "" → relative URL → Next.js rewrites proxy ke backend.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

// ── URL SANITIZER ─────────────────────────────────────────────────────────
// Ekstrak username dari URL TikTok apapun formatnya, strip query params.
// Contoh input yang didukung:
//   https://www.tiktok.com/@prabowosubianto08?lang=id-ID  → prabowosubianto08
//   @prabowosubianto08                                    → prabowosubianto08
//   prabowosubianto08                                     → prabowosubianto08

export function sanitizeTikTokUsername(raw: string): string {
  const trimmed = (raw ?? "").trim()
  if (!trimmed) return ""

  // Kalau berupa URL TikTok — ambil username dari path @xxx
  const urlMatch = trimmed.match(/tiktok\.com\/@([^/?&#\s]+)/i)
  if (urlMatch) return urlMatch[1]

  // Bukan URL — strip @ di depan jika ada
  return trimmed.replace(/^@+/, "")
}

// ── REQUEST HELPER ────────────────────────────────────────────────────────

async function req<T>(path: string, init?: RequestInit): Promise<ApiResponse<T>> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })

  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    /* ignore parse error */
  }

  if (!res.ok) {
    const b = body as Record<string, unknown> | null
    const msg = b?.detail ?? b?.message ?? `HTTP ${res.status}`
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg))
  }

  return body as ApiResponse<T>
}

// ── SCRAPE (async — balas job_id) ─────────────────────────────────────────

export function scrapeVideo(url: string, maxComments: number) {
  return req<JobStartResponse>("/api/scrape/video", {
    method: "POST",
    body: JSON.stringify({ url, max_comments: maxComments }),
  })
}

export function scrapeVideos(urls: string[], maxComments: number) {
  return req<JobStartResponse>("/api/scrape/videos/batch", {
    method: "POST",
    body: JSON.stringify({ urls, max_comments: maxComments }),
  })
}

// Sanitize username/URL sebelum dikirim ke backend
export function scrapeProfile(usernameOrUrl: string) {
  const username = sanitizeTikTokUsername(usernameOrUrl)
  if (!username) throw new Error("Username tidak valid")

  return req<JobStartResponse>("/api/scrape/profile", {
    method: "POST",
    body: JSON.stringify({ username }),
  })
}

export function scrapeVideoUnified(
  url: string,
  maxComments: number,
  includeReplies: boolean,
  maxReplies: number,
  scrapeLikers: boolean,
  maxLikers: number
) {
  return req<JobStartResponse>("/api/scrape/video/unified", {
    method: "POST",
    body: JSON.stringify({
      url,
      max_comments: maxComments,
      include_replies: includeReplies,
      max_replies_per_comment: maxReplies,
      scrape_likers: scrapeLikers,
      max_likers: maxLikers,
    }),
  })
}

export function scrapeVideoCheckpoint(
  url: string,
  batchSize = 300,
  maxTotal = 2000,
  sortType = 0,
  cooldownMin = 10,
  cooldownMax = 20,
  analyzeSentiment = true
) {
  return req<JobStartResponse>("/api/scrape/video/checkpoint", {
    method: "POST",
    body: JSON.stringify({
      url,
      batch_size: batchSize,
      max_total: maxTotal,
      sort_type: sortType,
      cooldown_min: cooldownMin,
      cooldown_max: cooldownMax,
      analyze_sentiment: analyzeSentiment,
    }),
  })
}

// ── JOB POLLING ───────────────────────────────────────────────────────────

export function getJob<T = unknown>(jobId: string) {
  return req<Job<T>>(`/api/jobs/${encodeURIComponent(jobId)}`)
}

export function listJobs() {
  return req<{ jobs: JobSummary[]; count: number }>("/api/jobs")
}

export async function pollJob<T = unknown>(
  jobId: string,
  opts?: {
    intervalMs?: number
    timeoutMs?: number
    onProgress?: (job: Job<T>) => void
    signal?: AbortSignal
  }
): Promise<Job<T>> {
  const interval = opts?.intervalMs ?? 2000
  const timeout = opts?.timeoutMs ?? 15 * 60 * 1000
  const start = Date.now()

  while (true) {
    if (opts?.signal?.aborted) throw new Error("Polling dibatalkan")
    if (Date.now() - start > timeout) throw new Error("Polling timeout")

    const resp = await getJob<T>(jobId)
    const job = resp.data
    opts?.onProgress?.(job)

    if (job.status === "done" || job.status === "error") {
      return job
    }
    await new Promise((r) => setTimeout(r, interval))
  }
}

// ── TOP 5 LIKED ───────────────────────────────────────────────────────────

export function getTop5LatestVideo() {
  return req<{
    file: string
    video_id: string
    username: string
    top_5_liked_comments: TopLikedComment[]
  }>("/api/scrape/video/top5")
}

export function getTop5FromFile(filename: string) {
  return req<{
    file: string
    video_id: string
    username: string
    top_5_liked_comments: TopLikedComment[]
  }>(`/api/scrape/video/top5/${encodeURIComponent(filename)}`)
}

// ── FILES ─────────────────────────────────────────────────────────────────

export function listOutputFiles() {
  return req<{ files: OutputFile[]; count: number }>("/api/files")
}

export async function getOutputFile(filename: string): Promise<unknown> {
  const res = await fetch(`${BASE}/api/files/${encodeURIComponent(filename)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// ── PROFILES (growth tracking) ────────────────────────────────────────────

export function listProfiles() {
  return req<{ users: TrackedProfile[]; count: number }>("/api/profiles")
}

// ── SESSION / HEALTH ──────────────────────────────────────────────────────

export function getSession() {
  return req<{ valid: boolean; info?: unknown; error?: string }>("/api/session")
}

export function getHealth() {
  return req<Record<string, unknown>>("/api/health")
}

// ── ANALYTICS ─────────────────────────────────────────────────────────────

export function getAnalytics() {
  return req<{
    total_videos: number
    total_comments: number
    sentiment: {
      positive: number
      negative: number
      neutral: number
      humor: number
      toxic: number
      hate: number
    }
    positive_percentage: number
    top_videos: VideoResult[]
  }>("/api/analytics")
}

// ── COOKIES ───────────────────────────────────────────────────────────────

export function saveCookies(cookiesJson: string, username = "") {
  return req<{
    saved: boolean
    total_cookies: number
    has_sessionid: boolean
  }>("/api/cookies", {
    method: "POST",
    body: JSON.stringify({ cookies_json: cookiesJson, username }),
  })
}

export function getCookieStatus() {
  return req<{
    valid: boolean
    exists: boolean
    total_cookies?: number
    username?: string
    saved_at?: string
    error?: string
  }>("/api/cookies")
}

export function deleteCookies() {
  return req<{ deleted: boolean }>("/api/cookies", { method: "DELETE" })
}

// ════════════════════════════════════════════════════════════════
// SEARCH API (tiktok_search_endpoints.py)
// ════════════════════════════════════════════════════════════════

/** Temukan saran hashtag & user dari sebuah keyword. */
export function discoverHashtags(query: string) {
  return req<DiscoverResult>("/api/search/discover", {
    method: "POST",
    body: JSON.stringify({ query }),
  })
}

/** Scrape video dari sebuah hashtag TikTok (blocking). */
export function searchHashtag(hashtag: string, maxPosts = 60) {
  return req<HashtagSearchResult>("/api/search/hashtag", {
    method: "POST",
    body: JSON.stringify({ hashtag, max_posts: maxPosts }),
  })
}

/** Cari video berdasarkan keyword. */
export function searchKeyword(keyword: string, maxPosts = 60, maxHashtags = 5) {
  return req<KeywordSearchResult>("/api/search/keyword", {
    method: "POST",
    body: JSON.stringify({ keyword, max_posts: maxPosts, max_hashtags: maxHashtags }),
  })
}

// ── DEEP SEARCH (background jobs) ─────────────────────────────────────────

export function startDeepHashtagSearch(
  hashtag: string,
  maxRelatedHashtags = 10,
  includeTop = true,
  maxPostsPerHashtag = 300
) {
  return req<DeepSearchStartResponse>("/api/search/deep/hashtag", {
    method: "POST",
    body: JSON.stringify({
      hashtag,
      max_related_hashtags: maxRelatedHashtags,
      include_top: includeTop,
      max_posts_per_hashtag: maxPostsPerHashtag,
    }),
  })
}

export function startDeepKeywordSearch(
  keyword: string,
  maxHashtags = 5,
  maxPostsPerHashtag = 150
) {
  return req<DeepSearchStartResponse>("/api/search/deep/keyword", {
    method: "POST",
    body: JSON.stringify({
      keyword,
      max_hashtags: maxHashtags,
      max_posts_per_hashtag: maxPostsPerHashtag,
    }),
  })
}

export function listDeepSearchJobs() {
  return req<{ jobs: DeepSearchJob[]; count: number }>("/api/search/deep/jobs")
}

export function getDeepSearchJob(jobId: string) {
  return req<DeepSearchJob>(`/api/search/deep/jobs/${encodeURIComponent(jobId)}`)
}

export function getDeepSearchJobPosts(jobId: string) {
  return req<DeepJobPostsResult>(
    `/api/search/deep/jobs/${encodeURIComponent(jobId)}/posts`
  )
}

export function cancelDeepSearchJob(jobId: string) {
  return req<{ job_id: string; cancelled: boolean }>(
    `/api/search/deep/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" }
  )
}

export function deleteDeepSearchJob(jobId: string) {
  return req<{ job_id: string; deleted: boolean }>(
    `/api/search/deep/jobs/${encodeURIComponent(jobId)}`,
    { method: "DELETE" }
  )
}

export async function pollDeepSearchJob(
  jobId: string,
  opts?: {
    intervalMs?: number
    timeoutMs?: number
    onProgress?: (job: DeepSearchJob) => void
    signal?: AbortSignal
  }
): Promise<DeepSearchJob> {
  const interval = opts?.intervalMs ?? 3000
  const timeout = opts?.timeoutMs ?? 30 * 60 * 1000
  const start = Date.now()
  const TERMINAL = ["completed", "failed", "cancelled", "error"]

  while (true) {
    if (opts?.signal?.aborted) throw new Error("Polling dibatalkan")
    if (Date.now() - start > timeout) throw new Error("Polling timeout")

    const resp = await getDeepSearchJob(jobId)
    const job = resp.data
    opts?.onProgress?.(job)

    if (TERMINAL.includes(job.status)) return job
    await new Promise((r) => setTimeout(r, interval))
  }
}

// ── DOWNLOAD CSV ───────────────────────────────────────────────────────────

export async function downloadSearchCsv(
  posts: SearchPost[],
  filenameHint = "tiktok_search"
): Promise<void> {
  const res = await fetch(`${BASE}/api/download/search-csv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ posts, filename_hint: filenameHint }),
  })
  if (!res.ok) throw new Error(`Download gagal: HTTP ${res.status}`)

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${filenameHint}_videos.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}