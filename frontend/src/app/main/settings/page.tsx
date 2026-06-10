"use client"

import { useState, useEffect } from "react"
import {
  Cookie, Save, Trash2, CheckCircle, XCircle, Loader2,
  AlertCircle, ExternalLink, ShieldCheck,
} from "lucide-react"
import { saveCookies, getCookieStatus, deleteCookies } from "@/lib/api"

interface CookieStatus {
  valid: boolean
  exists: boolean
  total_cookies?: number
  username?: string
  saved_at?: string
}

export default function SettingsPage() {
  const [cookiesJson, setCookiesJson] = useState("")
  const [username, setUsername] = useState("")
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<CookieStatus | null>(null)
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null)

  const loadStatus = () =>
    getCookieStatus().then(r => setStatus(r.data)).catch(() => setStatus(null))

  useEffect(() => { loadStatus() }, [])

  async function handleSave() {
    if (!cookiesJson.trim()) {
      setMsg({ type: "err", text: "Paste dulu cookie JSON-nya." })
      return
    }
    setSaving(true); setMsg(null)
    try {
      const r = await saveCookies(cookiesJson.trim(), username.trim())
      setMsg({ type: "ok", text: `${r.data.total_cookies} cookies tersimpan. Siap scraping!` })
      setCookiesJson("")
      loadStatus()
    } catch (e: unknown) {
      setMsg({ type: "err", text: e instanceof Error ? e.message : "Gagal menyimpan cookie" })
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!confirm("Hapus cookie tersimpan? Kamu perlu paste ulang untuk scraping lagi.")) return
    try {
      await deleteCookies()
      setMsg({ type: "ok", text: "Cookie dihapus." })
      loadStatus()
    } catch (e: unknown) {
      setMsg({ type: "err", text: e instanceof Error ? e.message : "Gagal menghapus" })
    }
  }

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-center gap-3 mb-8">
        <Cookie size={32} className="text-ttcyan" />
        <div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-display)" }}>Settings</h1>
          <p className="text-sm text-white/40">Login TikTok via cookie (Cookie-Editor)</p>
        </div>
      </div>

      {/* Status cookie */}
      <div className="glass-card p-5 mb-6">
        <h2 className="text-xs font-medium text-white/50 uppercase tracking-widest mb-3">Status Login</h2>
        {status === null ? (
          <div className="skeleton h-10 rounded-lg" />
        ) : status.valid ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <CheckCircle size={20} className="text-emerald-400" />
              <div>
                <p className="text-sm font-medium text-emerald-400">Cookie aktif & valid</p>
                <p className="text-xs text-white/40">
                  {status.total_cookies} cookies
                  {status.username && ` · @${status.username}`}
                  {status.saved_at && ` · disimpan ${new Date(status.saved_at).toLocaleString("id-ID")}`}
                </p>
              </div>
            </div>
            <button onClick={handleDelete}
              className="btn-glass text-xs flex items-center gap-1.5 text-red-400 hover:text-red-300">
              <Trash2 size={13} /> Hapus
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <XCircle size={20} className="text-red-400" />
            <div>
              <p className="text-sm font-medium text-red-400">Belum login</p>
              <p className="text-xs text-white/40">Paste cookie JSON di bawah untuk mulai.</p>
            </div>
          </div>
        )}
      </div>

      {/* Form paste cookie */}
      <div className="glass-card p-6 mb-6">
        <h2 className="text-xs font-medium text-white/50 uppercase tracking-widest mb-4">Inject Cookie</h2>

        <label className="block text-xs text-white/50 mb-2">Username TikTok (opsional)</label>
        <div className="relative mb-4">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">@</span>
          <input type="text" value={username} onChange={e => setUsername(e.target.value)}
            placeholder="username" className="input-glass pl-9" />
        </div>

        <label className="block text-xs text-white/50 mb-2">Cookie JSON (dari Cookie-Editor → Export as JSON)</label>
        <textarea
          value={cookiesJson}
          onChange={e => setCookiesJson(e.target.value)}
          placeholder='[{"name":"sessionid","value":"...","domain":".tiktok.com",...}, ...]'
          rows={8}
          className="input-glass font-mono text-xs resize-y"
          style={{ lineHeight: 1.5 }}
        />

        {msg && (
          <div className={`mt-3 flex items-center gap-2 text-sm glass rounded-xl px-4 py-2.5 ${
            msg.type === "ok" ? "text-emerald-400" : "text-red-400"
          }`}>
            {msg.type === "ok" ? <CheckCircle size={15} /> : <AlertCircle size={15} />}
            {msg.text}
          </div>
        )}

        <button onClick={handleSave} disabled={saving}
          className="btn-tt flex items-center gap-2 px-6 py-3 mt-4 disabled:opacity-50">
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          {saving ? "Menyimpan..." : "Simpan Cookies"}
        </button>
      </div>

      {/* Panduan */}
      <div className="glass-card p-6">
        <h2 className="text-xs font-medium text-white/50 uppercase tracking-widest mb-4 flex items-center gap-2">
          <ShieldCheck size={14} /> Cara Mendapatkan Cookie
        </h2>
        <ol className="space-y-2.5 text-sm text-white/60">
          {[
            "Login TikTok di browser (Chrome/Firefox) seperti biasa.",
            "Install ekstensi Cookie-Editor.",
            "Buka tiktok.com, klik ikon Cookie-Editor.",
            'Klik "Export" → pilih "Export as JSON" (cookie tersalin ke clipboard).',
            "Paste di kotak di atas, lalu klik Simpan Cookies.",
          ].map((step, i) => (
            <li key={i} className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-ttcyan/15 text-ttcyan text-xs flex items-center justify-center font-bold">{i + 1}</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
        <a href="https://cookie-editor.com" target="_blank" rel="noopener noreferrer"
          className="btn-glass text-xs flex items-center gap-1.5 mt-4 w-fit">
          <ExternalLink size={12} /> cookie-editor.com
        </a>
        <p className="text-[11px] text-white/30 mt-4 leading-relaxed">
          Cookie wajib: <code className="text-ttcyan">sessionid</code>. Cookie disimpan lokal di
          <code className="text-white/50"> engine/session/tt_session.json</code> dan dipakai engine
          saat scraping. Kalau scraping gagal dengan "session expired", export ulang cookie di sini.
        </p>
      </div>
    </div>
  )
}
