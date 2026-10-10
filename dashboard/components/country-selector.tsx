"use client";
import { useEffect, useId, useRef, useState } from "react";
import { Search, ChevronDown } from "lucide-react";
import { countries, type Country } from "@/lib/scenes";

const normalize = (text: string) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
export function CountrySelector({ selected, onSelect }: { selected: Country | null; onSelect: (country: Country) => void }) {
  const id = useId();
  const [query, setQuery] = useState(selected?.name ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const container = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const matches = countries.filter((country) => normalize(country.name + (country.id === "792" ? " Türkiye Turkiye" : "")).includes(normalize(query)));
  useEffect(() => { setQuery(selected?.name ?? ""); setOpen(false); setActive(-1); }, [selected]);
  useEffect(() => { if (active >= 0) document.getElementById(`${id}-option-${active}`)?.scrollIntoView({ block: "nearest" }); }, [active, id]);
  function close() { setOpen(false); setQuery(selected?.name ?? ""); setActive(-1); }
  function choose(country: Country) { onSelect(country); setQuery(country.name); setOpen(false); setActive(-1); input.current?.focus(); }
  return <div ref={container} className="country-selector" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) close(); }}>
    <label htmlFor={id}>Find a country</label>
    <div className="country-input"><Search size={16} /><input ref={input} id={id} role="combobox" aria-expanded={open} aria-controls={`${id}-list`} aria-autocomplete="list" aria-activedescendant={open && active >= 0 && matches[active] ? `${id}-option-${active}` : undefined} autoComplete="off" placeholder="Search countries…" value={query}
      onClick={() => { setOpen(true); input.current?.select(); }}
      onChange={(event) => { setQuery(event.target.value); setOpen(true); setActive(-1); }}
      onKeyDown={(event) => {
        if (event.key === "Escape") { event.preventDefault(); close(); }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault(); setOpen(true);
          setActive((previous) => matches.length ? Math.max(0, Math.min(matches.length - 1, previous + (event.key === "ArrowDown" ? 1 : -1))) : -1);
        }
        if (event.key === "Enter" && open && matches.length) { event.preventDefault(); choose(matches[active >= 0 ? active : 0]); }
      }} /><button aria-label="Browse countries" aria-expanded={open} onClick={() => { setQuery(""); setActive(-1); setOpen(true); input.current?.focus(); }}><ChevronDown size={15} /></button></div>
    {open && <div className="country-dropdown"><ul id={`${id}-list`} role="listbox" aria-label="Countries">{matches.map((country, index) => <li id={`${id}-option-${index}`} key={country.id} role="option" aria-selected={selected?.id === country.id} data-active={active === index} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(country)} onMouseEnter={() => setActive(index)}>{country.name}{selected?.id === country.id && <span>Selected</span>}</li>)}</ul>{!matches.length && <p role="status">No countries match. Try another name.</p>}<p className="country-dataset-note">Local Natural Earth map · small territories may be omitted at this scale.</p></div>}
  </div>;
}
