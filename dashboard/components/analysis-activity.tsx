"use client";
import { Check, Circle, ArrowRight, AlertCircle } from "lucide-react";
import { activitySteps } from "@/lib/konya";
export function AnalysisActivity({ completed, error }: { completed: number; error: string | null }) {
  const ready = completed === activitySteps.length && !error;
  return <details className="analysis-activity" open={ready ? undefined : true} data-complete={ready}>
    <summary><span className="eyebrow">Analysis activity</span><span role="status">{error ? "Package could not be loaded" : ready ? "Local evidence ready" : activitySteps[completed]}</span><span className="activity-count">{completed} / {activitySteps.length}</span></summary>
    <ol>{activitySteps.map((step, index) => <li key={step} data-state={index < completed ? "complete" : index === completed ? error ? "error" : "current" : "pending"}>{index < completed ? <Check size={14} /> : index === completed ? error ? <AlertCircle size={14} /> : <ArrowRight size={14} /> : <Circle size={12} />}<span>{step}</span><small>{index < completed ? "Complete" : index === completed ? error ? "Failed" : "In progress" : "Pending"}</small></li>)}</ol>
    <p>Reading saved local artifacts. No satellite download or new scientific processing. Figures load when opened.</p>
  </details>;
}
