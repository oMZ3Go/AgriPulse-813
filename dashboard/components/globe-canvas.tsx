"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";
import { MeshPhongMaterial, PerspectiveCamera } from "three";
import { useReducedMotion } from "framer-motion";
import { useLanguage } from "./language-provider";
import { Minus, Plus, RotateCcw } from "lucide-react";
import { countryById, locations } from "@/lib/scenes";
import type { EarthGlobeProps } from "./earth-globe";

export default function GlobeCanvas({ selected, onSelect, idleRotation = false }: EarthGlobeProps) {
  const { t } = useLanguage();
  // At the closest view the whole sphere and atmosphere fit the smaller dimension.
  const MIN_ALTITUDE = .95, MAX_ALTITUDE = 3;
  const [altitude, setAltitude] = useState(1.75);
  const globe = useRef<GlobeMethods | undefined>(undefined);
  const container = useRef<HTMLDivElement>(null);
  const onSelectRef = useRef(onSelect);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const stageHeight = Math.max(180, size.height - 76);
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
    fitCamera(globe.current.pointOfView().altitude);
    const controls = globe.current.controls();
    controls.autoRotateSpeed = .18;
    controls.enableZoom = true;
    controls.zoomSpeed = .55;
    controls.minDistance = globe.current.getGlobeRadius() * (1 + MIN_ALTITUDE);
    controls.maxDistance = globe.current.getGlobeRadius() * (1 + MAX_ALTITUDE);
    controls.enablePan = false;
    controls.enableDamping = !reduced;
    controls.rotateSpeed = 0.45;
  }, [ready, reduced, size.width, stageHeight]);

  useEffect(() => {
    if (!ready || !globe.current || !container.current) return;
    const controls = globe.current.controls(), element = container.current;
    let interacting = false, visible = true, timer: ReturnType<typeof setTimeout> | undefined;
    const update = () => {
      controls.autoRotate = idleRotation && !selected && !reduced && !interacting && visible && !document.hidden;
      element.dataset.autoRotating = String(controls.autoRotate);
    };
    const pause = () => { clearTimeout(timer); interacting = true; update(); };
    const resume = () => { clearTimeout(timer); timer = setTimeout(() => { interacting = false; update(); }, 6000); };
    const wheel = () => { pause(); resume(); };
    controls.addEventListener("start", pause); controls.addEventListener("end", resume);
    element.addEventListener("pointerdown", pause, true); element.addEventListener("pointerup", resume, true);
    element.addEventListener("wheel", wheel, { passive: true });
    element.addEventListener("focusin", pause); element.addEventListener("focusout", resume);
    document.addEventListener("visibilitychange", update);
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; update(); });
    observer.observe(element); update();
    return () => {
      clearTimeout(timer); controls.autoRotate = false;
      controls.removeEventListener("start", pause); controls.removeEventListener("end", resume);
      element.removeEventListener("pointerdown", pause, true); element.removeEventListener("pointerup", resume, true);
      element.removeEventListener("wheel", wheel); element.removeEventListener("focusin", pause); element.removeEventListener("focusout", resume);
      document.removeEventListener("visibilitychange", update); observer.disconnect();
    };
  }, [ready, idleRotation, selected, reduced]);

  useEffect(() => {
    if (!ready || !selected) return;
    globe.current?.pointOfView({ lat: selected.lat, lng: selected.lng, altitude: size.width < 500 ? 1.95 : 1.5 }, reduced ? 0 : 350);
    setFocused(selected.id);
  }, [selected, ready, reduced, size.width, stageHeight]);

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
    // CSS2DRenderer owns this wrapper's transform on every camera frame.
    // Button hover/active transitions must never interpolate that projection.
    const anchor = document.createElement("div");
    anchor.className = "earth-marker-anchor";
    anchor.dataset.latitude = String(location.lat);
    anchor.dataset.longitude = String(location.lng);
    const button = document.createElement("button");
    button.className = `earth-marker earth-marker-${location.id}`;
    button.setAttribute("aria-label", `${t(location.name)}: ${t(location.label)}`);
    button.dataset.scene = location.id;
    const dot = document.createElement("span");
    dot.className = "marker-dot";
    const label = document.createElement("span");
    label.className = "marker-label";
    const name = document.createElement("strong");
    name.textContent = location.id === "konya" ? t("Konya") : t("Syria");
    const caption = document.createElement("small");
    caption.textContent = t(location.label);
    label.append(name, caption);
    button.append(dot, label);
    button.onpointerdown = (event) => event.stopPropagation();
    button.onclick = (event) => { event.stopPropagation(); const country = countryById(location.countryId); if (country) onSelectRef.current(country); };
    anchor.append(button);
    return anchor;
  }, [t]);

  function onReady() {
    globe.current?.renderer().setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    globe.current?.pointOfView({ lat: 23, lng: 22, altitude: size.width < 500 ? 2.3 : 1.75 }, 0);
    setReady(true);
  }

  function resetView() {
    globe.current?.pointOfView(selected ? { lat: selected.lat, lng: selected.lng, altitude: size.width < 500 ? 1.95 : 1.5 } : { lat: 23, lng: 22, altitude: size.width < 500 ? 2.3 : 1.75 }, reduced ? 0 : 350);
  }

  function zoom(factor: number) {
    const current = globe.current?.pointOfView();
    if (current) globe.current?.pointOfView({ ...current, altitude: Math.max(MIN_ALTITUDE, Math.min(MAX_ALTITUDE, current.altitude * factor)) }, 0);
  }

  function fitCamera(cameraAltitude: number) {
    const camera = globe.current?.camera();
    if (!(camera instanceof PerspectiveCamera)) return;
    // Widen only at close zoom to retain an 8% edge margin including atmosphere.
    const halfFov = Math.max(Math.PI / 6, Math.atan(Math.tan(Math.asin(1.055 / (1 + cameraAltitude))) / .92));
    const fov = 2 * Math.atan(Math.tan(halfFov) / Math.min(1, size.width / stageHeight)) * 180 / Math.PI;
    if (Math.abs(camera.fov - fov) > .0001) { camera.fov = fov; camera.updateProjectionMatrix(); }
  }

  const polygonId = (polygon: object) => (polygon as { id: string }).id;
  const landPalette = ["#344d40", "#3a5144", "#40584a", "#354a40", "#3c5547"];

  return (
    <div ref={container} className="globe-canvas" data-globe-ready={ready && polygons.length > 0 && !failed ? "true" : "false"} data-altitude={altitude.toFixed(4)} data-min-altitude={MIN_ALTITUDE} data-max-altitude={MAX_ALTITUDE} data-focused-country={focused} data-focus-lat={selected?.lat} data-focus-lng={selected?.lng} data-hover-country={hovered} style={{ cursor: hovered ? "pointer" : "grab" }}>
      {failed ? <div className="globe-placeholder" role="status"><p>{t("Earth view unavailable on this device")}</p><span>{t("Use the region controls to continue.")}</span></div> : size.width > 0 && <div className="globe-stage" style={{ height: stageHeight }}><Globe
        ref={globe}
        width={size.width}
        height={stageHeight}
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
        polygonLabel={() => ""}
        onPolygonHover={(polygon) => setHovered(polygon && countryById(polygonId(polygon)) ? polygonId(polygon) : null)}
        onPolygonClick={(polygon, event) => {
          // HTML locators sit over the WebGL surface; never also pick the land beneath them.
          if (event.target instanceof Element && event.target.closest(".earth-marker")) return;
          const country = countryById(polygonId(polygon)); if (country) onSelectRef.current(country);
        }}
        htmlElementsData={locations}
        htmlLat="lat"
        htmlLng="lng"
        htmlElement={createMarker}
        htmlAltitude={0.008}
        htmlTransitionDuration={0}
        onGlobeReady={onReady}
        onZoom={(pov) => { fitCamera(pov.altitude); setAltitude((previous) => Math.abs(previous - pov.altitude) < .00001 ? previous : pov.altitude); }}
        rendererConfig={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      /></div>}
      {hovered && <span className="globe-hover-label" role="status">{t(countryById(hovered)?.name ?? "")}</span>}
      {!failed && <div className="globe-tools"><span>{t("Drag to explore · click a country")}</span><button onClick={() => zoom(.8)} disabled={!ready || altitude <= MIN_ALTITUDE + .001} aria-label={t("Zoom globe in")}><Plus size={14} /></button><button onClick={() => zoom(1.25)} disabled={!ready || altitude >= MAX_ALTITUDE - .001} aria-label={t("Zoom globe out")}><Minus size={14} /></button><button onClick={resetView} aria-label={t("Reset globe view")} title={t("Reset globe view")}><RotateCcw size={14} /></button></div>}
      <p className="globe-caption">{t("Geographic context")} <span>·</span> {t("not scene coverage")}</p>
    </div>
  );
}
