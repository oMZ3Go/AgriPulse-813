"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";
import { MeshPhongMaterial } from "three";
import { useReducedMotion } from "framer-motion";
import { Pause, Play, RotateCcw } from "lucide-react";
import { locations, type SceneId } from "@/lib/scenes";
import type { EarthGlobeProps } from "./earth-globe";

export default function GlobeCanvas({ selected, onSelect }: EarthGlobeProps) {
  const globe = useRef<GlobeMethods | undefined>(undefined);
  const container = useRef<HTMLDivElement>(null);
  const onSelectRef = useRef(onSelect);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [ready, setReady] = useState(false);
  const [paused, setPaused] = useState(false);
  const [failed, setFailed] = useState(false);
  const reduced = useReducedMotion();
  const material = useMemo(() => new MeshPhongMaterial({ color: "#c5d6cb", shininess: 3, specular: "#172820" }), []);
  const rotating = !paused && !selected && !reduced;

  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: Math.round(entry.contentRect.width), height: Math.round(entry.contentRect.height) });
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!ready || !globe.current) return;
    const controls = globe.current.controls();
    controls.autoRotate = rotating;
    controls.autoRotateSpeed = 0.22;
    controls.enableZoom = false;
    controls.enablePan = false;
    controls.enableDamping = true;
    controls.rotateSpeed = 0.45;
    const stopOnInteraction = () => setPaused(true);
    controls.addEventListener("start", stopOnInteraction);
    return () => controls.removeEventListener("start", stopOnInteraction);
  }, [ready, rotating]);

  useEffect(() => {
    if (!ready || !selected) return;
    const location = locations.find((item) => item.id === selected)!;
    globe.current?.pointOfView({ lat: location.lat - 3, lng: location.lng - 4, altitude: size.width < 500 ? 1.95 : 1.5 }, reduced ? 0 : 850);
  }, [selected, ready, reduced, size.width]);

  useEffect(() => {
    if (!ready) return;
    const syncVisibility = () => document.hidden ? globe.current?.pauseAnimation() : globe.current?.resumeAnimation();
    document.addEventListener("visibilitychange", syncVisibility);
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !document.hidden) globe.current?.resumeAnimation();
      else globe.current?.pauseAnimation();
    });
    if (container.current) observer.observe(container.current);
    const canvas = container.current?.querySelector("canvas");
    const onLost = (event: Event) => { event.preventDefault(); setFailed(true); };
    canvas?.addEventListener("webglcontextlost", onLost);
    return () => { document.removeEventListener("visibilitychange", syncVisibility); observer.disconnect(); canvas?.removeEventListener("webglcontextlost", onLost); };
  }, [ready]);

  useEffect(() => {
    // A blocked or missing local texture must never leave an indefinite loading screen.
    const timeout = window.setTimeout(() => { if (!ready) setFailed(true); }, 15000);
    return () => window.clearTimeout(timeout);
  }, [ready]);

  const createMarker = useCallback((datum: object) => {
    const location = datum as (typeof locations)[number];
    const button = document.createElement("button");
    button.className = `earth-marker earth-marker-${location.id}`;
    button.setAttribute("aria-label", `${location.name}: ${location.label}`);
    button.dataset.scene = location.id;
    const dot = document.createElement("span");
    dot.className = "marker-dot";
    const label = document.createElement("span");
    label.className = "marker-label";
    const name = document.createElement("strong");
    name.textContent = location.id === "konya" ? "KONYA" : "SYRIA";
    const caption = document.createElement("small");
    caption.textContent = location.label;
    label.append(name, caption);
    button.append(dot, label);
    button.onclick = () => onSelectRef.current(location.id as SceneId);
    return button;
  }, []);

  function onReady() {
    globe.current?.renderer().setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    globe.current?.pointOfView({ lat: 23, lng: 22, altitude: size.width < 500 ? 2.3 : 1.75 }, 0);
    setReady(true);
  }

  function resetView() {
    const location = locations.find((item) => item.id === selected);
    globe.current?.pointOfView(location ? { lat: location.lat - 3, lng: location.lng - 4, altitude: size.width < 500 ? 1.95 : 1.5 } : { lat: 23, lng: 22, altitude: size.width < 500 ? 2.3 : 1.75 }, reduced ? 0 : 850);
  }

  return (
    <div ref={container} className="globe-canvas" data-globe-ready={ready && !failed ? "true" : "false"}>
      {failed ? <div className="globe-placeholder" role="status"><p>Earth view unavailable on this device</p><span>Use the region controls to continue.</span></div> : size.width > 0 && <Globe
        ref={globe}
        width={size.width}
        height={size.height}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl="/globe/earth.svg"
        globeMaterial={material}
        showAtmosphere
        atmosphereColor="#638779"
        atmosphereAltitude={0.055}
        animateIn={false}
        htmlElementsData={locations}
        htmlElement={createMarker}
        htmlAltitude={0.008}
        htmlTransitionDuration={0}
        onGlobeReady={onReady}
        rendererConfig={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      />}
      {!failed && <div className="globe-tools"><span>Drag to explore</span><button onClick={resetView} aria-label="Reset globe view" title="Reset view"><RotateCcw size={14} /></button><button onClick={() => setPaused(!paused)} aria-label={rotating ? "Pause globe rotation" : "Resume globe rotation"} title={selected ? "Rotation pauses while a region is selected" : reduced ? "Rotation disabled by reduced-motion preference" : "Toggle rotation"} disabled={Boolean(selected) || Boolean(reduced)}>{rotating ? <Pause size={14} /> : <Play size={14} />}</button></div>}
      <p className="globe-caption">Geographic context <span>·</span> not scene coverage</p>
    </div>
  );
}
