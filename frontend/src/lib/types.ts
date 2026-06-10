// lib/types.ts — Type definitions untuk TikTok Scraper UI

export interface ApiResponse<T> {
  success: boolean
  message: string
  timestamp: string
  data: T
}

// ── COMMENT ───────────────────────────────────────────────────────────────

export interface Comment {
  number: number
  username: string
  nickname: string
  text: string
  comment_id: string
  like_count: number
  created_at: number
  reply_count: number
  category: string
  sentiment: string
  language: string
  is_hate_speech: boolean
  is_toxic: boolean
  is_sarcasm: boolean
  is_wellwish: boolean
  hate_score: number
  hate_words: string[]
  toxic_words: string[]
  positive_words: string[]
  negative_words: string[]
  humor_words: string[]
  emojis: string[]
  ml_confidence: number
  decision_source: string
}

// ── TOP LIKED COMMENT ─────────────────────────────────────────────────────

export interface TopLikedComment {
  rank: number
  username: string
  nickname?: string
  text: string
  like_count: number
  category: string
  sentiment: string
  number?: number
}

// ── SENTIMENT SUMMARY ─────────────────────────────────────────────────────

export interface SentimentSummary {
  total_comments: number

  hate_speech_count: number
  hate_percentage: number

  toxic_count: number
  toxic_percentage: number

  positive_count: number
  positive_percentage: number

  negative_count: number
  negative_percentage: number

  neutral_count: number
  neutral_percentage: number

  humor_count: number
  humor_percentage: number

  sarcasm_count: number
  sarcasm_percentage: number

  wellwish_count: number
  wellwish_percentage: number

  avg_ml_confidence: number
  decision_source_breakdown: Record<string, number>

  hate_examples: Array<{
    username: string
    text: string
    hate_words: string[]
    like_count: number
  }>
  toxic_examples: Array<{
    username: string
    text: string
    toxic_words: string[]
  }>

  top_liked_comments: TopLikedComment[]

  most_active_users: Array<{
    username: string
    comment_count: number
  }>

  engagement?: Record<string, number>
}

// ── CAPTION SENTIMENT ─────────────────────────────────────────────────────

export interface CaptionSentiment {
  text: string
  sentiment: string
  category: string
  language: string
  is_hate_speech: boolean
  is_toxic: boolean
  is_sarcasm: boolean
  is_wellwish: boolean
  hate_score: number
  hate_words: string[]
  toxic_words: string[]
  positive_words: string[]
  negative_words: string[]
  humor_words: string[]
  emojis: string[]
  ml_confidence: number
  decision_source: string
}

// ── VIDEO RESULT ──────────────────────────────────────────────────────────

export interface VideoResult {
  url: string
  scraped_at: string
  sentiment_mode: string
  platform: string

  video_id: string
  username: string
  author_id: string
  description: string

  duration: number
  music_title: string
  hashtags: string[]
  create_time: number

  play_count: number
  digg_count: number
  share_count: number
  comment_count: number
  collect_count: number
  repost_count: number
  download_count: number

  method: string
  comments: Comment[]
  comments_count: number
  sentiment_summary: SentimentSummary
  caption_sentiment: CaptionSentiment

  top_5_liked_comments?: TopLikedComment[]

  // unified fields
  likers?: Liker[]
  likers_count?: number
  likers_method?: string
  active_commenters?: ActiveCommenter[]
  active_commenters_count?: number

  error?: string
  _saved_file?: string
  _meta?: Record<string, unknown>
}

// ── LIKER ─────────────────────────────────────────────────────────────────

export interface Liker {
  user_id: string
  username: string
  nickname: string
  avatar_url: string
  is_verified: boolean
  is_private: boolean
}

// ── ACTIVE COMMENTER ──────────────────────────────────────────────────────

export interface ActiveCommenter {
  username: string
  comment_count: number
  reply_count: number
  total_interactions: number
  total_likes: number
  dominant_category: string
  dominant_sentiment: string
}

// ── PROFILE ───────────────────────────────────────────────────────────────

export interface ProfileData {
  username: string
  scraped_at: string
  display_name: string
  bio: string
  avatar_url: string
  followers: number
  following: number
  total_likes: number
  total_videos: number
  is_verified: boolean
  profile_url: string
  method: string
}

export interface ProfileResult {
  success: boolean
  username: string
  scraped_at?: string
  data: ProfileData
  error?: string | null
  _saved_file?: string
}

// ── OUTPUT FILE ───────────────────────────────────────────────────────────

export interface OutputFile {
  name: string
  kind: "video" | "profile"
  size: number
  modified: string
}

// ── TRACKED PROFILE ───────────────────────────────────────────────────────

export interface TrackedProfile {
  username: string
  followers: number
  following: number
  total_likes: number
  total_videos: number
  data_points: number
  last_tracked: string
}

// ── BATCH ─────────────────────────────────────────────────────────────────

export interface BatchItem {
  url: string
  success: boolean
  data?: VideoResult
  error?: string
}

export interface BatchScrapeData {
  total: number
  success: number
  failed: number
  elapsed_seconds?: number
  results: BatchItem[]
  _saved_file?: string
}

// ── JOB SYSTEM (scrape jobs) ──────────────────────────────────────────────

export type JobStatus = "queued" | "running" | "done" | "error"
export type JobKind = "single" | "batch" | "profile" | "unified" | "checkpoint"

export interface JobStartResponse {
  job_id: string
  status: JobStatus
}

export interface Job<T = unknown> {
  job_id: string
  kind: JobKind
  label: string
  status: JobStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
  result: T | null
  error: string | null
  saved_file: string | null
}

export interface JobSummary {
  job_id: string
  kind: JobKind
  label: string
  status: JobStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
  saved_file: string | null
  error: string | null
}

// ════════════════════════════════════════════════════════════════
// SEARCH TYPES (baru — dari tiktok_search_endpoints.py)
// ════════════════════════════════════════════════════════════════

/**
 * Satu video/post hasil search (hashtag search, keyword search, atau deep search).
 * Field ini sesuai dengan _parse_video_item() di tiktok_search_scraper.py
 */
export interface SearchPost {
  video_id: string
  url: string
  username: string
  full_name: string
  is_verified: boolean
  caption: string
  hashtags: string[]

  like_count: number
  comment_count: number
  share_count: number
  play_count: number
  collect_count: number

  duration: number
  music_title: string

  create_time: number
  create_time_iso: string
  thumbnail_url: string

  /** Dari strategi mana post ini diambil (misal "hashtag_kulinerindonesia", "direct_bakso") */
  source: string
  /** Urutan ranking dalam hasil (berdasarkan like_count) */
  rank: number
  /** Untuk keyword search: hashtag sumber yang dipakai */
  search_source_tag?: string

  _meta?: Record<string, unknown>
}

/**
 * Info challenge/hashtag dari TikTok (dari /api/challenge/detail/).
 */
export interface ChallengeInfo {
  challenge_id: string
  name: string
  desc: string
  video_count: number
  view_count: number
}

/**
 * Hasil POST /api/search/hashtag
 */
export interface HashtagSearchResult {
  query: string
  hashtag: string
  scraped_at: string
  scraped_date: string
  success: boolean
  total_fetched: number
  /** challenge_api | search_api | page_navigate */
  method: string
  challenge_info: Partial<ChallengeInfo>
  posts: SearchPost[]
  error: string | null
  _meta?: {
    elapsed_seconds: number
    saved_file: string
  }
}

/**
 * Summary per-hashtag dalam hasil keyword search.
 */
export interface SearchedHashtagSummary {
  hashtag: string
  method: string
  fetched: number
}

/**
 * Satu item dalam suggested_hashtags dari discover/keyword search.
 */
export interface SuggestedHashtag {
  name: string
  video_count?: number
  source: "suggest" | "search_hashtag" | string
}

/**
 * Hasil POST /api/search/keyword
 */
export interface KeywordSearchResult {
  query: string
  scraped_at: string
  scraped_date: string
  success: boolean
  total_fetched: number
  searched_hashtags: SearchedHashtagSummary[]
  suggested_hashtags: SuggestedHashtag[]
  posts: SearchPost[]
  error: string | null
  _meta?: {
    elapsed_seconds: number
    saved_file: string
  }
}

/**
 * Hasil POST /api/search/discover
 */
export interface DiscoverResult {
  query: string
  scraped_at: string
  success: boolean
  hashtags: SuggestedHashtag[]
  users: Array<{ username: string; [key: string]: unknown }>
  error: string | null
}

// ── DEEP SEARCH (background jobs) ─────────────────────────────────────────

/** Status sebuah deep search job */
export type DeepSearchStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"

/**
 * State sebuah deep search job.
 * Sesuai dengan struktur yang dikembalikan tiktok_search_checkpoint.py
 */
export interface DeepSearchJob {
  job_id: string
  /** "hashtag" | "keyword" */
  mode: "hashtag" | "keyword"
  query: string
  status: DeepSearchStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
  error: string | null

  /** Konfigurasi awal (max_related_hashtags / max_hashtags / include_top) */
  config: Record<string, unknown>

  /** Progress scraping */
  progress: {
    total_posts: number
    hashtags_done: number
    hashtags_total: number
    current_hashtag: string | null
    /** 0–100 */
    percentage: number
  }
}

/**
 * Response POST /api/search/deep/hashtag dan /api/search/deep/keyword
 */
export interface DeepSearchStartResponse {
  job_id: string
  mode: "hashtag" | "keyword"
  query: string
}

/**
 * Response GET /api/search/deep/jobs/{jobId}/posts
 */
export interface DeepJobPostsResult {
  posts: SearchPost[]
  total: number
}

// ============================================================
// tiktok-search-types.ts
// TikTok Deep Search — type definitions untuk frontend Next.js
// ============================================================

// ── Job status ──────────────────────────────────────────────
export type TikTokDeepJobStatus =
  | "pending"
  | "running"
  | "completed"
  | "cancelled"
  | "error";

// ── Satu video/post hasil scrape ─────────────────────────────
export interface TikTokSearchPost {
  video_id:        string;
  url:             string;
  username:        string;
  full_name:       string;
  is_verified:     boolean;
  caption:         string;
  hashtags:        string[];

  like_count:      number;
  comment_count:   number;
  share_count:     number;
  play_count:      number;
  collect_count:   number;

  duration:        number;           // detik
  music_title:     string;
  create_time:     number;           // unix timestamp
  create_time_iso: string;           // ISO 8601
  thumbnail_url:   string;

  source:          string;           // "hashtag_xxx" | "search_xxx" | "direct_xxx"
  rank:            number;

  // ditambahkan oleh deep search worker
  deep_source_tag?: string;
  search_source_tag?: string;
}

// ── Info challenge/hashtag dari TikTok ───────────────────────
export interface TikTokChallengeInfo {
  challenge_id: string;
  name:         string;
  desc:         string;
  video_count:  number;
  view_count:   number;
}

// ── Progress hashtag yang sudah di-scrape ────────────────────
export interface TikTokSearchedHashtag {
  hashtag:     string;
  method:      string;   // "challenge_api" | "search_api" | "page_navigate"
  fetched:     number;
  video_count?: number;
}

// ── State lengkap satu job (dari GET /jobs/{job_id}) ─────────
export interface TikTokDeepJobState {
  job_id:              string;
  platform:            "tiktok";
  mode:                "hashtag" | "keyword";
  query:               string;
  config:              TikTokDeepJobConfig;
  status:              TikTokDeepJobStatus;
  created_at:          string;
  updated_at:          string;
  total_fetched:       number;
  progress_log:        string[];
  searched_hashtags:   TikTokSearchedHashtag[];
  challenge_info:      TikTokChallengeInfo | Record<string, never>;
  error:               string | null;
}

// ── Config job ────────────────────────────────────────────────
export interface TikTokDeepJobConfig {
  // hashtag mode
  max_related_hashtags?:  number;
  // keyword mode
  max_hashtags?:          number;
  // shared
  max_posts_per_hashtag?: number;
}

// ── Ringkasan job (dari GET /jobs list) ──────────────────────
export interface TikTokDeepJobSummary {
  job_id:              string;
  platform:            "tiktok";
  mode:                "hashtag" | "keyword";
  query:               string;
  status:              TikTokDeepJobStatus;
  total_fetched:       number;
  searched_hashtags:   TikTokSearchedHashtag[];
  challenge_info:      TikTokChallengeInfo | Record<string, never>;
  created_at:          string;
  updated_at:          string;
  error:               string | null;
}

// ── API response wrapper (mirip pola IG scraper) ─────────────
export interface TikTokDeepApiResponse<T = unknown> {
  success:   boolean;
  message:   string;
  timestamp: string;
  data:      T;
}

// ── POST /hashtag request body ────────────────────────────────
export interface TikTokDeepHashtagRequest {
  hashtag:               string;
  max_related_hashtags?: number;   // default 10
  include_top?:           boolean;  // default true (include top videos)
  max_posts_per_hashtag?: number;  // default 300
}

// ── POST /keyword request body ────────────────────────────────
export interface TikTokDeepKeywordRequest {
  keyword:               string;
  max_hashtags?:         number;   // default 5
  max_posts_per_hashtag?: number;  // default 150
}

// ── Response saat create job ──────────────────────────────────
export interface TikTokDeepCreateJobResponse {
  job_id: string;
  mode:   "hashtag" | "keyword";
  query:  string;
}

// ── Response GET /jobs/{job_id}/posts ─────────────────────────
export interface TikTokDeepPostsResponse {
  posts: TikTokSearchPost[];
  total: number;
}

// ── Response GET /jobs list ───────────────────────────────────
export interface TikTokDeepJobsListResponse {
  jobs:  TikTokDeepJobSummary[];
  count: number;
}