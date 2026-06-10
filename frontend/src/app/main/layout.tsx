"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Search,
  Users,
  BarChart3,
  FileJson,
  Settings,
  Wifi,
  WifiOff,
  Hash,
  ChevronLeft,
  ChevronRight,
} from "lucide-react"
import { TikTokLogo } from "@/components/ui/TikTokLogo"
import { getCookieStatus } from "@/lib/api"

const NAV = [
  { href: "/main/scrapes", label: "Scrape Video", icon: Search },
  { href: "/main/search", label: "Search", icon: Hash },   // ← tambahan menu Search
  { href: "/main/profiles", label: "Profiles", icon: Users },
  { href: "/main/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/main/files", label: "Output Files", icon: FileJson },
  { href: "/main/settings", label: "Settings", icon: Settings },
]

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [session, setSession] = useState<"loading" | "valid" | "invalid">("loading")
  const [sidebarOpen, setSidebarOpen] = useState(true)

  useEffect(() => {
    getCookieStatus()
      .then(r => setSession(r.data?.valid ? "valid" : "invalid"))
      .catch(() => setSession("invalid"))
  }, [pathname])

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside
        className={`relative flex-shrink-0 overflow-hidden border-r border-white/[0.07] bg-slate-950/90 transition-all duration-300 ease-in-out ${
          sidebarOpen ? "w-64 p-5" : "w-16 p-3"
        }`}>
        <div className={`flex items-center justify-between ${sidebarOpen ? "mb-8" : "mb-6"}`}>
          <div className={`flex items-center gap-3 ${sidebarOpen ? "" : "justify-center w-full"}`}>
            <TikTokLogo size={40} />
            {sidebarOpen && (
              <div>
                <h1 className="font-bold text-lg tt-text" style={{ fontFamily: "var(--font-display)" }}>
                  TikTok Scraper
                </h1>
                <p className="text-[11px] text-white/40">Sentiment Dashboard</p>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => setSidebarOpen(open => !open)}
            className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-white transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-ttcyan"
            aria-label={sidebarOpen ? "Sembunyikan sidebar" : "Tampilkan sidebar"}
          >
            {sidebarOpen ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
          </button>
        </div>

        {/* Session indicator */}
        <div className={`glass-card mb-6 flex items-center gap-3 ${sidebarOpen ? "p-3" : "p-2 justify-center"}`}>
          {session === "valid" ? (
            <>
              <Wifi size={16} className="text-emerald-400" />
              {sidebarOpen ? (
                <div>
                  <p className="text-xs font-medium text-emerald-400">Session aktif</p>
                  <p className="text-[10px] text-white/30">Siap scraping</p>
                </div>
              ) : (
                <span className="sr-only">Session aktif</span>
              )}
            </>
          ) : session === "invalid" ? (
            <Link
              href="/main/settings"
              className={`flex items-center gap-3 w-full ${sidebarOpen ? "" : "justify-center"}`}
            >
              <WifiOff size={16} className="text-red-400" />
              {sidebarOpen ? (
                <div>
                  <p className="text-xs font-medium text-red-400">Belum login</p>
                  <p className="text-[10px] text-white/30">Klik untuk paste cookie</p>
                </div>
              ) : (
                <span className="sr-only">Belum login</span>
              )}
            </Link>
          ) : (
            <div className="skeleton h-8 w-full rounded-lg" />
          )}
        </div>

        <nav className="space-y-1 flex-1">
          {NAV.map(item => {
            const active = pathname === item.href
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all ${
                  active
                    ? "bg-white/10 text-white border border-white/10"
                    : "text-white/50 hover:text-white/80 hover:bg-white/[0.04] border border-transparent"
                } ${sidebarOpen ? "justify-start" : "justify-center"}`}
              >
                <Icon size={16} className={active ? "text-ttcyan" : ""} />
                {sidebarOpen && item.label}
              </Link>
            )
          })}
        </nav>

        {sidebarOpen && (
          <p className="text-[10px] text-white/20 mt-4">TikTok Scraper · FastAPI Bridge</p>
        )}
      </aside>

      {/* Konten */}
      <main className="flex-1 overflow-x-hidden">{children}</main>
    </div>
  )
}