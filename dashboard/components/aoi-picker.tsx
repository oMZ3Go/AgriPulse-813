"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, MapPin } from "lucide-react";
import { areaCenter, areaKm2, bboxString, coordinateKeys, coordinateLabels, parseBBox, type BBox } from "@/lib/aoi";
import type { Country } from "@/lib/scenes";
import { productUrl, type Mode, type UseCase } from "@/lib/product";
import { useLanguage } from "./language-provider";
import { WorkflowStepHeading } from "./workflow-step-heading";

const AoiMap = dynamic(() => import("./aoi-map"), { ssr: false });
const invalidMessage = "Enter valid coordinates: −180 ≤ west < east ≤ 180 and −90 ≤ south < north ≤ 90.";

export function AoiPicker({ country, useCase, mode, onAreaChange }: { country: Country; useCase: UseCase; mode: Mode; onAreaChange: (ready: boolean) => void }) {
  const { t } = useLanguage();
  const router = useRouter();
  const coordinateForm = useRef<HTMLFormElement>(null);
  const [values, setValues] = useState(["", "", "", ""]);
  const box = parseBBox(values.map((value) => value.trim()).join(","));
  const [tool, setTool] = useState<"draw" | "pan">("draw");
  const [error, setError] = useState(false);
  function edit(nextValues: string[]) {
    const valid = Boolean(parseBBox(nextValues.map((value) => value.trim()).join(",")));
    setValues(nextValues);
    setError(!valid && (Boolean(box) || error || nextValues.every((value) => value.trim() !== "")));
    onAreaChange(valid);
  }
  function select(next: BBox) {
    edit(coordinateKeys.map((key) => String(next[key])));
  }
  function clear() { edit(["", "", "", ""]); setError(false); setTool("draw"); }
  function useArea() {
    // Drawing and typing share the same WGS84 source of truth and confirmation.
    const parsed = parseBBox(values.map((value) => value.trim()).join(","));
    if (!parsed) { setError(true); coordinateForm.current?.querySelector("input")?.focus(); return; }
    select(parsed);
    router.push(productUrl("/dashboard", useCase, mode, { aoi: "custom", country: country.id, bbox: bboxString(parsed) }) + (useCase === "VERIFY_MY_FIELD" ? "#ground-observation" : ""));
  }
  const center = box && areaCenter(box);
  return <section id="area-selection" tabIndex={-1} data-mode={mode.toLowerCase()} className="aoi-selection panel workflow-target" aria-label={t("Area selection")}>
    <div className="aoi-heading"><div><WorkflowStepHeading step={4} label={t("Area of interest")} /><h2>{t("Choose an area to analyse")}</h2><p>{t("Selected country")}: <strong>{t(country.name)}</strong></p></div><MapPin size={24} /></div>
    <p className="aoi-intro">{t("A country selection provides geographic context. It does not mean the country has been analysed.")} {country.id === "760" && t("Syria is our target deployment context.")}</p>
    <div className="aoi-layout"><div>
      <p className="map-instruction">{t("Drag between two corners on the map, or enter coordinates below.")}</p>
      <AoiMap country={country} box={box} onDraw={select} tool={tool} onToolChange={setTool} onClear={clear} canClear={values.some(Boolean)} />
      <form id="coordinate-form" ref={coordinateForm} className="coordinate-form" onSubmit={(event) => { event.preventDefault(); useArea(); }} noValidate>
        <fieldset><legend>{t("Bounding box")}</legend><div className="coordinate-grid">{coordinateKeys.map((key, index) => <label key={key}>{t(coordinateLabels[index])}<input name={key} aria-invalid={error} aria-describedby={error ? "bbox-error" : "bbox-help"} inputMode="decimal" dir="ltr" value={values[index]} onChange={(event) => edit(values.map((value, i) => index === i ? event.target.value : value))} /></label>)}</div></fieldset>
        <p id="bbox-help" className="form-help">{t("Coordinates are WGS84 decimal degrees. Split areas that cross the antimeridian.")}</p>
        {error && <p id="bbox-error" className="field-error" role="alert">{t(invalidMessage)}</p>}
      </form>
    </div><div id="area-confirmation" tabIndex={-1} className="aoi-summary workflow-target">
      <WorkflowStepHeading step={5} label={t("Confirm area")} />
      <p className="selection-status" role="status"><MapPin size={18} />{t(box ? "Area ready to confirm" : "No area selected")}</p>
      {box && center && <dl className="area-metadata"><div><dt>{t("Bounding box")}</dt><dd dir="ltr">{coordinateKeys.map((key) => box[key].toFixed(6)).join(", ")}</dd></div><div><dt>{t("Approximate center")}</dt><dd dir="ltr">{Math.abs(center.latitude).toFixed(6)}° {center.latitude < 0 ? "S" : "N"}, {Math.abs(center.longitude).toFixed(6)}° {center.longitude < 0 ? "W" : "E"}</dd></div><div><dt>{t("Approximate area")}</dt><dd dir="ltr">{areaKm2(box).toLocaleString("en-US", { maximumFractionDigits: 2 })} km²</dd></div></dl>}
      <p>{t("Country is navigation context; the selected box may cross borders or include water.")}</p>
      <p className="aoi-caution">{t("Live global EO processing has not yet been executed for this location in this PoC.")}</p>
      <button className="button button-primary" type="submit" form="coordinate-form" disabled={!values.some(Boolean)}>{t("Use this area")}<Check size={16} /></button>
      <div className="validated-area"><p className="eyebrow gold-text">{t("Current validated demo scene")}</p><h3>{t("Konya, Turkey")}</h3><p><bdi>20250608_091605_90_4001</bdi></p><Link className="button button-secondary" href={productUrl("/dashboard", useCase, mode, { aoi: "konya" }) + (useCase === "VERIFY_MY_FIELD" ? "#ground-observation" : "")}>{t(country.id === "792" ? "Use validated Konya area" : "Open validated Konya demo")}<ArrowRight className="directional" size={15} /></Link></div>
    </div></div>
  </section>;
}
