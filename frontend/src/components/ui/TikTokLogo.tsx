// components/ui/TikTokLogo.tsx
// Logo nada musik TikTok dengan glitch offset cyan (#00F2EA) + merah (#FF0050).

export function TikTokLogo({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none"
      xmlns="http://www.w3.org/2000/svg" className={className} aria-label="TikTok">
      {/* layer cyan (offset kiri) */}
      <path
        d="M33 10.5c1.2 2.6 3.5 4.5 6.3 5v5.1c-2.6 0-5-.8-7-2.3v10.4c0 5.7-4.6 10.3-10.3 10.3S11.7 34.4 11.7 28.7c0-5.3 4-9.7 9.2-10.2v5.3c-2.3.5-4 2.5-4 4.9 0 2.8 2.3 5 5 5s5-2.2 5-5V7h6.1c0 1.2.3 2.4 0 3.5z"
        fill="#00F2EA" transform="translate(-1.4 1.2)"
      />
      {/* layer merah (offset kanan) */}
      <path
        d="M33 10.5c1.2 2.6 3.5 4.5 6.3 5v5.1c-2.6 0-5-.8-7-2.3v10.4c0 5.7-4.6 10.3-10.3 10.3S11.7 34.4 11.7 28.7c0-5.3 4-9.7 9.2-10.2v5.3c-2.3.5-4 2.5-4 4.9 0 2.8 2.3 5 5 5s5-2.2 5-5V7h6.1c0 1.2.3 2.4 0 3.5z"
        fill="#FF0050" transform="translate(1.4 -1.2)"
      />
      {/* layer putih (utama) */}
      <path
        d="M33 10.5c1.2 2.6 3.5 4.5 6.3 5v5.1c-2.6 0-5-.8-7-2.3v10.4c0 5.7-4.6 10.3-10.3 10.3S11.7 34.4 11.7 28.7c0-5.3 4-9.7 9.2-10.2v5.3c-2.3.5-4 2.5-4 4.9 0 2.8 2.3 5 5 5s5-2.2 5-5V7h6.1c0 1.2.3 2.4 0 3.5z"
        fill="#FFFFFF"
      />
    </svg>
  )
}
