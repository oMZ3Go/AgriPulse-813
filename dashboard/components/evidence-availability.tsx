import { Check, Minus } from "lucide-react";
import type { Contract } from "@/lib/konya";
const labels = { sentinel: "Sentinel-2", temporal: "Temporal history", hyperspectral: "Hyperspectral", ml: "Experimental ML", weather: "Weather", ground: "Ground Observation", iot: "IoT" } as const;
export function EvidenceAvailability({ contract }: { contract: Contract }) {
  return <section className="availability panel" aria-label="Evidence availability"><div className="panel-header"><div><p className="eyebrow">Data availability</p><h2>What supports this assessment</h2></div><span className="evidence-level">{contract.analysis_level}</span></div><dl>{Object.entries(labels).map(([key, label]) => {
    const state = contract.data_availability[key as keyof typeof labels];
    return <div key={key} data-available={state === "AVAILABLE"}><dt>{state === "AVAILABLE" ? <Check size={13} /> : <Minus size={13} />}{label}</dt><dd>{state.replaceAll("_", " ")}{key === "weather" && <small>Not integrated</small>}</dd></div>;
  })}</dl><p className="availability-note">Analysis level describes evidence richness, not accuracy, probability or a guarantee.</p></section>;
}
