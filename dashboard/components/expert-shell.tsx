import { ArrowRight, LockKeyhole } from "lucide-react";
import { SectionHeading } from "@/components/ui";
import { ScientificFigure } from "@/components/scientific-figure";
import type { KonyaData } from "@/lib/konya";
import { expertSections, type ExpertSection } from "@/lib/scenes";

const number = (value: number) => value.toLocaleString("en-US");
function Metrics({ items }: { items: [string, string][] }) { return <dl className="metric-row">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>; }
function Limits({ items }: { items: string[] }) { return <details className="limitations-disclosure"><summary>Methodology and limitations</summary><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></details>; }

export function ExpertShell({ data, view, onView }: { data: KonyaData; view: ExpertSection; onView: (view: ExpertSection) => void }) {
  const { contract, spatial, temporal, spectral, ml, fusion, provenance } = data;
  const section = expertSections.find((item) => item.id === view)!;
  const figures = view in data.manifest.figures ? data.manifest.figures[view as keyof typeof data.manifest.figures] : [];
  const title = view === "overview" ? "Trace the evidence." : view === "ml" ? "Experimental Spectral Anomaly ML" : section.label;
  return <><SectionHeading eyebrow={`${section.stage} / Expert View`} title={title} description={view === "overview" ? "The validated Konya evidence package. Inspect each layer, its origin and its limits." : "Saved scientific evidence · Konya, Turkey · 20250608_091605_90_4001"} />
    {view === "overview" && <>
      <section className="assessment-card"><div><p className="eyebrow gold-text">Stage 4 · Rule {fusion.matched_rule_id}</p><h2>{contract.decision_state.replaceAll("_", " ")}</h2><p>{contract.recommended_next_action}</p></div><div className="policy-note"><LockKeyhole size={18} /><strong>automation_allowed: false</strong></div></section>
      <div className="expert-overview-grid">{[
        ["spatial", "Relative hotspots present", "Scene-relative priorities for field inspection."],
        ["temporal", "Neutral / mixed context", "No strong broad moisture decline confirmation."],
        ["spectral", "Hyperspectral detail", "Fine spectral structure beyond the compact index baseline."],
        ["ml", "Experimental spectral anomaly", "Unusual vegetation spectra; cause unconfirmed."],
      ].map(([id, heading, text]) => <button className="evidence-module" key={id} onClick={() => onView(id as ExpertSection)}><p className="eyebrow">{expertSections.find((item) => item.id === id)?.stage}</p><h2>{heading}</h2><p>{text}</p><span className="module-bottom">Review evidence <ArrowRight size={16} /></span></button>)}</div>
      <p className="science-note">The analysis level {contract.analysis_level} describes evidence richness, not accuracy or calibrated confidence. Ground evidence is unavailable. The experimental ML layer does not select or modify the Stage 4 decision.</p>
    </>}
    {view === "spatial" && <>
      <Metrics items={[["Classified vegetation pixels", number(spatial.summary.classified_vegetation_pixels)], ["Vegetation screen", `NDVI ≥ ${spatial.summary.vegetation_threshold}`], ["Score interpretation", "Relative rank · not probability"]]} />
      <p className="science-note">These are image-pixel maps of the processed scene. Field boundaries are not available. Relative classes identify sampling priorities, not drought prevalence.</p>
      <div className="evidence-table-wrap"><table className="evidence-table"><caption>Class context · denominator: classified vegetation pixels</caption><thead><tr><th>Relative class</th><th>Pixels</th><th>Share of classified vegetation</th></tr></thead><tbody>{(["Low", "Moderate", "High", "Very High"] as const).map((name) => <tr key={name}><th>{name}</th><td>{number(spatial.statistics.risk_class_counts[name])}</td><td>{spatial.summary.risk_class_percentages[name].toFixed(2)}%</td></tr>)}</tbody></table></div>
      <Limits items={spatial.summary.limitations} />
    </>}
    {view === "temporal" && <>
      <Metrics items={[["Decision-time observations", String(temporal.decision_time.historical_observations_used)], ["Full-season observations", String(temporal.season.usable_temporal_observations)], ["Decision-time state", temporal.decision_time.state.replaceAll("_", " ")]]} />
      <section className="panel text-panel"><p className="eyebrow">Decision cutoff · {contract.decision_as_of}</p><h2>No strong broad moisture decline confirmation</h2><p>{temporal.decision_time.category_reason}</p><p>{temporal.decision_time.cutoff_rule}</p></section>
      <div className="evidence-table-wrap"><table className="evidence-table"><caption>Saved Stage 4 trends at the cutoff · no frontend trend calculation</caption><thead><tr><th>Index</th><th>Direction</th><th>Slope / day</th><th>Baseline percentile</th></tr></thead><tbody>{(["NDVI", "NDRE", "NDMI"] as const).map((index) => <tr key={index}><th>{index}</th><td>{temporal.decision_time.decision_time_trends[index].direction}</td><td>{temporal.decision_time.decision_time_trends[index].slope_per_day.toFixed(6)}</td><td>{temporal.decision_time.baseline.indices[index].target_empirical_percentile.toFixed(2)}</td></tr>)}</tbody></table></div>
      <p className="science-note">The baseline percentile is a rank, not a probability. The figure below includes later April–July observations for retrospective context only; they did not select the decision.</p>
      <Limits items={temporal.season.limitations} />
    </>}
    {view === "spectral" && <>
      <Metrics items={[["In-window band centers", String(spectral.number_of_bands_in_range)], ["Bands with both-group statistics", String(spectral.bands_with_statistics_in_both_groups)], ["Compatibility window", "400–1700 nm"]]} />
      <section className="panel text-panel"><h2>Fine structure, with interpretation limits.</h2><p>{spectral.information_comparison.conclusion}</p><p>{spectral.information_comparison.compact_baseline}</p><p>Risk-selected groups share the same scene and indices. Their separation is not independent validation. No Satellite 813 response simulation or accuracy benchmark is claimed.</p></section>
      <Limits items={spectral.limitations} />
    </>}
    {view === "ml" && <>
      <p className="science-note ml-caution">Identifies vegetation spectra that are unusual relative to the current scene. Unsupervised, exploratory, scene-relative and not field-calibrated. Not a probability, drought detection, disease detection or independent validation of Stage 2. The Stage 4 decision remains unchanged.</p>
      <Metrics items={[["Eligible vegetation pixels", number(ml.eligible_vegetation_pixel_count)], ["Usable spectral bands", String(ml.usable_band_count)], ["Retained PCA components", String(ml.pca.retained_component_count)]]} />
      <section className="panel text-panel"><p className="eyebrow">Descriptive comparison with Stage 2</p><h2>Spearman ρ ≈ {ml.descriptive_stage2_comparison.spearman_rank_correlation >= 0 ? "+" : ""}{ml.descriptive_stage2_comparison.spearman_rank_correlation.toFixed(6)}</h2><p>The near-zero relationship is retained. Moisture-risk ranks and spectral unusualness answer different questions; neither layer independently validates the other.</p><p>{ml.descriptive_stage2_comparison.interpretation}</p></section>
      <details className="limitations-disclosure"><summary>Model and score details</summary><p>{ml.anomaly_score_definition}</p><Metrics items={[["Fitting sample", number(ml.fitting_sample_size)], ["Median raw score", ml.anomaly_statistics.median.toFixed(6)], ["Retained sample variance", ml.pca.cumulative_explained_variance.toFixed(6)]]} /><p>Retained variance is not predictive accuracy. No binary anomaly threshold or known anomaly fraction is asserted.</p></details>
      <Limits items={ml.scientific_limitations} />
    </>}
    {view === "fusion" && <>
      <section className="assessment-card"><div><p className="eyebrow">Matched rule · {fusion.matched_rule_id}</p><h2>{fusion.decision}</h2><p>{fusion.recommended_next_step}</p></div><div className="policy-note"><LockKeyhole size={18} /><strong>automation_allowed: false</strong></div></section>
      <ol className="reasoning-trace">{fusion.reasoning_trace.map((entry) => <li key={entry.rule_id}><span className="mono">{entry.rule_id}</span><p>{entry.explanation}</p></li>)}</ol>
      <Limits items={fusion.limitations} />
    </>}
    {view === "provenance" && <>
      <section className="panel text-panel"><p className="eyebrow gold-text">Current validated demo scene</p><h2>Konya, Turkey</h2><p>Scene: {provenance.scene.scene_id}</p><p>Acquisition: {provenance.scene.acquisition_date}</p><p>Decision cutoff: {contract.decision_as_of}</p><p>AOI bbox [west, south, east, north]: {provenance.scene.bbox.map((value) => value.toFixed(6)).join(", ")}</p><p>{provenance.attribution}</p></section>
      <p className="science-note">This is a retrospective reconstruction, not evidence of an operational decision made in 2025. The source hashes support reproducibility and change detection, not authenticity. No raw satellite assets are shipped to the browser.</p>
      <div className="source-records">{provenance.sources.map((source) => <details key={source.path}><summary>{source.path}</summary><p>{number(source.bytes)} bytes</p><code>SHA-256 {source.sha256}</code></details>)}</div>
      <Limits items={[provenance.scene.valid_pixel_definition, provenance.lineage.note]} />
    </>}
    {view === "methodology" && <div className="methodology-list">{contract.limitations.map((text, index) => <section key={text}><span className="mono">{String(index + 1).padStart(2, "0")}</span><p>{text}</p></section>)}</div>}
    {figures.map((figure) => <ScientificFigure key={figure.src} figure={figure} />)}
  </>;
}
