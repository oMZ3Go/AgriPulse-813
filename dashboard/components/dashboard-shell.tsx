"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowUpRight, ChevronRight, ScanLine } from "lucide-react";
import { Brand } from "@/components/brand";
import { ModeSwitch } from "@/components/mode-switch";
import { SimpleShell } from "@/components/simple-shell";
import { ExpertShell } from "@/components/expert-shell";
import { AnalysisActivity } from "@/components/analysis-activity";
import { EvidenceAvailability } from "@/components/evidence-availability";
import { ProductFlow } from "@/components/product-flow";
import { expertSections, type ExpertSection } from "@/lib/scenes";
import { loadKonya, type KonyaData } from "@/lib/konya";
import { parseMode, parseUseCase, productUrl, useCases, type Mode, type UseCase } from "@/lib/product";

export function DashboardShell() {
  const search = useSearchParams();
  const router = useRouter();
  const mode = parseMode(search.get("mode"));
  const useCase = parseUseCase(search.get("useCase"));
  const view: ExpertSection = expertSections.find((section) => section.id === search.get("view"))?.id ?? "overview";
  const [data, setData] = useState<KonyaData | null>(null);
  const [completed, setCompleted] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError(null); setCompleted(0);
    loadKonya(controller.signal, (value) => { if (!controller.signal.aborted) setCompleted(value); })
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "The local package could not be read."); });
    return () => controller.abort();
  }, [attempt]);
  function navigate(nextCase: UseCase, nextMode: Mode, nextView = view) {
    router.replace(productUrl("/dashboard", nextCase, nextMode, nextView !== "overview" ? { view: nextView } : {}), { scroll: false });
  }
  return <div className="workspace">
    <header className="workspace-header"><Brand compact /><div className="workspace-breadcrumb"><span>Validated demo</span><ChevronRight size={13} /><span>Konya, Turkey</span></div><Link href={productUrl("/scene", useCase, mode, { country: "792" })} className="change-scene">Choose location <ArrowUpRight size={14} /></Link></header>
    <aside className="workspace-sidebar" aria-label="Workspace navigation">
      <div className="sidebar-scene"><span className="eyebrow">Current scene</span><h2><span className="location-dot gold" />Konya, Turkey</h2><p>Current validated demo scene</p><span className="mono">8 JUN 2025 / SAVED EVIDENCE</span></div>
      <p className="sidebar-nav-label mono">{mode === "SIMPLE" ? "ASSESSMENT" : "EVIDENCE WORKSPACE"}</p>
      <nav aria-label={mode === "SIMPLE" ? "Simple navigation" : "Expert navigation"}>{(mode === "EXPERT" ? expertSections : [expertSections[0]]).map((section) => <button key={section.id} className="sidebar-nav-item" aria-current={(mode === "SIMPLE" || view === section.id) ? "page" : undefined} onClick={() => navigate(useCase, mode, section.id)}><span>{section.label}</span>{view === section.id && <span className="nav-active-dot" />}</button>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-principle"><ScanLine size={19} strokeWidth={1.3} /><p>Evidence before action.<span>Observe. Understand. Verify.</span></p></div><Link href="/"><ArrowLeft size={14} /> Back to Earth view</Link><span className="sidebar-credit">A Beyond The Limit project</span></div>
    </aside>
    <main id="main-content" className="workspace-main">
      <div className="workspace-toolbar"><div className="workspace-use-case"><label htmlFor="workspace-use-case">Use case</label><select id="workspace-use-case" value={useCase} onChange={(event) => navigate(parseUseCase(event.target.value), mode)}>{useCases.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></div><ModeSwitch mode={mode} onChange={(next) => navigate(useCase, next)} /></div>
      <AnalysisActivity completed={completed} error={error} />
      {error ? <section className="load-error" role="alert"><h1>Evidence package unavailable</h1><p>{error}</p><p>No assessment is displayed until the local package is complete and consistent.</p><button className="button button-primary" onClick={() => setAttempt((value) => value + 1)}>Retry local package</button></section> : data ? <>
        <div className="snapshot-note"><span className="location-dot gold" /><p>Saved Konya assessment · retrospective demo. Location selection elsewhere does not imply analysis.</p></div>
        <div id="mode-panel" key={mode + view} className="evidence-enter">{mode === "SIMPLE" ? <SimpleShell data={data} onExpert={() => navigate(useCase, "EXPERT", "spatial")} /> : <ExpertShell data={data} view={view} onView={(next) => navigate(useCase, mode, next)} />}</div>
        <ProductFlow useCase={useCase} />
        <EvidenceAvailability contract={data.contract} />
      </> : <section className="package-loading"><h1>Opening the validated Konya scene</h1><p>Reading the saved evidence package from this application.</p></section>}
      <footer className="workspace-footer"><span><span className="location-dot gold" /> Konya validated demo · decision support only</span><span>Syria & the Arab region <span className="footer-slash">/</span> target deployment only</span></footer>
    </main>
  </div>;
}
