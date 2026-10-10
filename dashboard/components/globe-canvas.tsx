"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";
import { MeshPhongMaterial } from "three";
import { useReducedMotion } from "framer-motion";
import { RotateCcw } from "lucide-react";
import { countryById, locations } from "@/lib/scenes";
import type { EarthGlobeProps } from "./earth-globe";

export default function GlobeCanvas({ selected, onSelect }: EarthGlobeProps) {
  const globe = useRef<GlobeMethods | undefined>(undefined);
  const container = useRef<HTMLDivElement>(null);
  const onSelectRef = useRef(onSelect);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [ready, setReady] = useState(false);
  const [polygons, setPolygons] = useState<object[]>([]);
  const [hovered, setHovered] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const reduced = useReducedMotion();
  const material = useMemo(() => new MeshPhongMaterial({ color: "#c5d6cb", shininess: 3, specular: "#172820" }), []);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/globe/countries.json", { signal: controller.signal }).then((response) => {
      if (!response.ok) throw new Error("Local geography unavailable");
      return response.json();
    }).then((data) => setPolygons(data.features)).catch((error) => { if (error.name !== "AbortError") setFailed(true); });
    return () => controller.abort();
  }, []);

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
    controls.autoRotate = false;
    controls.enableZoom = false;
    controls.enablePan = false;
    controls.enableDamping = !reduced;
    controls.rotateSpeed = 0.45;
  }, [ready, reduced]);

  useEffect(() => {
    if (!ready || !selected) return;
    globe.current?.pointOfView({ lat: selected.lat, lng: selected.lng, altitude: size.width < 500 ? 1.95 : 1.5 }, reduced ? 0 : 350);
    setFocused(selected.id);
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
    button.onpointerdown = (event) => event.stopPropagation();
    button.onclick = (event) => { event.stopPropagation(); const country = countryById(location.countryId); if (country) onSelectRef.current(country); };
    return button;
  }, []);

  function onReady() {
    globe.current?.renderer().setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    globe.current?.pointOfView({ lat: 23, lng: 22, altitude: size.width < 500 ? 2.3 : 1.75 }, 0);
    setReady(true);
  }

  function resetView() {
    globe.current?.pointOfView(selected ? { lat: selected.lat, lng: selected.lng, altitude: size.width < 500 ? 1.95 : 1.5 } : { lat: 23, lng: 22, altitude: size.width < 500 ? 2.3 : 1.75 }, reduced ? 0 : 350);
  }

  const polygonId = (polygon: object) => (polygon as { id: string }).id;
  const landPalette = ["#344d40", "#3a5144", "#40584a", "#354a40", "#3c5547"];

  return (
    <div ref={container} className="globe-canvas" data-globe-ready={ready && polygons.length > 0 && !failed ? "true" : "false"} data-focused-country={focused} data-focus-lat={selected?.lat} data-focus-lng={selected?.lng} data-hover-country={hovered} style={{ cursor: hovered ? "pointer" : "grab" }}>
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
        polygonsData={polygons}
        polygonCapColor={(polygon) => polygonId(polygon) === selected?.id ? "#4b7b68" : polygonId(polygon) === hovered ? "#496b59" : landPalette[Array.from(polygonId(polygon)).reduce((sum, char) => sum + char.charCodeAt(0), 0) % landPalette.length]}
        polygonSideColor={() => "#1b3229"}
        polygonStrokeColor={(polygon) => polygonId(polygon) === selected?.id ? "#92d7c4" : polygonId(polygon) === hovered ? "#72bfb0" : "#61746355"}
        polygonAltitude={0.002}
        polygonsTransitionDuration={reduced ? 0 : 250}
        polygonLabel={(polygon) => countryById(polygonId(polygon))?.name ?? ""}
        onPolygonHover={(polygon) => setHovered(polygon ? polygonId(polygon) : null)}
        onPolygonClick={(polygon, event) => {
          // HTML locators sit over the WebGL surface; never also pick the land beneath them.
          if (event.target instanceof Element && event.target.closest(".earth-marker")) return;
          const country = countryById(polygonId(polygon)); if (country) onSelectRef.current(country);
        }}
        htmlElementsData={locations}
        htmlElement={createMarker}
        htmlAltitude={0.008}
        htmlTransitionDuration={0}
        onGlobeReady={onReady}
        rendererConfig={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      />}
      {!failed && <div className="globe-tools"><span>Drag to explore · click a country</span><button onClick={resetView} aria-label="Reset globe view" title="Reset view"><RotateCcw size={14} /></button></div>}
      <p className="globe-caption">Geographic context <span>·</span> not scene coverage</p>
    </div>
  );
}
