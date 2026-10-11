"use client";
import { useLanguage } from "./language-provider";
import { useRef } from "react";
import { SlidersHorizontal, AlignLeft } from "lucide-react";
import type { Mode } from "@/lib/product";
export type { Mode } from "@/lib/product";
export function ModeSwitch({ mode, onChange }: { mode: Mode; onChange: (mode: Mode) => void }) {
  const { t } = useLanguage();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  return <div className="mode-switch" role="group" aria-label={t("Presentation depth")}>{(["SIMPLE", "EXPERT"] as const).map((item, index) => <button key={item} ref={(el) => { buttons.current[index] = el; }} aria-pressed={mode === item} onClick={() => onChange(item)} onKeyDown={(event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - index;
    onChange(next === 0 ? "SIMPLE" : "EXPERT"); buttons.current[next]?.focus();
  }}>{item === "SIMPLE" ? <AlignLeft size={15} /> : <SlidersHorizontal size={15} />}{t(item === "SIMPLE" ? "Simple View" : "Expert View")}</button>)}</div>;
}
