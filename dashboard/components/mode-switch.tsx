"use client";

import { useRef } from "react";
import { SlidersHorizontal, Sprout } from "lucide-react";

export type Mode = "farmer" | "expert";

export function ModeSwitch({ mode, onChange }: { mode: Mode; onChange: (mode: Mode) => void }) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  return <div className="mode-switch" role="tablist" aria-label="Workspace mode">{(["farmer", "expert"] as const).map((item, index) => <button key={item} ref={(el) => { buttons.current[index] = el; }} id={`mode-${item}`} role="tab" aria-selected={mode === item} aria-controls="mode-panel" tabIndex={mode === item ? 0 : -1} onClick={() => onChange(item)} onKeyDown={(event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - index;
    onChange(next === 0 ? "farmer" : "expert");
    buttons.current[next]?.focus();
  }}>{item === "farmer" ? <Sprout size={15} /> : <SlidersHorizontal size={15} />}{item === "farmer" ? "Farmer Mode" : "Expert Mode"}</button>)}</div>;
}
