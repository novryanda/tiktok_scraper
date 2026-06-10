// components/ui/StatCard.tsx
type Color = "cyan" | "red" | "white" | "purple" | "green"

const COLORS: Record<Color, string> = {
  cyan: "#00F2EA",
  red: "#FF0050",
  white: "#FFFFFF",
  purple: "#A855F7",
  green: "#22C55E",
}

export function StatCard({
  label, value, color = "cyan",
}: { label: string; value: number | string; color?: Color }) {
  const fmt = typeof value === "number" ? value.toLocaleString("id-ID") : value
  return (
    <div className="glass-card p-4 text-center">
      <p className="text-2xl font-bold" style={{ color: COLORS[color] }}>{fmt}</p>
      <p className="text-[11px] uppercase tracking-widest text-white/40 mt-1">{label}</p>
    </div>
  )
}
