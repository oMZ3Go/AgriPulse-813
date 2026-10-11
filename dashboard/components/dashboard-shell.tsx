"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowUpRight, ChevronRight, ScanLine, MapPin, CheckCircle2, CircleDashed, Layers3 } from "lucide-react";
import { Brand } from "@/components/brand";
import { ModeSwitch } from "@/components/mode-switch";
import { SimpleShell } from "@/components/simple-shell";
import { ExpertShell } from "@/components/expert-shell";
import { AnalysisActivity } from "@/components/analysis-activity";
import { EvidenceAvailability } from "@/components/evidence-availability";
import { ProductFlow } from "@/components/product-flow";
import { GroundObservation } from "./ground-observation";
import { LanguageSwitcher, useLanguage } from "./language-provider";
import { expertSections, type ExpertSection } from "@/lib/scenes";
import { loadKonya, type KonyaData } from "@/lib/konya";
import { selectedArea, bboxString, areaCenter, type BBox } from "@/lib/aoi";
import { parseMode, parseUseCase, productUrl, useCases, type Mode, type UseCase } from "@/lib/product";

export function DashboardShell() {
  const search = useSearchParams();
  const router = useRouter();
  const { t } = useLanguage();
  const mode = parseMode(search.get("mode"));
  const useCase = parseUseCase(search.get("useCase"));
  const view: ExpertSection = expertSections.find((section) => section.id === search.get("view"))?.id ?? "overview";
  // Legacy /dashboard is the validated demo. Any custom/malformed AOI must never fall back to Konya.
  const isKonya = (!search.has("aoi") || search.get("aoi") === "konya") && !search.has("bbox") && (!search.has("country") || search.get("country") === "792");
  const customArea = search.get("aoi") === "custom" ? selectedArea(search.get("country"), search.get("bbox")) : null;
  const [data, setData] = useState<KonyaData | null>(null);
  const [completed, setCompleted] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const navigation = useRef<HTMLElement>(null);
  const country = isKonya ? "Konya, Turkey" : customArea?.country.name ?? "Invalid area";
  const box: BBox | null = isKonya && data ? { ...data.contract.aoi.geometry, type: "BoundingBox" } : customArea?.geometry ?? null;
  const center = box && areaCenter(box);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError(null); setCompleted(0);
    if (isKonya) loadKonya(controller.signal, (value) => { if (!controller.signal.aborted) setCompleted(value); })
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "The local package could not be read."); });
    return () => controller.abort();
  }, [attempt, isKonya]);
  useEffect(() => {
    navigation.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [view, mode]);
  useEffect(() => {
    if (useCase === "VERIFY_MY_FIELD" && window.location.hash === "#ground-observation") document.getElementById("ground-observation")?.scrollIntoView();
  }, [useCase, data]);
  function navigate(nextCase: UseCase, nextMode: Mode, nextView = view, anchor = "") {
    const extra: Record<string, string> = {};
    for (const key of ["aoi", "country", "bbox"]) if (search.has(key)) extra[key] = search.get(key)!;
    if (nextView !== "overview") extra.view = nextView;
    router.replace(productUrl("/dashboard", nextCase, nextMode, extra) + anchor, { scroll: false });
    if (anchor) requestAnimationFrame(() => document.getElementById(anchor.slice(1))?.scrollIntoView());
  }
  function changeView(next: ExpertSection) {
    navigate(useCase, mode, next);
    document.getElementById("evidence-section")?.scrollIntoView();
  }
  const locationUrl = productUrl("/scene", useCase, mode, { country: isKonya ? "792" : customArea?.country.id ?? "" });
  return <div className="workspace" data-mode={mode.toLowerCase()}>
    <header className="workspace-header"><Brand compact /><div className="workspace-breadcrumb"><span>{t(isKonya ? "Validated demo" : "Selected site")}</span><ChevronRight className="directional" size={13} /><span>{t(country)}</span></div><Link href={locationUrl} className="change-scene">{t("Choose location")}<ArrowUpRight className="directional" size={14} /></Link><LanguageSwitcher /></header>
    <aside className="workspace-sidebar" aria-label={t("Workspace navigation")}>
      <div className="sidebar-scene" data-validated={isKonya}><span className="eyebrow"><MapPin size={13} />{t(isKonya ? "Current scene" : "Selected site")}</span><h2><span className={`location-dot ${isKonya ? "gold" : "teal"}`} />{t(country)}</h2><p className={isKonya ? "gold-text" : "teal-text"}>{t(isKonya ? "Current validated demo scene" : customArea ? "Analysis not performed" : "Invalid area")}</p><span className="mono">{isKonya ? t("8 JUN 2025 / SAVED EVIDENCE") : t(customArea ? "AOI selected" : "No area selected")}</span></div>
      <p className="sidebar-nav-label mono"><Layers3 size={13} />{t(mode === "SIMPLE" ? "ASSESSMENT" : "EVIDENCE WORKSPACE")}</p>
      <nav ref={navigation} aria-label={t(mode === "SIMPLE" ? "Simple navigation" : "Expert navigation")}>{(mode === "EXPERT" && isKonya ? expertSections : [expertSections[0]]).map((section) => <button key={section.id} className="sidebar-nav-item" aria-current={(mode === "SIMPLE" || !isKonya || view === section.id) ? "page" : undefined} onClick={() => changeView(section.id)}><span>{t(section.label)}</span>{view === section.id && <span className="nav-active-dot" />}</button>)}
        {useCase === "VERIFY_MY_FIELD" && box && <a className="sidebar-nav-item ground-nav" href="#ground-observation">{t("Ground Observation")}</a>}
        {useCase === "SMART_FARM" && box && <a className="sidebar-nav-item" href="#site-monitoring">{t("Smart Farm")}</a>}
        {isKonya && data && <a className="sidebar-nav-item" href="#evidence-availability">{t("Data availability")}</a>}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-principle"><ScanLine size={19} strokeWidth={1.3} /><p>{t("Evidence before action.")}<span>{t("Observe. Understand. Verify.")}</span></p></div><Link href="/"><ArrowLeft className="directional" size={14} />{t("Back to Earth view")}</Link><span className="sidebar-credit">Beyond The Limit</span></div>
    </aside>
    <div className="workspace-toolbar" role="region" aria-label={t("Workspace controls")}><div className="workspace-use-case"><label htmlFor="workspace-use-case">{t("Use case")}</label><select id="workspace-use-case" value={useCase} onChange={(event) => navigate(parseUseCase(event.target.value), mode)}>{useCases.map((item) => <option value={item.id} key={item.id}>{t(item.label)}</option>)}</select></div><ModeSwitch mode={mode} onChange={(next) => navigate(useCase, next)} /></div>
    <main id="main-content" className="workspace-main">
      {isKonya && <AnalysisActivity completed={completed} error={error} />}
      <div id="evidence-section" className="evidence-anchor" />
      {!isKonya ? customArea ? <section className="selected-site panel" aria-label={t("Selected site")}><p className="eyebrow teal-text" role="status"><CheckCircle2 size={18} />{t("AOI selected")}</p><h1>{t("No EO assessment available for this area")}</h1><div className="site-readiness"><p><CircleDashed size={19} /><span><strong>{t("Live EO analysis not executed in this PoC")}</strong><small>{t("Live global EO processing has not yet been executed for this location in this PoC.")}</small></span></p><p><Layers3 size={19} /><span><strong>{t("Validated Konya demo available")}</strong><small>{t("Selecting an area does not start satellite processing or establish evidence availability.")}</small></span></p></div><dl className="area-metadata"><div><dt>{t("Selected country")}</dt><dd>{t(country)}</dd></div><div><dt>{t("Bounding box")}</dt><dd dir="ltr">{bboxString(customArea.geometry)}</dd></div><div><dt>{t("Approximate center")}</dt><dd dir="ltr">{center?.latitude.toFixed(6)}, {center?.longitude.toFixed(6)}</dd></div></dl><div className="site-actions"><Link className="text-button" href={locationUrl}>{t("Edit area")}<ArrowUpRight className="directional" size={15} /></Link><Link className="button button-secondary" href={productUrl("/dashboard", useCase, mode, { aoi: "konya" })}>{t("Open validated Konya demo")}</Link></div></section> : <section className="load-error" role="alert"><h1>{t("Invalid area")}</h1><p>{t("The area link is incomplete or invalid. Define and confirm an area to continue.")}</p><Link className="button button-primary" href={locationUrl}>{t("Choose an area")}</Link></section> : error ? <section className="load-error" role="alert"><h1>{t("Evidence package unavailable")}</h1><p>{t(error)}</p><p>{t("No assessment is displayed until the local package is complete and consistent.")}</p><button className="button button-primary" onClick={() => setAttempt((value) => value + 1)}>{t("Retry local package")}</button></section> : data ? <>
        <div className="snapshot-note"><span className="location-dot gold" /><p>{t("Saved Konya assessment · retrospective demo. Location selection elsewhere does not imply analysis.")}</p></div>
        <details className="validated-footprint"><summary>{t("Area of interest")} · {t("Konya, Turkey")}</summary><p dir="ltr" data-testid="validated-bbox">{box && bboxString(box)}</p><p><bdi>20250608_091605_90_4001</bdi> · <bdi>{data.contract.analysis_level}</bdi></p></details>
        <div id="mode-panel" key={mode + view} className="evidence-enter">{mode === "SIMPLE" ? <SimpleShell data={data} onExpert={() => navigate(useCase, "EXPERT", "spatial")} onObserve={() => navigate("VERIFY_MY_FIELD", mode, view, "#ground-observation")} /> : <ExpertShell data={data} view={view} onView={changeView} />}</div>
      </> : <section className="package-loading"><h1>{t("Opening the validated Konya scene")}</h1><p>{t("Reading the saved evidence package from this application.")}</p></section>}
      {box && <div className="workflow-content">
        <div hidden={useCase !== "VERIFY_MY_FIELD"}><GroundObservation key={bboxString(box)} box={box} country={country} /></div>
        <ProductFlow useCase={useCase} />
      </div>}
      {isKonya && data && <EvidenceAvailability contract={data.contract} />}
      <footer className="workspace-footer"><span><span className={`location-dot ${isKonya ? "gold" : "teal"}`} />{t(isKonya ? "Konya validated demo · decision support only" : "AOI selected")}</span><span>{t("Evidence before action.")}</span></footer>
    </main>
  </div>;
}
