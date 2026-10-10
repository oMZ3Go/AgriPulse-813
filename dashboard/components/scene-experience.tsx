"use client";

import { useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, ArrowUpRight, ChevronLeft, Fingerprint, Layers3, Sprout } from "lucide-react";
import { EarthGlobe } from "@/components/earth-globe";
import { CountrySelector } from "@/components/country-selector";
import { UseCasePicker } from "@/components/use-case-picker";
import { ModeSwitch } from "@/components/mode-switch";
import { countryById, type Country } from "@/lib/scenes";
import { parseMode, parseUseCase, productUrl, useCases, type Mode, type UseCase } from "@/lib/product";

export function SceneExperience({ variant }: { variant: "landing" | "selection" }) {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selected = countryById(search.get("country"));
  const useCase = parseUseCase(search.get("useCase"));
  const mode = parseMode(search.get("mode"));
  const isLanding = variant === "landing";
  const selectCountry = useCallback((country: Country) => {
    router.replace(productUrl(pathname, useCase, mode, { country: country.id }), { scroll: false });
  }, [pathname, router, useCase, mode]);
  function updateProduct(nextCase: UseCase, nextMode: Mode) {
    router.replace(productUrl(pathname, nextCase, nextMode, selected ? { country: selected.id } : {}), { scroll: false });
  }
  const sceneUrl = productUrl("/scene", useCase, mode, selected ? { country: selected.id } : {});
  const demoUrl = productUrl("/dashboard", useCase, mode);
  return <main id="main-content">
    <section className={`experience ${isLanding ? "hero intro-sequence" : "scene-experience"}`} aria-label={isLanding ? "AgriPulse introduction" : "Geographic selection"}>
      <div className="experience-copy">
        {isLanding ? <>
          <p className="eyebrow intro-copy"><span className="little-line" /> A clearer view. A considered response.</p>
          <h1 className="intro-copy">From spectral<br />signals to<br /><span>grounded decisions.</span></h1>
          <p className="hero-description intro-copy">Earth-observation intelligence that brings spectral detail and temporal context together. A clearer starting point for verification on the ground.</p>
          <div className="hero-actions intro-cta"><Link className="button button-primary" href={sceneUrl}>Choose an area <ArrowUpRight size={18} /></Link><Link className="text-button" href={demoUrl}>Open validated demo <ArrowRight size={15} /></Link></div>
          <div className="creator-line"><span className="creator-mark">BTL</span><p>A <strong>Beyond The Limit</strong> project<span>Arab Youth Space Hackathon · Challenge 813</span></p></div>
        </> : <>
          <Link href="/" className="back-link"><ChevronLeft size={14} /> Back to Earth view</Link>
          <p className="eyebrow"><span className="little-line" /> 01 / Choose your perspective</p>
          <h1>One real scene.<br /><span>A wider ambition.</span></h1>
          <p className="hero-description">Choose how you want to work, then select a country. The validated Konya scene is ready to explore.</p>
          <UseCasePicker value={useCase} onChange={(next) => updateProduct(next, mode)} />
          <p className="use-case-detail">{useCases.find((item) => item.id === useCase)?.detail}</p>
          <div className="presentation-choice"><p className="eyebrow">Presentation depth</p><ModeSwitch mode={mode} onChange={(next) => updateProduct(useCase, next)} /><p>Any use case, either view.</p></div>
        </>}
      </div>
      <div className="earth-column intro-earth">
        <div className="earth-topline"><span className="mono">EARTH / GEOGRAPHIC SELECTION</span><span className="earth-topline-rule" /><span className="mono">813</span></div>
        <CountrySelector selected={selected} onSelect={selectCountry} />
        <EarthGlobe selected={selected} onSelect={selectCountry} />
        <div className="globe-region-controls" aria-label="Featured regions">
          <button onClick={() => selectCountry(countryById("792")!)} aria-pressed={selected?.id === "792"}><span className="location-dot gold" /><span>Konya, Turkey<small>Current validated demo scene</small></span><ArrowUpRight size={15} /></button>
          <button onClick={() => selectCountry(countryById("760")!)} aria-pressed={selected?.id === "760"}><span className="location-dot teal hollow" /><span>Syria<small>Target deployment · not validated</small></span></button>
        </div>
        {selected ? <section className="area-selection scene-detail" aria-label="Area selection">
          <div role="status"><p className="eyebrow teal-text">Location selected · {selected.name}</p><h2>Choose an area to analyse</h2><p>A country selection provides geographic context. It does not mean the country has been analysed.</p></div>
          {selected.id === "792" ? <div className="validated-area"><p className="eyebrow gold-text">Current validated demo scene</p><h3>Konya, Turkey</h3><p>Planet Tanager + Sentinel-2 · 8 June 2025 scene</p><Link href={demoUrl} className="button button-primary">Open validated demo <ArrowRight size={16} /></Link></div> :
            <><p>{selected.id === "760" ? "Syria is our target deployment context. " : ""}Live global EO processing has not yet been executed for this location in this PoC. The validated Konya demo is available now.</p><Link href={demoUrl} className="text-button">Open validated Konya demo <ArrowRight size={14} /></Link></>}
          <details className="aoi-future"><summary>Area selection options · upcoming</summary><p>Point, bounding box and polygon selection are planned for agricultural areas. Drawing and live analysis are not connected yet.</p><div className="aoi-options"><span>Point</span><span>Bounding box</span><span>Polygon</span></div></details>
        </section> : <p className="scene-prompt">Search or click a country to choose your starting point.</p>}
      </div>
    </section>
    {isLanding && <section className="product-section" aria-label="Choose a product flow"><div><p className="eyebrow">Three ways to begin</p><h2>Your purpose. Your perspective.</h2></div><UseCasePicker value={useCase} onChange={(next) => updateProduct(next, mode)} /><p className="use-case-detail">{useCases.find((item) => item.id === useCase)?.detail}</p><Link className="text-button" href={sceneUrl}>Continue with {useCases.find((item) => item.id === useCase)?.label} <ArrowRight size={15} /></Link></section>}
    <section className="evidence-strip" aria-label="The evidence approach"><div className="evidence-intro"><p className="eyebrow">The evidence approach</p><p>Understand more.<br /><span>Assume less.</span></p></div><EvidenceStep number="01" icon={<Layers3 size={18} />} title="Spectral detail" text="Look beyond what the eye can see." /><EvidenceStep number="02" icon={<Fingerprint size={18} />} title="Temporal context" text="Understand the signal over time." /><EvidenceStep number="03" icon={<Sprout size={18} />} title="Grounded action" text="Verify in the field before acting." /></section>
    <p className="demo-disclosure">“Validated demo scene” identifies the processed dataset. Satellite screening is not a diagnosis or ground-truth confirmation.</p>
    <footer className="site-footer"><span>AgriPulse-813 <span className="footer-slash">/</span> Beyond The Limit</span><span>Evidence before action.</span></footer>
  </main>;
}
function EvidenceStep({ number, icon, title, text }: { number: string; icon: React.ReactNode; title: string; text: string }) {
  return <div className="evidence-step"><span className="evidence-number mono">{number}</span><div><h2>{icon}{title}</h2><p>{text}</p></div></div>;
}
