"use client"

import { useState, useEffect } from "react"
import {
  FileJson, Eye, RefreshCw, Search, X, ChevronDown, ChevronUp,
  ExternalLink, CheckCircle, XCircle, Users,
} from "lucide-react"
import { listOutputFiles, getOutputFile } from "@/lib/api"
import type { OutputFile } from "@/lib/types"
import { SentimentChart } from "@/components/features/SentimentChart"
import { CommentList } from "@/components/features/CommentList"

type AnyObj = Record<string, any>

function TopComments({ topLiked }: { topLiked?: any[] }) {
  if (!Array.isArray(topLiked) || topLiked.length === 0) return null
  return (
    <div className="glass-card p-5">
      <h4 className="text-xs font-medium text-white/50 uppercase tracking-widest mb-3">🔥 Top Komentar (Likes)</h4>
      <div className="space-y-2">
        {topLiked.slice(0, 5).map((c, i) => (
          <div key={i} className="flex gap-3 items-start py-2 border-b border-white/[0.04] last:border-0">
            <span className="text-base font-bold text-white/20 w-6 flex-shrink-0">#{i + 1}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white/80 mb-0.5">@{c.username}</p>
              <p className="text-sm text-white/50 line-clamp-2">{c.text}</p>
            </div>
            <p className="text-ttred font-bold text-sm flex-shrink-0">❤ {(c.like_count || 0).toLocaleString("id-ID")}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function FilesPage() {
  const [files, setFiles] = useState<OutputFile[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [selected, setSelected] = useState<AnyObj | null>(null)
  const [selectedName, setSelectedName] = useState("")
  const [previewLoading, setPreviewLoading] = useState(false)
  const [showComments, setShowComments] = useState(false)
  const [openBatch, setOpenBatch] = useState<number | null>(null)

  const load = () => {
    setLoading(true)
    listOutputFiles().then(r => { if (r.success) setFiles(r.data.files) }).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const filtered = files.filter(f => f.name.toLowerCase().includes(search.toLowerCase()))

  async function preview(name: string) {
    setPreviewLoading(true); setSelected(null); setSelectedName(name)
    setShowComments(false); setOpenBatch(null)
    try {
      const data = await getOutputFile(name) as any
      // file profile engine: {success, username, data:{...}}. Ratakan.
      const normalized = data?.data && data.data.username && !Array.isArray(data.results)
        ? { ...data.data, _profile: true }
        : data
      setSelected(normalized)
    } catch { /* skip */ }
    finally { setPreviewLoading(false) }
  }

  const fmtSize = (b: number) =>
    b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`
  const fmtNum = (n: any) => typeof n === "number" ? n.toLocaleString("id-ID") : (n ?? "—")

  const isBatch = (d: AnyObj) => d && Array.isArray(d.results)
  const isProfile = (d: AnyObj) => d && !isBatch(d) && (d._profile || d.total_videos !== undefined || d.total_likes !== undefined)
  const isVideo = (d: AnyObj) => d && !isBatch(d) && !isProfile(d) && (d.video_id !== undefined || d.digg_count !== undefined)

  return (
    <div className="p-8 max-w-7xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-display)" }}>Output Files</h1>
          <p className="text-sm text-white/40 mt-0.5">Semua hasil scraping tersimpan di sini</p>
        </div>
        <button onClick={load} disabled={loading} className="btn-glass flex items-center gap-2 text-sm">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* List */}
        <div>
          <div className="relative mb-4">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
            <input type="text" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Cari file..." className="input-glass pl-9 text-sm" />
            {search && (
              <button onClick={() => setSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2">
                <X size={14} className="text-white/30" />
              </button>
            )}
          </div>
          <div className="glass-card p-4">
            {loading ? (
              <div className="space-y-2">{[1, 2, 3, 4, 5].map(i => <div key={i} className="skeleton h-12 rounded-lg" />)}</div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-12 text-white/30 text-sm">
                <FileJson size={40} className="mx-auto mb-3 opacity-20" />
                {files.length === 0 ? "Belum ada file output." : "Tidak ada file yang cocok."}
              </div>
            ) : (
              <div className="space-y-1.5 max-h-[600px] overflow-y-auto pr-1">
                {filtered.map(f => (
                  <button key={f.name} onClick={() => preview(f.name)}
                    className={`w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
                      selectedName === f.name ? "bg-white/10 border border-white/15" : "hover:bg-white/[0.05] border border-transparent"
                    }`}>
                    <FileJson size={16} className={
                      f.name.includes("batch") ? "text-purple-400" :
                      f.kind === "profile" ? "text-ttcyan" : "text-ttred"
                    } />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-mono text-white/80 truncate">{f.name}</p>
                      <p className="text-[10px] text-white/30 mt-0.5">{fmtSize(f.size)} · {new Date(f.modified).toLocaleString("id-ID")}</p>
                    </div>
                    <Eye size={13} className="text-white/20 flex-shrink-0" />
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Preview */}
        <div>
          {previewLoading && (
            <div className="glass-card p-12 text-center"><div className="animate-pulse text-white/30 text-sm">Memuat file...</div></div>
          )}

          {/* BATCH */}
          {selected && !previewLoading && isBatch(selected) && (
            <div className="space-y-4">
              <div className="glass-card p-5 flex items-center gap-6">
                <div>
                  <p className="text-2xl font-bold tt-text">{selected.success ?? 0}/{selected.total ?? selected.results.length}</p>
                  <p className="text-xs text-white/40">video berhasil</p>
                </div>
                <div className="flex items-center gap-2 text-sm text-emerald-400"><CheckCircle size={16} /> {selected.success ?? 0} sukses</div>
                {(selected.failed ?? 0) > 0 && <div className="flex items-center gap-2 text-sm text-red-400"><XCircle size={16} /> {selected.failed} gagal</div>}
              </div>
              {selected.results.map((item: AnyObj, idx: number) => {
                const d = item.data
                const ss = d?.sentiment_summary
                const isOpen = openBatch === idx
                if (!item.success || !d) {
                  return (
                    <div key={idx} className="glass-card p-4 border border-red-500/20">
                      <div className="flex items-center gap-2 text-red-400 text-sm"><XCircle size={15} /> Gagal</div>
                      <p className="text-xs text-white/40 mt-1 break-all">{item.url}</p>
                      {item.error && <p className="text-xs text-red-400/70 mt-1">{item.error}</p>}
                    </div>
                  )
                }
                return (
                  <div key={idx} className="glass-card p-5 space-y-3">
                    <div className="flex items-start justify-between">
                      <h3 className="font-semibold">@{d.username || "unknown"}</h3>
                      {d.url && <a href={d.url} target="_blank" rel="noopener noreferrer" className="btn-glass text-xs flex items-center gap-1.5"><ExternalLink size={12} /> Buka</a>}
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="glass rounded-xl p-3 text-center"><p className="text-base font-bold tt-text">{fmtNum(d.play_count)}</p><p className="text-[11px] text-white/40">Views</p></div>
                      <div className="glass rounded-xl p-3 text-center"><p className="text-base font-bold tt-text">{fmtNum(d.digg_count)}</p><p className="text-[11px] text-white/40">Likes</p></div>
                      <div className="glass rounded-xl p-3 text-center"><p className="text-base font-bold tt-text">{fmtNum(d.comments_count)}</p><p className="text-[11px] text-white/40">Komentar</p></div>
                    </div>
                    {ss && ss.total_comments > 0 && <SentimentChart summary={ss} />}
                    {ss?.top_liked_comments?.length > 0 && (
                      <div>
                        <h4 className="text-xs font-medium text-white/50 uppercase tracking-widest mb-2">🔥 Top Komentar (Likes)</h4>
                        <div className="space-y-2">
                          {ss.top_liked_comments.slice(0, 5).map((c: any, i: number) => (
                            <div key={i} className="flex gap-3 items-start py-1.5 border-b border-white/[0.04] last:border-0">
                              <span className="text-sm font-bold text-white/20 w-5 flex-shrink-0">#{i + 1}</span>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium text-white/80">@{c.username}</p>
                                <p className="text-xs text-white/50 line-clamp-2">{c.text}</p>
                              </div>
                              <p className="text-ttred font-bold text-xs flex-shrink-0">❤ {(c.like_count || 0).toLocaleString("id-ID")}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {Array.isArray(d.comments) && d.comments.length > 0 && (
                      <div>
                        <button onClick={() => setOpenBatch(isOpen ? null : idx)} className="w-full flex items-center justify-between text-sm font-medium">
                          <span>💬 Semua Komentar ({d.comments_count})</span>{isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                        {isOpen && <div className="mt-3"><CommentList comments={d.comments} /></div>}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* PROFILE */}
          {selected && !previewLoading && isProfile(selected) && (
            <div className="glass-card p-5">
              <div className="flex items-start gap-4 mb-4">
                <div className="w-16 h-16 rounded-full overflow-hidden glass flex items-center justify-center flex-shrink-0">
                  {selected.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={selected.avatar_url} alt={selected.username} className="w-full h-full object-cover"
                      onError={e => { (e.target as HTMLImageElement).style.display = "none" }} />
                  ) : <Users size={24} className="text-white/30" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-lg truncate">@{selected.username}</h3>
                    {selected.is_verified && <CheckCircle size={16} className="text-ttcyan flex-shrink-0" />}
                  </div>
                  <p className="text-sm text-white/50 truncate">{selected.display_name || "—"}</p>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-3">
                {[
                  { l: "Followers", v: selected.followers },
                  { l: "Following", v: selected.following },
                  { l: "Likes", v: selected.total_likes },
                  { l: "Videos", v: selected.total_videos },
                ].map(x => (
                  <div key={x.l} className="glass rounded-xl p-3 text-center">
                    <p className="text-base font-bold tt-text">{fmtNum(x.v)}</p>
                    <p className="text-[11px] text-white/40">{x.l}</p>
                  </div>
                ))}
              </div>
              {selected.bio && <p className="text-xs text-white/40 mt-3 leading-relaxed">{selected.bio}</p>}
              {selected.method && <p className="text-[11px] text-white/30 mt-3">Method: {selected.method}</p>}
            </div>
          )}

          {/* VIDEO */}
          {selected && !previewLoading && isVideo(selected) && (
            <div className="space-y-4">
              <div className="glass-card p-5">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="font-semibold">@{selected.username || "unknown"}</h3>
                    <p className="text-xs text-white/40 mt-0.5 font-mono">{selected.video_id || "—"}</p>
                  </div>
                  {selected.url && <a href={selected.url} target="_blank" rel="noopener noreferrer" className="btn-glass text-xs flex items-center gap-1.5"><ExternalLink size={12} /> Buka</a>}
                </div>
                <div className="grid grid-cols-4 gap-3">
                  {[
                    { l: "Views", v: selected.play_count },
                    { l: "Likes", v: selected.digg_count },
                    { l: "Komentar", v: selected.comments_count },
                    { l: "Shares", v: selected.share_count },
                  ].map(x => (
                    <div key={x.l} className="glass rounded-xl p-3 text-center">
                      <p className="text-base font-bold tt-text">{fmtNum(x.v)}</p>
                      <p className="text-[11px] text-white/40">{x.l}</p>
                    </div>
                  ))}
                </div>
                {selected.description && <p className="text-sm text-white/50 mt-3 leading-relaxed line-clamp-3">{selected.description}</p>}
              </div>

              {selected.sentiment_summary && selected.sentiment_summary.total_comments > 0 && (
                <div className="glass-card p-5">
                  <h4 className="text-xs font-medium text-white/50 uppercase tracking-widest mb-3">Sentimen</h4>
                  <SentimentChart summary={selected.sentiment_summary} />
                </div>
              )}

              <TopComments topLiked={selected.sentiment_summary?.top_liked_comments} />

              {Array.isArray(selected.comments) && selected.comments.length > 0 && (
                <div className="glass-card p-5">
                  <button onClick={() => setShowComments(v => !v)} className="w-full flex items-center justify-between text-sm font-medium">
                    <span>💬 Semua Komentar ({selected.comments.length})</span>{showComments ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                  {showComments && <div className="mt-4"><CommentList comments={selected.comments} /></div>}
                </div>
              )}
            </div>
          )}

          {!selected && !previewLoading && (
            <div className="glass-card p-12 text-center text-white/20">
              <FileJson size={48} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">Pilih file untuk preview</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
