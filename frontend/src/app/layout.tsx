import type { Metadata } from "next"
import { Space_Mono } from "next/font/google"
import "./globals.css"

const display = Space_Mono({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-display",
})

export const metadata: Metadata = {
  title: "TikTok Scraper",
  description: "Scrape komentar & profil TikTok + analisis sentimen",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body className={display.variable}>{children}</body>
    </html>
  )
}
