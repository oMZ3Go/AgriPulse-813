"use client";

import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { Eraser, Hand, Minus, Plus, RotateCcw, Scan, SquareDashed, Trash2 } from "lucide-react";
import type { Country } from "@/lib/scenes";
import type { BBox } from "@/lib/aoi";
import { clamp, frameAt, project, unproject, type MapFrame, type Position } from "@/lib/map-projection";
import { useLanguage } from "./language-provider";

type Feature = { id: string; geometry: { type: "Polygon"; coordinates: Position[][] } | { type: "MultiPolygon"; coordinates: Position[][][] } };
const ringsOf = (feature: Feature) => feature.geometry.type === "Polygon" ? feature.geometry.coordinates : feature.geometry.coordinates.flat();
function countryFrame(country: Country, features: Feature[]): MapFrame {
  const feature = features.find((item) => item.id === country.id);
  const rings = feature ? ringsOf(feature) : [];
  const nearby = rings.filter((ring) => ring.some(([lng, lat]) => Math.abs(lng - country.lng) < 8 && Math.abs(lat - country.lat) < 8));
  const points = (nearby.length ? nearby : rings).flat().map(([lng, lat]) => project(lng, lat));
  const [x, y] = project(country.lng, country.lat);
  if (!points.length) return frameAt(x, y, 24 / 360);
  const xs = points.map(([x]) => x), ys = points.map(([, y]) => y);
  const width = Math.max(Math.max(...xs) - Math.min(...xs), (Math.max(...ys) - Math.min(...ys)) * 2) * 1.25;
  return frameAt(x, y, clamp(width, 3 / 360, 170 / 360));
}

export default function AoiMap({ country, box, onDraw, tool, onToolChange, onClear, canClear }: { country: Country; box: BBox | null; onDraw: (box: BBox) => void; tool: "draw" | "pan"; onToolChange: (tool: "draw" | "pan") => void; onClear: () => void; canClear: boolean }) {
  const { t, language } = useLanguage();
  const map = useRef<SVGSVGElement>(null);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [failed, setFailed] = useState(false);
  const [tileErrors, setTileErrors] = useState<Set<string>>(() => new Set());
  const [frame, setFrame] = useState<MapFrame>(() => frameAt(...project(country.lng, country.lat), 24 / 360));
  const [pixels, setPixels] = useState(640);
  const [visible, setVisible] = useState(false);
  const [preview, setPreview] = useState<BBox | null>(null);
  const drag = useRef<{ point: Position; frame: MapFrame; x: number; y: number } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/globe/countries.json", { signal: controller.signal }).then((response) => {
      if (!response.ok) throw new Error("Geography unavailable");
      return response.json();
    }).then((data) => { setFeatures(data.features); setFrame(countryFrame(country, data.features)); }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [country]);
  useEffect(() => {
    if (!map.current) return;
    const resize = new ResizeObserver(([entry]) => setPixels(entry.contentRect.width));
    const intersection = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    resize.observe(map.current); intersection.observe(map.current);
    return () => { resize.disconnect(); intersection.disconnect(); };
  }, []);
  const paths = useMemo(() => features.map((feature) => ({ id: feature.id, path: ringsOf(feature).map((ring) =>
    ring.map(([lng, lat], index) => `${index === 0 || Math.abs(lng - ring[index - 1][0]) > 180 ? "M" : "L"}${project(lng, lat).join(",")}`).join(" ") + "Z"
  ).join(" ") })), [features]);
  const zoomLevel = clamp(Math.floor(Math.log2(pixels / (256 * frame.width))), 0, 19);
  const detail = zoomLevel >= 8;
  const tiles = useMemo(() => {
    if (!detail || !visible) return [];
    const n = 2 ** zoomLevel, result: { key: string; x: number; y: number; size: number }[] = [];
    // Visible tiles only: no prefetch, offline download, cache bypass or secret key.
    for (let y = Math.floor(frame.y * n); y < Math.ceil((frame.y + frame.height) * n); y++) {
      for (let x = Math.floor(frame.x * n); x < Math.ceil((frame.x + frame.width) * n); x++) {
        if (x >= 0 && x < n && y >= 0 && y < n) result.push({ key: `${zoomLevel}/${x}/${y}`, x: x / n, y: y / n, size: 1 / n });
      }
    }
    return result;
  }, [detail, visible, zoomLevel, frame]);
  const tilesUnavailable = tiles.some((tile) => tileErrors.has(tile.key));
  function point(event: PointerEvent<SVGSVGElement>): Position {
    const bounds = event.currentTarget.getBoundingClientRect();
    return unproject(frame.x + (event.clientX - bounds.left) / bounds.width * frame.width, frame.y + (event.clientY - bounds.top) / bounds.height * frame.height);
  }
  function boxFrom(a: Position, b: Position): BBox {
    const round = (n: number) => Number(n.toFixed(6));
    return { type: "BoundingBox", west: round(Math.min(a[0], b[0])), east: round(Math.max(a[0], b[0])), south: round(Math.min(a[1], b[1])), north: round(Math.max(a[1], b[1])) };
  }
  function zoom(factor: number) { setFrame((old) => frameAt(old.x + old.width / 2, old.y + old.height / 2, old.width * factor)); }
  function fitSelection() {
    if (!box) return;
    const [west, north] = project(box.west, box.north), [east, south] = project(box.east, box.south);
    setFrame(frameAt((west + east) / 2, (north + south) / 2, Math.max(east - west, (south - north) * 2) * 1.25));
  }
  const shown = preview ?? box;
  const topLeft = shown && project(shown.west, shown.north), bottomRight = shown && project(shown.east, shown.south);
  return <div className="aoi-map-wrap" dir="ltr">
    <div className="map-toolbar" role="group" aria-label={t("Map tools")} dir={language === "ar" ? "rtl" : "ltr"}>
      <button type="button" aria-pressed={tool === "draw"} aria-label={t("Draw a box")} title={t("Draw a box")} onClick={() => onToolChange("draw")}><SquareDashed size={16} /><span>{t("Draw")}</span></button>
      <button type="button" aria-pressed={tool === "pan"} aria-label={t("Pan map")} title={t("Pan map")} onClick={() => onToolChange("pan")}><Hand size={16} /><span>{t("Pan")}</span></button>
      <button type="button" aria-label={t("Clear selection")} title={t("Clear selection")} disabled={!canClear} onClick={onClear}><Trash2 size={16} /><span>{t("Clear")}</span></button>
      <button type="button" aria-label={t("Redraw selection")} title={t("Redraw selection")} disabled={!box} onClick={onClear}><Eraser size={16} /></button>
      <span className="map-tool-divider" aria-hidden="true" />
      <button type="button" aria-label={t("Zoom in")} title={t("Zoom in")} onClick={() => zoom(.5)} disabled={frame.width <= .000001}><Plus size={16} /></button>
      <button type="button" aria-label={t("Zoom out")} title={t("Zoom out")} onClick={() => zoom(2)} disabled={frame.width >= 1}><Minus size={16} /></button>
      <button type="button" aria-label={t("Fit selected area")} title={t("Fit selected area")} onClick={fitSelection} disabled={!box}><Scan size={16} /></button>
      <button type="button" aria-label={t("Reset map")} title={t("Reset map")} onClick={() => setFrame(countryFrame(country, features))}><RotateCcw size={16} /></button>
    </div>
    <svg ref={map} className={`aoi-map ${tool}`} viewBox={`${frame.x} ${frame.y} ${frame.width} ${frame.height}`} role="img" tabIndex={0} aria-label={t("AOI map")} aria-describedby="map-keyboard-help" data-map-ready={features.length > 0 || failed} data-map-x={frame.x} data-map-y={frame.y} data-map-width={frame.width} data-map-height={frame.height} data-basemap={detail ? "openstreetmap" : "local"} data-map-zoom={zoomLevel}
      onKeyDown={(event) => {
        const directions: Record<string, Position> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        if (directions[event.key]) { event.preventDefault(); const [dx, dy] = directions[event.key]; setFrame((old) => frameAt(old.x + old.width / 2 + dx * old.width / 4, old.y + old.height / 2 + dy * old.height / 4, old.width)); }
        if (event.key === "+" || event.key === "=") { event.preventDefault(); zoom(.5); }
        if (event.key === "-") { event.preventDefault(); zoom(2); }
      }}
      onPointerDown={(event) => { if (event.button !== 0) return; event.currentTarget.setPointerCapture(event.pointerId); drag.current = { point: point(event), frame, x: event.clientX, y: event.clientY }; }}
      onPointerMove={(event) => {
        const start = drag.current;
        if (!start) return;
        if (tool === "draw") setPreview(boxFrom(start.point, point(event)));
        else {
          const bounds = event.currentTarget.getBoundingClientRect();
          setFrame(frameAt(start.frame.x + start.frame.width / 2 - (event.clientX - start.x) / bounds.width * start.frame.width, start.frame.y + start.frame.height / 2 - (event.clientY - start.y) / bounds.height * start.frame.height, start.frame.width));
        }
      }}
      onPointerUp={(event) => {
        if (drag.current && tool === "draw" && Math.hypot(event.clientX - drag.current.x, event.clientY - drag.current.y) >= 4) onDraw(boxFrom(drag.current.point, point(event)));
        drag.current = null; setPreview(null);
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      }}
      onPointerCancel={() => { drag.current = null; setPreview(null); }}>
      <title>{t("AOI map")}: {t(country.name)}</title>
      <rect width="1" height="1" fill="#101f20" />
      {paths.map(({ id, path }) => <path key={id} d={path} fill={id === country.id ? "#305348" : "#1d3530"} stroke={id === country.id ? "#72bfb0" : "#536e61"} strokeWidth={id === country.id ? 1.2 : .6} vectorEffect="non-scaling-stroke" />)}
      {tiles.map((tile) => <image key={tile.key} className="context-tile" href={`https://tile.openstreetmap.org/${tile.key}.png`} x={tile.x} y={tile.y} width={tile.size} height={tile.size} onLoad={(event) => {
        event.currentTarget.dataset.loaded = "true";
        setTileErrors((old) => { if (!old.has(tile.key)) return old; const next = new Set(old); next.delete(tile.key); return next; });
      }} onError={() => setTileErrors((old) => new Set(old).add(tile.key))} />)}
      {topLeft && bottomRight && <g><rect x={topLeft[0]} y={topLeft[1]} width={bottomRight[0] - topLeft[0]} height={bottomRight[1] - topLeft[1]} fill="none" stroke="#082c28" strokeWidth="5" vectorEffect="non-scaling-stroke" /><rect data-testid="aoi-rectangle" x={topLeft[0]} y={topLeft[1]} width={bottomRight[0] - topLeft[0]} height={bottomRight[1] - topLeft[1]} fill="#0e80792b" stroke="#a3ffee" strokeWidth="2" vectorEffect="non-scaling-stroke" /></g>}
      {!detail && <text x={project(country.lng, country.lat)[0]} y={project(country.lng, country.lat)[1]} textAnchor="middle" fontSize={frame.width / 55} fill="#f1f4f2" pointerEvents="none">{t(country.name)}</text>}
    </svg>
    <div className="map-attribution" dir="auto"><strong>{t("Geographic context only · not EO evidence")}</strong>{detail ? <span>© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a> · <a href="https://www.openstreetmap.org/fixthemap" target="_blank" rel="noreferrer">{t("Report a map issue")}</a></span> : <span>{t("Local Natural Earth geography · approximate boundaries, not field boundaries.")}</span>}</div>
    <p className="map-help" dir="auto" id="map-keyboard-help">{t("Zoom in for roads and settlements. Arrow keys pan; + / − zoom. Coordinates remain editable below.")}</p>
    {(failed || tilesUnavailable) && <p className="map-tile-status" dir="auto" role="status">{t(tilesUnavailable ? "Detailed map tiles unavailable. The local outline is approximate; use coordinates or try again when online." : "Map unavailable. You can still define your area with coordinates.")}</p>}
  </div>;
}
