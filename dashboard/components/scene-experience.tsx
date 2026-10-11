"use client";
import { useLanguage } from "./language-provider";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, ArrowUpRight, ChevronLeft, Fingerprint, Layers3, Sprout, MapPinned, Check } from "lucide-react";
import { EarthGlobe } from "@/components/earth-globe";
import { CountrySelector } from "@/components/country-selector";
import { UseCasePicker } from "@/components/use-case-picker";
import { AoiPicker } from "./aoi-picker";
import { WorkflowStepHeading } from "./workflow-step-heading";
import { ModeSwitch } from "@/components/mode-switch";
import { countryById, type Country } from "@/lib/scenes";
import { parseMode, parseUseCase, productUrl, useCases, type Mode, type UseCase } from "@/lib/product";

export function SceneExperience({ variant }: { variant: "landing" | "selection" }) {
  const { t } = useLanguage();
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selected = countryById(search.get("country"));
  const useCase = parseUseCase(search.get("useCase"));
  const mode = parseMode(search.get("mode"));
  const isLanding = variant === "landing";
  const [areaReady, setAreaReady] = useState(false);
  const [step, setStep] = useState(selected ? 3 : 0);
  const [visited, setVisited] = useState(selected ? 3 : 0);
  const [stepMessage, setStepMessage] = useState("");
  useEffect(() => { setAreaReady(false); setStepMessage(""); if (selected) { setStep(3); setVisited(3); } }, [selected]);
  const stepIds = ["purpose-selection", "view-selection", "country-selection", "area-selection", "area-confirmation"];
  const labels = ["Choose your purpose", "Choose your view", "Choose country", "Choose AOI", "Confirm area"];
  function goToStep(index: number) {
    if (index >= 3 && !selected) { setStepMessage("Choose a country before defining your area."); return; }
    if (index === 4 && !areaReady) { setStepMessage("Draw a box or enter four valid coordinates before confirmation."); return; }
    setStep(index); setVisited((previous) => Math.max(previous, index)); setStepMessage("");
    const target = document.getElementById(stepIds[index]);
    target?.focus({ preventScroll: true });
    target?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
  }
  const selectCountry = useCallback((country: Country) => {
    router.replace(productUrl(pathname, useCase, mode, { country: country.id }), { scroll: false });
  }, [pathname, router, useCase, mode]);
  function updateProduct(nextCase: UseCase, nextMode: Mode) {
    if (!isLanding) { setStep(nextMode !== mode ? 1 : 0); setVisited((previous) => Math.max(previous, nextMode !== mode ? 1 : 0)); }
    router.replace(productUrl(pathname, nextCase, nextMode, selected ? { country: selected.id } : {}), { scroll: false });
  }
  const sceneUrl = productUrl("/scene", useCase, mode, selected ? { country: selected.id } : {});
  const demoUrl = productUrl("/dashboard", useCase, mode);
  return <main id="main-content" data-mode={mode.toLowerCase()}>
    {!isLanding && <><nav className="workflow-navigation" aria-label={t("Your selection")}><ol className="workflow-progress">{labels.map((label, index) => {
      const available = index < 3 || Boolean(selected) && (index === 3 || areaReady);
      const done = index < 2 ? visited > index : index === 2 ? Boolean(selected) : index === 3 ? areaReady : false;
      return <li key={label} data-step={index + 1} data-done={done}><button type="button" aria-current={index === step ? "step" : undefined} aria-disabled={!available} aria-describedby={!available ? "workflow-step-help" : undefined} onClick={() => goToStep(index)}><span className="step-number">{String(index + 1).padStart(2, "0")}</span><span>{t(label)}{done && <Check size={12} aria-label={t("Complete")} />}</span></button></li>;
    })}</ol></nav><p id="workflow-step-help" className="workflow-step-help" role="status">{t(stepMessage || (!selected ? "Choose a country before defining your area." : !areaReady ? "Draw a box or enter four valid coordinates before confirmation." : "Your area is ready for confirmation."))}</p><Link href="/" className="back-link selection-back"><ChevronLeft size={14} />{t("Back to Earth view")}</Link></>}
    <section className={`experience ${isLanding ? "hero intro-sequence" : "scene-experience"}`} aria-label={isLanding ? "AgriPulse introduction" : "Geographic selection"}>
      <div className="experience-copy">
        {isLanding ? <>
          <p className="eyebrow intro-copy"><span className="little-line" />{t("A clearer view. A considered response.")}</p>
          <h1 className="intro-copy">{t("From spectral")}<br />{t("signals to")}<br /><span>{t("grounded decisions.")}</span></h1>
          <p className="hero-description intro-copy">{t("Earth-observation intelligence that brings spectral detail and temporal context together. A clearer starting point for verification on the ground.")}</p>
          <div className="hero-actions intro-cta"><Link className="button button-primary" href={sceneUrl}><MapPinned size={18} />{t("Choose an area")}</Link><Link className="text-button" href={demoUrl}>{t("Open validated demo")}<ArrowRight size={15} /></Link></div>
          <div className="how-it-works"><p className="eyebrow">{t("How AgriPulse works")}</p>{[["Observe", "Choose a place and review available satellite evidence."], ["Understand", "Compare spectral detail with temporal context."], ["Verify", "Collect site-specific ground evidence before acting."]].map(([title, text], index) => <div key={title}><span className="mono">0{index + 1}</span><p><strong>{t(title)}</strong><span>{t(text)}</span></p></div>)}</div>
        </> : <>
          <div id="purpose-selection" className="workflow-target" tabIndex={-1}><WorkflowStepHeading step={1} label={t("Choose your purpose")} /></div>
          <h1>{t("One real scene.")}<br /><span>{t("A wider ambition.")}</span></h1>
          <p className="hero-description">{t("Choose how you want to work, then select a country. The validated Konya scene is ready to explore.")}</p>
          <UseCasePicker value={useCase} onChange={(next) => updateProduct(next, mode)} />
          <p className="use-case-detail">{t(useCases.find((item) => item.id === useCase)!.detail)}</p>
          <div id="view-selection" tabIndex={-1} className="presentation-choice workflow-target"><WorkflowStepHeading step={2} label={t("Choose your view")} /><ModeSwitch mode={mode} onChange={(next) => updateProduct(useCase, next)} /><p>{t("Any use case, either view.")}</p></div><a className="button button-primary flow-next" href={selected ? "#area-selection" : "#country-selection"} onClick={(event) => { event.preventDefault(); goToStep(selected ? 3 : 2); }}>{t(selected ? "Next: define your area" : "Next: choose a country")}<ArrowRight className="directional" size={16} /></a>
        </>}
      </div>
      <div className="earth-column intro-earth workflow-target" id="country-selection" tabIndex={-1}>
        <div className="earth-topline">{!isLanding ? <WorkflowStepHeading step={3} label={t("EARTH / GEOGRAPHIC SELECTION")} /> : <><span className="mono">{t("EARTH / GEOGRAPHIC SELECTION")}</span><span className="earth-topline-rule" /><span className="mono">813</span></>}</div>
        <CountrySelector selected={selected} onSelect={selectCountry} />
        <EarthGlobe selected={selected} onSelect={selectCountry} idleRotation={isLanding} />
        <div className="globe-region-controls" aria-label={t("Featured regions")}>
          <button onClick={() => selectCountry(countryById("792")!)} aria-pressed={selected?.id === "792"}><span className="location-dot gold" /><span>{t("Konya, Turkey")}<small>{t("Current validated demo scene")}</small></span><ArrowUpRight size={15} /></button>
          <button onClick={() => selectCountry(countryById("760")!)} aria-pressed={selected?.id === "760"}><span className="location-dot teal hollow" /><span>{t("Syria")}<small>{t("Target deployment · not validated")}</small></span></button>
        </div>
        {selected ? <div className="selected-country-next"><p role="status">{t(isLanding ? "Browsing country" : "Location selected")}: <strong>{t(selected.name)}</strong></p>{isLanding && <p className="browsing-note">{t("Explore freely. Choose an area starts the selection workflow.")}</p>}</div> : <p className="scene-prompt">{t(isLanding ? "Explore freely. Choose an area starts the selection workflow." : "Search or click a country to choose your starting point.")}</p>}
      </div>
    </section>
    {!isLanding && selected && <AoiPicker key={selected.id} country={selected} useCase={useCase} mode={mode} onAreaChange={(ready) => { setAreaReady(ready); setStep(ready ? 4 : 3); setStepMessage(""); }} />}
    {isLanding && <section className="product-section" aria-label={t("Choose a product flow")}><div><p className="eyebrow">{t("Three ways to begin")}</p><h2>{t("Your purpose. Your perspective.")}</h2></div><UseCasePicker value={useCase} onChange={(next) => updateProduct(next, mode)} /><p className="use-case-detail">{t(useCases.find((item) => item.id === useCase)!.detail)}</p><div className="landing-view"><span className="eyebrow">{t("Choose your view")}</span><ModeSwitch mode={mode} onChange={(next) => updateProduct(useCase, next)} /></div></section>}
    <section className="evidence-strip" aria-label={t("The evidence approach")}><div className="evidence-intro"><p className="eyebrow">{t("The evidence approach")}</p><p>{t("Understand more.")}<br /><span>{t("Assume less.")}</span></p></div><EvidenceStep number="01" icon={<Layers3 size={18} />} title={t("Spectral detail")} text="Look beyond what the eye can see." /><EvidenceStep number="02" icon={<Fingerprint size={18} />} title={t("Temporal context")} text="Understand the signal over time." /><EvidenceStep number="03" icon={<Sprout size={18} />} title={t("Grounded action")} text="Verify in the field before acting." /></section>
    <p className="demo-disclosure">{t("“Validated demo scene” identifies the processed dataset. Satellite screening is not a diagnosis or ground-truth confirmation.")}</p>
    <footer className="site-footer"><span>{t("AgriPulse-813")}<span className="footer-slash">/</span>{t("Beyond The Limit")}</span><span>{t("Evidence before action.")}</span></footer>
  </main>;
}
function EvidenceStep({ number, icon, title, text }: { number: string; icon: React.ReactNode; title: string; text: string }) {
  const { t } = useLanguage();
  return <div className="evidence-step"><span className="evidence-number mono">{number}</span><div><h2>{icon}{title}</h2><p>{t(text)}</p></div></div>;
}
