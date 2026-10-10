import { ArrowRight, LockKeyhole } from "lucide-react";
import type { KonyaData } from "@/lib/konya";
import { SectionHeading } from "./ui";
export function SimpleShell({ data, onExpert }: { data: KonyaData; onExpert: () => void }) {
  const { simple } = data;
  return <><SectionHeading eyebrow="Konya / Current assessment" title={simple.assessment} description="A real satellite screening, with a clear next step on the ground." />
    <section className="assessment-card"><div><p className="eyebrow gold-text">Recommended next action</p><h2>Inspect before intervening.</h2><p>{simple.next_action}</p></div><div className="policy-note"><LockKeyhole size={20} /><div><strong>Automatic intervention: not allowed</strong><p>Human review is required. This PoC cannot control irrigation.</p></div></div></section>
    <div className="simple-evidence-grid">{[
      ["Satellite evidence", simple.satellite, "Relative moisture-risk hotspots identify areas to inspect. They do not establish the cause."],
      ["Recent temporal context", simple.temporal, "Neutral or mixed temporal evidence does not rule out local or short-term concern."],
      ["Experimental Spectral Anomaly ML", "Unusual spectra, unconfirmed cause", simple.ml],
      ["Ground evidence", "Unavailable", "No Ground Observations are present. Site-specific evidence is needed before intervention."],
    ].map(([label, title, text]) => <section className="status-card" key={label}><p className="eyebrow">{label}</p><h2>{title}</h2><p>{text}</p></section>)}</div>
    <p className="science-note">Experimental ML is unsupervised, exploratory, scene-relative and not field-calibrated. It is not a probability, drought detection, disease detection or independent validation of the moisture-risk layer. It does not change the decision.</p>
    <button className="text-button review-evidence" onClick={onExpert}>Review maps and scientific evidence in Expert View <ArrowRight size={15} /></button>
    <details className="limitations-disclosure"><summary>Interpretation and limitations</summary><ul>{simple.projection.key_limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
  </>;
}
