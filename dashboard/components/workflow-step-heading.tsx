export function WorkflowStepHeading({ step, label }: { step: number; label: string }) {
  return <p className="workflow-step-heading eyebrow" data-step={step}>
    <span className="step-number">{String(step).padStart(2, "0")}</span>
    <span>{label}</span><span className="step-rule" aria-hidden="true" />
  </p>;
}
