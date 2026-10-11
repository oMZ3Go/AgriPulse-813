"use client";
import { useLanguage } from "./language-provider";
import { Check, Minus } from "lucide-react";
import type { Contract } from "@/lib/konya";
const labels = { sentinel: "Sentinel-2", temporal: "Temporal history", hyperspectral: "Hyperspectral", ml: "Experimental ML", weather: "Weather", ground: "Ground Observation", iot: "IoT" } as const;
export function EvidenceAvailability({ contract }: { contract: Contract }) {
  const { t } = useLanguage();
  return <section id="evidence-availability" className="availability panel" aria-label={t("Evidence availability")}><div className="panel-header"><div><p className="eyebrow">{t("Data availability")}</p><h2>{t("What supports this assessment")}</h2></div><span className="evidence-level">{contract.analysis_level}</span></div><dl>{Object.entries(labels).map(([key, label]) => {
    const state = contract.data_availability[key as keyof typeof labels];
    return <div key={key} data-available={state === "AVAILABLE"}><dt>{state === "AVAILABLE" ? <Check size={13} /> : <Minus size={13} />}{t(label)}</dt><dd>{t(state.replaceAll("_", " "))}{key === "weather" && <small>{t("Not integrated")}</small>}</dd></div>;
  })}</dl><p className="availability-note">{t("Analysis level describes evidence richness, not accuracy, probability or a guarantee.")}</p></section>;
}
