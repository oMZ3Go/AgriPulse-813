"use client";

import { useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight, ArrowUpRight, Check, ChevronLeft, Fingerprint, Layers3, MoveUpRight, ScanLine, Sprout } from "lucide-react";
import { EarthGlobe } from "@/components/earth-globe";
import type { SceneId } from "@/lib/scenes";

export function SceneExperience({ variant }: { variant: "landing" | "selection" }) {
  const [selected, setSelected] = useState<SceneId | null>(null);
  const reduced = useReducedMotion();
  const isLanding = variant === "landing";

  return (
    <main id="main-content">
      <section className={`experience ${isLanding ? "hero" : "scene-experience"}`} aria-label={isLanding ? "AgriPulse introduction" : "Scene selection"}>
        <div className="experience-copy">
          {isLanding ? <>
            <p className="eyebrow"><span className="little-line" /> A clearer view. A considered response.</p>
            <h1>From spectral<br />signals to<br /><span>grounded decisions.</span></h1>
            <p className="hero-description">Earth-observation intelligence that combines hyperspectral, temporal, and ground evidence before recommending action.</p>
            <div className="hero-actions"><Link className="button button-primary" href="/scene">Launch Demo <ArrowUpRight size={18} /></Link><span className="quiet-label">Rooted in evidence.<br />Designed for the field.</span></div>
            <div className="creator-line"><span className="creator-mark">BTL</span><p>A <strong>Beyond The Limit</strong> project<span>Arab Youth Space Hackathon · Challenge 813</span></p></div>
          </> : <>
            <Link href="/" className="back-link"><ChevronLeft size={14} /> Back to Earth view</Link>
            <p className="eyebrow"><span className="little-line" /> The starting point</p>
            <h1>One real scene.<br /><span>A wider ambition.</span></h1>
            <p className="hero-description">Explore our current demo in Konya, Turkey. Our intended deployment begins with Syria and the Arab region.</p>
            <div className="scene-options" aria-label="Available regions">
              <button className={`scene-option validated ${selected === "konya" ? "selected" : ""}`} onClick={() => setSelected("konya")} aria-pressed={selected === "konya"}>
                <span className="location-dot gold" /><span><span className="option-kicker">Current validated demo scene</span><strong>Konya, Turkey</strong><span className="option-description">Planet Tanager + Sentinel-2</span></span>{selected === "konya" ? <Check size={18} /> : <ArrowUpRight size={18} />}
              </button>
              <button className={`scene-option target ${selected === "syria" ? "selected" : ""}`} onClick={() => setSelected("syria")} aria-pressed={selected === "syria"}>
                <span className="location-dot teal hollow" /><span><span className="option-kicker">Target deployment</span><strong>Syria and the Arab region</strong><span className="option-description">Future application · no validated analysis</span></span><ArrowUpRight size={18} />
              </button>
            </div>
          </>}
        </div>

        <div className="earth-column">
          <div className="earth-topline"><span className="mono">EARTH / REGIONAL CONTEXT</span><span className="earth-topline-rule" /><span className="mono">813</span></div>
          <EarthGlobe selected={selected} onSelect={setSelected} />
          {isLanding && <div className="globe-region-controls" aria-label="Explore regions"><button onClick={() => setSelected("konya")} aria-pressed={selected === "konya"}><span className="location-dot gold" /><span>Konya, Turkey<small>Current validated demo scene</small></span><MoveUpRight size={15} /></button><button onClick={() => setSelected("syria")} aria-pressed={selected === "syria"}><span className="location-dot teal hollow" /><span>Syria<small>Target deployment</small></span></button></div>}
          <AnimatePresence mode="wait">
            {selected && <motion.div className="scene-detail" key={selected} initial={{ opacity: 0, y: reduced ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} role="status">
              {selected === "konya" ? <><div><p className="eyebrow gold-text">Current validated demo scene</p><h2>Konya, Turkey</h2><p>Planet Tanager hyperspectral<br />Sentinel-2 temporal observations</p></div><Link href="/dashboard" className="button button-primary">Open dashboard <ArrowRight size={17} /></Link><p className="scene-disclosure">Explore the interface. Analysis panels are placeholders.</p></> : <><p className="eyebrow teal-text">Target deployment</p><h2>Syria and the Arab region</h2><p>Our intended application context. There is no validated AgriPulse analysis for this region in the current demo.</p><button className="text-button" onClick={() => setSelected("konya")}>Explore the Konya demo <ArrowRight size={16} /></button></>}
            </motion.div>}
          </AnimatePresence>
          {!selected && !isLanding && <p className="scene-prompt"><ScanLine size={16} /> Select Konya to enter the demo workspace.</p>}
        </div>
      </section>

      {isLanding ? <section className="evidence-strip" aria-label="The evidence approach"><div className="evidence-intro"><p className="eyebrow">The evidence approach</p><p>Understand more.<br /><span>Assume less.</span></p></div><EvidenceStep number="01" icon={<Layers3 size={18} />} title="Spectral detail" text="Look beyond what the eye can see." /><EvidenceStep number="02" icon={<Fingerprint size={18} />} title="Temporal context" text="Understand the signal over time." /><EvidenceStep number="03" icon={<Sprout size={18} />} title="Grounded action" text="Verify in the field before acting." /></section> : <div className="selection-note"><span className="mono">DEMO CONTEXT</span><p>“Validated demo scene” identifies the processed dataset. Satellite evidence does not establish ground-truth-confirmed stress.</p></div>}
      <footer className="site-footer"><span>AgriPulse-813 <span className="footer-slash">/</span> Beyond The Limit</span><span>Evidence before action.</span></footer>
    </main>
  );
}

function EvidenceStep({ number, icon, title, text }: { number: string; icon: React.ReactNode; title: string; text: string }) {
  return <div className="evidence-step"><span className="evidence-number mono">{number}</span><div><h2>{icon}{title}</h2><p>{text}</p></div></div>;
}
