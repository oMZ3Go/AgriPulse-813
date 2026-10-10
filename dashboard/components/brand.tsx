import Link from "next/link";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="brand" aria-label="AgriPulse-813 home">
      <svg width="34" height="38" viewBox="0 0 34 38" fill="none" aria-hidden="true">
        <path d="M4 27V15L17 7l13 8v12l-13 8L4 27Z" stroke="currentColor" strokeWidth="1.4" />
        <path d="m9 24 8-5 8 5M9 18l8-5 8 5M17 19v11" stroke="currentColor" strokeWidth="1.4" />
        <path d="M17 2v5" stroke="#C9A866" strokeWidth="2" />
      </svg>
      <span><span className="brand-name">AgriPulse<span className="brand-number">-813</span></span>{!compact && <span className="brand-caption">Earth observation intelligence</span>}</span>
    </Link>
  );
}
