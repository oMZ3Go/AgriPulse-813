"use client";

import { useRef, useState } from "react";
import { Check, Download, MapPin, LocateFixed } from "lucide-react";
import { areaCenter, bboxString, type BBox } from "@/lib/aoi";
import { emptyObservation, makeObservation, observationOptions, validateObservation, type Observation, type ObservationInput, type ObservationErrors } from "@/lib/observation";
import { useLanguage } from "./language-provider";

export function GroundObservation({ box, country }: { box: BBox; country: string }) {
  const { t } = useLanguage();
  const [input, setInput] = useState<ObservationInput>(emptyObservation);
  const [errors, setErrors] = useState<ObservationErrors>({});
  const [observation, setObservation] = useState<Observation | null>(null);
  const [centerSuggested, setCenterSuggested] = useState(false);
  const [locationReviewed, setLocationReviewed] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const summary = useRef<HTMLDivElement>(null);
  function update(key: keyof ObservationInput, value: string) {
    if (key === "longitude" || key === "latitude") setCenterSuggested(false);
    setInput((old) => ({ ...old, [key]: value, ...(key === "recent_irrigation" && value !== "YES" ? { recent_irrigation_timestamp: "" } : {}) }));
    setErrors((old) => ({ ...old, [key]: undefined, ...(key === "recent_irrigation" ? { recent_irrigation_timestamp: undefined } : {}) }));
  }
  function attributes(key: keyof ObservationInput) {
    return { id: `ground-${key}`, name: key, value: input[key], "aria-invalid": Boolean(errors[key]), "aria-describedby": errors[key] ? `ground-error-${key}` : undefined, onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => update(key, event.target.value) };
  }
  function error(key: keyof ObservationInput) { return errors[key] ? <span className="field-error" id={`ground-error-${key}`}>{t(errors[key]!)}</span> : null; }
  function exportDraft() {
    const draft = { schema_version: "5C.draft.1", storage: "LOCAL_EXPORT_ONLY", included_in_saved_assessment: false, selected_aoi: { country, crs: "EPSG:4326", geometry: box }, observation };
    const url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2) + "\n"], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `agripulse-ground-observation-${observation!.observation_id}.json`; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section id="ground-observation" className="ground-observation panel" aria-label={t("Field verification pathway")}>
    <div className="ground-heading"><MapPin size={23} /><div><p className="eyebrow">{t("Verify My Field")}</p><h2>{t("Ground Observation")}</h2><p>{t("Capture what you observed on site.")}</p></div><span className="local-badge">{t("Self-reported · not independently verified")}</span></div>
    <p className="ground-disclosure">{t("Human input is ground evidence; it is not automatically verified ground truth.")} {t("A local draft is separate from the saved assessment. It does not update the decision, availability or analysis level.")}</p>
    <div className="ground-aoi"><span>{t("Selected site")}: {t(country)}</span><bdi>{bboxString(box)}</bdi></div>
    {observation ? <div className="observation-summary confirmation-feedback" ref={summary} tabIndex={-1}>
      <p className="capture-success" role="status"><Check size={19} />{t("Ground observation captured locally. Persistent storage / backend integration is not yet enabled.")}</p>
      <h3>{t("Observation summary")}</h3><dl>{[
        ["Observer", t(observation.observer_type)], ["Crop", observation.crop_type], ["Plant condition", t(observation.plant_condition)],
        ["Soil condition", t(observation.soil_condition)], ["Recent irrigation", t(observation.recent_irrigation)],
        ["Location", `${observation.location.latitude}, ${observation.location.longitude}`], ["Timestamp", observation.timestamp], ["Verification state", observation.verification_state],
      ].map(([label, value]) => <div key={label}><dt>{t(label)}</dt><dd><bdi>{value}</bdi></dd></div>)}</dl>
      <p className="form-help">{t("This draft stays in this page until you leave or reload. Export it to keep a copy.")}</p>
      <div className="ground-actions"><button className="button button-primary" onClick={exportDraft}><Download size={16} />{t("Export JSON draft")}</button><button className="button button-secondary" onClick={() => { setObservation(null); requestAnimationFrame(() => form.current?.querySelector<HTMLInputElement>("input")?.focus()); }}>{t("Edit observation")}</button></div>
    </div> : <form ref={form} noValidate onSubmit={(event) => {
      event.preventDefault(); const nextErrors = validateObservation(input, box);
      if (centerSuggested && !locationReviewed) nextErrors.longitude = "Check the suggested coordinates against the actual observation point, or edit them.";
      setErrors(nextErrors);
      if (Object.keys(nextErrors).length) { requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()); return; }
      setObservation(makeObservation(input)); requestAnimationFrame(() => summary.current?.focus());
    }}>
      <p className="form-help">{t("Required fields are marked *.")}</p>
      {Object.values(errors).some(Boolean) && <p role="alert" className="field-error">{t("Please correct the highlighted fields.")}</p>}
      <div className="observation-fields">
        <label htmlFor="ground-crop_type">{t("Crop type")} *<input {...attributes("crop_type")} required maxLength={120} autoComplete="off" />{error("crop_type")}</label>
        {(Object.keys(observationOptions) as (keyof typeof observationOptions)[]).map((key) => <label htmlFor={`ground-${key}`} key={key}>{t({ observer_type: "Observer type", plant_condition: "Plant condition", soil_condition: "Soil condition", recent_irrigation: "Recent irrigation" }[key])} *<select {...attributes(key)} required><option value="">{t("Choose…")}</option>{observationOptions[key].map((value) => <option value={value} key={value}>{t(value)}</option>)}</select>{error(key)}</label>)}
        <label htmlFor="ground-timestamp">{t("Observation timestamp (UTC)")} *<input {...attributes("timestamp")} type="datetime-local" step="1" dir="ltr" required />{error("timestamp")}<span className="form-help">{t("Use the actual observation time, in UTC.")}</span></label>
        <label htmlFor="ground-recent_irrigation_timestamp">{t("Irrigation date and time (optional)")}<input {...attributes("recent_irrigation_timestamp")} type="datetime-local" step="1" dir="ltr" disabled={input.recent_irrigation !== "YES"} />{error("recent_irrigation_timestamp")}</label>
      </div>
      <fieldset className="observation-location"><legend><MapPin size={16} />{t("Observation point · WGS84")}</legend><p className="form-help" id="observation-location-help">{t("Enter the actual observation point inside the selected AOI; the box center is not assumed.")}</p>
        <button type="button" className="button button-secondary location-helper" onClick={() => {
          const center = areaCenter(box);
          setInput((old) => ({ ...old, longitude: String(center.longitude), latitude: String(center.latitude) }));
          setErrors((old) => ({ ...old, longitude: undefined, latitude: undefined }));
          setCenterSuggested(true); setLocationReviewed(false);
        }}><LocateFixed size={16} />{t("Use AOI center as starting point")}</button>
        <p className="form-help">{t("Convenience only: this is not a GPS reading. Check or edit both coordinates before capture.")}</p>
        <div className="observation-fields">
        {(["longitude", "latitude"] as const).map((key) => <label htmlFor={`ground-${key}`} key={key}>{t(key === "longitude" ? "Observation longitude" : "Observation latitude")} *<input {...attributes(key)} aria-describedby={`observation-location-help ground-range-${key}${errors[key] ? ` ground-error-${key}` : ""}`} dir="ltr" inputMode="decimal" required /><span id={`ground-range-${key}`} className="coordinate-range"><span>{t("Inside AOI")}</span><bdi>{key === "longitude" ? `${box.west.toFixed(6)} … ${box.east.toFixed(6)}` : `${box.south.toFixed(6)} … ${box.north.toFixed(6)}`} °</bdi></span>{error(key)}</label>)}
      </div>{centerSuggested && <label className="location-review"><input type="checkbox" checked={locationReviewed} onChange={(event) => { setLocationReviewed(event.target.checked); setErrors((old) => ({ ...old, longitude: undefined })); }} />{t("I checked that these coordinates are the actual observation point.")}</label>}</fieldset>
      <div className="observation-fields">
        <label htmlFor="ground-symptoms">{t("Symptoms (optional)")}<textarea {...attributes("symptoms")} rows={3} maxLength={2000} /></label>
        <label htmlFor="ground-notes">{t("Notes (optional)")}<textarea {...attributes("notes")} rows={3} maxLength={4000} /></label>
        <label htmlFor="ground-photo_reference">{t("Photo reference (optional)")}<input {...attributes("photo_reference")} maxLength={512} /><span className="form-help">{t("A filename or reference only; no photo is uploaded.")}</span></label>
      </div>
      <p className="form-help">{t("This draft stays in this page until you leave or reload. Export it to keep a copy.")}</p>
      <button type="submit" className="button button-primary">{t("Capture locally")}<Check size={16} /></button>
    </form>}
  </section>;
}
