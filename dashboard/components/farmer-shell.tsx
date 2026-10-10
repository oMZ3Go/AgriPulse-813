import { ArrowRight, ClipboardCheck, LockKeyhole, Satellite, ScanLine } from "lucide-react";
import { EmptyEvidence, PlaceholderBadge, SectionHeading } from "@/components/ui";

export function FarmerShell({ view, onView }: { view: string; onView: (view: string) => void }) {
  return <>
    <SectionHeading eyebrow="A view for the field" title={view === "map" ? "Know where to look." : view === "decision" ? "A considered next step." : "Your field, in perspective."} description="A clear path from satellite observations to a decision you can review." />
    {view === "overview" && <><div className="field-context"><div><span className="context-label">Current field / scene</span><h2>Konya, Turkey</h2></div><div><span className="context-label">Assessment status</span><span className="neutral-status">Not assessed in this preview</span></div><PlaceholderBadge /></div>
      <div className="farmer-status-grid"><StatusCard icon={<Satellite size={19} />} label="Satellite concern" value="Awaiting evidence" text="No concern level has been assigned." /><StatusCard icon={<ScanLine size={19} />} label="Ground verification" value="Not connected" text="No field observations are available in this preview." /><StatusCard icon={<ClipboardCheck size={19} />} label="Need for inspection" value="Not yet assessed" text="Inspection guidance will follow the evidence review." /></div></>}
    <div className={`farmer-main-grid ${view !== "overview" ? "single-view" : ""}`}>
      {view !== "decision" && <section className="panel map-panel"><div className="panel-header"><div><p className="eyebrow">Spatial context</p><h2>Map & hotspots</h2></div><PlaceholderBadge /></div><EmptyEvidence title="A place for the field evidence" description="The scene map and relative hotspot areas will appear here when connected. No field boundaries or risk areas are shown." spatial /><div className="panel-footer"><span>Scene and field context</span>{view === "overview" && <button className="text-button" onClick={() => onView("map")}>Expand view <ArrowRight size={14} /></button>}</div></section>}
      {view !== "map" && <section className="panel next-step-panel"><div className="panel-header"><div><p className="eyebrow">Recommended next step</p><h2>Let the evidence lead.</h2></div></div><div className="next-step-content"><PlaceholderBadge /><h3>No recommendation yet</h3><p>Satellite evidence and ground verification need to be reviewed before a field-specific next step can be shown.</p><div className="quiet-rule" /><div className="policy-note"><LockKeyhole size={18} /><div><strong>Automatic action is unavailable</strong><p>This demo supports human review. It cannot control irrigation.</p></div></div></div></section>}
    </div>
    {view !== "map" && <section className="decision-summary"><div><p className="eyebrow">Decision summary</p><h2>Nothing to conclude without the evidence.</h2><p>Concern, inspection need, and the recommended response remain unassessed in this interface preview.</p></div><PlaceholderBadge /></section>}
  </>;
}

function StatusCard({ icon, label, value, text }: { icon: React.ReactNode; label: string; value: string; text: string }) {
  return <section className="status-card"><div className="status-card-label">{icon}<h2>{label}</h2></div><h3>{value}</h3><p>{text}</p><PlaceholderBadge /></section>;
}
