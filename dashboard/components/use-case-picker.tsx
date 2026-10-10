"use client";
import { Globe2, MapPin, Radio, Check } from "lucide-react";
import { useCases, type UseCase } from "@/lib/product";
const icons = [Globe2, MapPin, Radio];
export function UseCasePicker({ value, onChange }: { value: UseCase; onChange: (value: UseCase) => void }) {
  return <div className="use-case-picker" role="group" aria-label="Product use case">{useCases.map((item, index) => {
    const Icon = icons[index];
    return <button key={item.id} className={`use-case-card use-case-${index}`} aria-pressed={value === item.id} onClick={() => onChange(item.id)}>
      <span className="use-case-icon"><Icon size={20} strokeWidth={1.5} /></span><span><strong>{item.label}</strong><small>{item.description}</small></span>
      {value === item.id && <Check size={14} className="use-case-check" />}
    </button>;
  })}</div>;
}
