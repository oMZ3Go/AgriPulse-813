import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Brand } from "@/components/brand";

export function Header({ scene = false }: { scene?: boolean }) {
  return (
    <header className="site-header">
      <Brand />
      <nav aria-label="Main navigation" className="header-nav">
        <Link className={scene ? "nav-link active" : "nav-link"} href="/scene" aria-current={scene ? "page" : undefined}>Explore Earth</Link>
        <span className="header-divider" />
        <span className="team-credit">Beyond The Limit <ArrowUpRight size={13} aria-hidden="true" /></span>
      </nav>
    </header>
  );
}
