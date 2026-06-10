"use client"

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts"
import type { SentimentSummary } from "@/lib/types"

const SLICES = [
  { key: "positive_count", label: "Positif", color: "#22c55e" },
  { key: "negative_count", label: "Negatif", color: "#f87171" },
  { key: "neutral_count", label: "Netral", color: "#94a3b8" },
  { key: "humor_count", label: "Humor", color: "#818cf8" },
  { key: "toxic_count", label: "Toxic", color: "#fde047" },
  { key: "hate_speech_count", label: "Hate", color: "#ef4444" },
] as const

export function SentimentChart({ summary }: { summary: SentimentSummary }) {
  const data = SLICES
    .map(s => ({ name: s.label, value: (summary as any)[s.key] || 0, color: s.color }))
    .filter(d => d.value > 0)

  if (data.length === 0) {
    return <p className="text-sm text-white/40 text-center py-8">Belum ada data sentimen.</p>
  }

  return (
    // height eksplisit + minHeight mencegah warning recharts "width(-1) height(-1)"
    <div style={{ width: "100%", height: 256, minHeight: 256 }}>
      <ResponsiveContainer width="100%" height={256} debounce={50}>
        <PieChart>
          <Pie
            data={data} dataKey="value" nameKey="name"
            cx="50%" cy="50%" innerRadius={50} outerRadius={85}
            paddingAngle={2}
            animationBegin={0} animationDuration={800}
          >
            {data.map((d, i) => <Cell key={i} fill={d.color} stroke="transparent" />)}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "rgba(0,0,0,0.85)", border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 12, fontSize: 12, color: "#fff",
            }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
