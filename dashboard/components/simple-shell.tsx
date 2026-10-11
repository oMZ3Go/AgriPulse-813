"use client";
import { useLanguage } from "./language-provider";
import { ArrowRight, LockKeyhole, ClipboardCheck } from "lucide-react";
import type { KonyaData } from "@/lib/konya";
import { SectionHeading } from "./ui";
export function SimpleShell({ data, onExpert, onObserve }: { data: KonyaData; onExpert: () => void; onObserve: () => void }) {
  const { t } = useLanguage();
  const { simple } = data;
  return <><SectionHeading eyebrow={t("Konya / Current assessment")} title={t(simple.assessment)} description={t("A real satellite screening, with a clear next step on the ground.")} />
    <section id="take-action" className="assessment-card take-action" aria-label={t("Take action")}><div className="action-heading"><span className="action-icon"><ClipboardCheck size={25} /></span><div><p className="eyebrow gold-text">{t("Take action")} / {t("Recommended next action")}</p><span className="action-priority"><span />{t("Verification required before action")}</span></div></div><div><h2>{t("Inspect before intervening.")}</h2><p>{t(simple.next_action)}</p><a className="button button-primary action-cta" href="#ground-observation" onClick={(event) => { event.preventDefault(); onObserve(); }}>{t("Continue to Ground Observation")}<ArrowRight className="directional" size={16} /></a></div><div className="policy-note"><LockKeyhole size={20} /><div><strong>{t("Automatic intervention: not allowed")}</strong><p>{t("Human review is required. This PoC cannot control irrigation.")}</p></div></div><div className="action-caution"><strong>{t("What not to assume")}</strong><p>{t("The satellite evidence does not independently diagnose drought or disease.")}</p></div></section>
    <div className="simple-evidence-grid">{[
      ["Satellite evidence", simple.satellite, "Relative moisture-risk hotspots identify areas to inspect. They do not establish the cause."],
      ["Recent temporal context", simple.temporal, "Neutral or mixed temporal evidence does not rule out local or short-term concern."],
      ["Experimental Spectral Anomaly ML", "Unusual spectra, unconfirmed cause", simple.ml],
      ["Ground evidence", "Unavailable", "No Ground Observations are present. Site-specific evidence is needed before intervention."],
    ].map(([label, title, text]) => <section className="status-card" key={t(label)}><p className="eyebrow">{t(label)}</p><h2>{t(title)}</h2><p>{t(text)}</p></section>)}</div>
    <p className="science-note">{t("Experimental ML is unsupervised, exploratory, scene-relative and not field-calibrated. It is not a probability, drought detection, disease detection or independent validation of the moisture-risk layer. It does not change the decision.")}</p>
    <button className="text-button review-evidence" onClick={onExpert}>{t("Review maps and scientific evidence in Expert View")}<ArrowRight size={15} /></button>
    <details className="limitations-disclosure"><summary>{t("Interpretation and limitations")}</summary><ul>{simple.projection.key_limitations.map((item) => <li key={t(item)}>{t(item)}</li>)}</ul></details>
  </>;
}
