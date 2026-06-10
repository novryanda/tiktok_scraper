"use client"

import type { Comment } from "@/lib/types"

function badge(c: Comment): { label: string; cls: string } {
  if (c.is_hate_speech) return { label: "🚨 Hate", cls: "bg-red-500/15 text-red-400" }
  if (c.is_toxic) return { label: "⚠️ Toxic", cls: "bg-yellow-500/15 text-yellow-300" }
  switch (c.category) {
    case "POSITIVE": return { label: "😊 Positif", cls: "bg-emerald-500/15 text-emerald-400" }
    case "NEGATIVE": return { label: "😞 Negatif", cls: "bg-rose-500/15 text-rose-400" }
    case "HUMOR": return { label: "😂 Humor", cls: "bg-indigo-500/15 text-indigo-300" }
    default: return { label: "😐 Netral", cls: "bg-white/10 text-white/50" }
  }
}

export function CommentList({ comments }: { comments: Comment[] }) {
  if (!comments?.length) {
    return <p className="text-sm text-white/40">Tidak ada komentar.</p>
  }
  return (
    <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
      {comments.map((c, i) => {
        const b = badge(c)
        return (
          <div key={i} className="glass rounded-xl p-3">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-sm font-medium text-white/80 truncate">@{c.username}</span>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className={`text-[10px] px-2 py-0.5 rounded-full ${b.cls}`}>{b.label}</span>
                {c.like_count > 0 && (
                  <span className="text-xs text-ttred font-semibold">❤ {c.like_count.toLocaleString("id-ID")}</span>
                )}
              </div>
            </div>
            <p className="text-sm text-white/60 leading-relaxed">{c.text}</p>
            {(c.is_sarcasm || c.is_wellwish) && (
              <p className="text-[11px] text-white/30 mt-1">
                {c.is_sarcasm && "🎭 Sarkasme "}{c.is_wellwish && "🙏 Doa/Wellwish"}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}