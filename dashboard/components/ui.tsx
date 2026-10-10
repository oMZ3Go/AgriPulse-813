import { Crosshair } from "lucide-react";

export function PlaceholderBadge() { return <span className="placeholder-badge">Placeholder</span>; }

export function SectionHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className="section-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>;
}

export function EmptyEvidence({ title, description, spatial = false }: { title: string; description: string; spatial?: boolean }) {
  return <div className={`empty-evidence ${spatial ? "spatial-placeholder" : ""}`}><span className="registration registration-tl" /><span className="registration registration-tr" /><span className="registration registration-bl" /><span className="registration registration-br" /><div className="empty-evidence-copy"><Crosshair size={26} strokeWidth={1} aria-hidden="true" /><PlaceholderBadge /><h3>{title}</h3><p>{description}</p></div><span className="empty-caption mono">NO ANALYSIS DISPLAYED</span></div>;
}
