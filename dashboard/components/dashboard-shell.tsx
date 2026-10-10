"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowLeft, ArrowUpRight, BookOpen, ChevronRight, FileCheck2, Fingerprint, Info, Layers3, LayoutGrid, Map, ScanLine, ShieldCheck, Workflow } from "lucide-react";
import { Brand } from "@/components/brand";
import { ModeSwitch, type Mode } from "@/components/mode-switch";
import { FarmerShell } from "@/components/farmer-shell";
import { ExpertShell } from "@/components/expert-shell";
import { expertSections, type ExpertSection } from "@/lib/scenes";

const expertIcons = [LayoutGrid, Map, Fingerprint, Workflow, Layers3, BookOpen, FileCheck2];

export function DashboardShell() {
  const search = useSearchParams();
  const router = useRouter();
  const reduced = useReducedMotion();
  const mode: Mode = search.get("mode") === "expert" ? "expert" : "farmer";
  const requestedView = search.get("view");
  const view: ExpertSection = expertSections.find((section) => section.id === requestedView)?.id ?? "overview";
  const farmerView = ["map", "decision"].includes(requestedView ?? "") ? requestedView! : "overview";

  function navigate(nextMode: Mode, nextView = "overview") {
    router.replace(`/dashboard?mode=${nextMode}${nextView !== "overview" ? `&view=${nextView}` : ""}`, { scroll: false });
  }

  return <div className="workspace">
    <header className="workspace-header"><Brand compact /><div className="workspace-breadcrumb"><span>Demo workspace</span><ChevronRight size={13} /><span>Konya, Turkey</span></div><Link href="/scene" className="change-scene">Change scene <ArrowUpRight size={14} /></Link></header>
    <aside className="workspace-sidebar" aria-label="Workspace navigation">
      <div className="sidebar-scene"><span className="eyebrow">Current scene</span><h2><span className="location-dot gold" />Konya, Turkey</h2><p>Current validated demo scene</p><span className="mono">TANAGER / SENTINEL-2</span></div>
      <p className="sidebar-nav-label mono">{mode === "farmer" ? "FIELD WORKSPACE" : "EVIDENCE WORKSPACE"}</p>
      <nav aria-label={mode === "farmer" ? "Farmer navigation" : "Expert navigation"}>
        {mode === "expert" ? expertSections.map((section, i) => { const Icon = expertIcons[i]; return <button key={section.id} className="sidebar-nav-item" aria-current={view === section.id ? "page" : undefined} onClick={() => navigate("expert", section.id)}><Icon size={17} /><span>{section.label}</span>{view === section.id && <span className="nav-active-dot" />}</button>; }) : [{ id: "overview", label: "Field overview", icon: LayoutGrid }, { id: "map", label: "Map & hotspots", icon: Map }, { id: "decision", label: "Decision summary", icon: ShieldCheck }].map(({ id, label, icon: Icon }) => <button className="sidebar-nav-item" key={id} aria-current={farmerView === id ? "page" : undefined} onClick={() => navigate("farmer", id)}><Icon size={17} /><span>{label}</span>{farmerView === id && <span className="nav-active-dot" />}</button>)}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-principle"><ScanLine size={19} strokeWidth={1.3} /><p>Evidence before action.<span>Observe. Understand. Verify.</span></p></div><Link href="/"><ArrowLeft size={14} /> Back to Earth view</Link><span className="sidebar-credit">A Beyond The Limit project</span></div>
    </aside>
    <main id="main-content" className="workspace-main">
      <div className="workspace-toolbar"><ModeSwitch mode={mode} onChange={(nextMode) => navigate(nextMode)} /><span className="workspace-type mono">SCENE WORKSPACE <span>/</span> 813</span></div>
      <div className="preview-notice"><Info size={16} /><p><strong>Interface preview</strong><span>All analysis areas are placeholders. No field assessment or recommendation is displayed.</span></p><span className="preview-tag">UI ONLY</span></div>
      <AnimatePresence mode="wait" initial={false}><motion.div key={`${mode}-${mode === "expert" ? view : farmerView}`} id="mode-panel" role="tabpanel" aria-labelledby={`mode-${mode}`} initial={{ opacity: 0, y: reduced ? 0 : 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reduced ? 0 : 0.22 }}>{mode === "farmer" ? <FarmerShell view={farmerView} onView={(next) => navigate("farmer", next)} /> : <ExpertShell view={view} onView={(next) => navigate("expert", next)} />}</motion.div></AnimatePresence>
      <footer className="workspace-footer"><span><span className="location-dot gold" /> Konya demo context</span><span>Syria & the Arab region <span className="footer-slash">/</span> target deployment only</span></footer>
    </main>
  </div>;
}
