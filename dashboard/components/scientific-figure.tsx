"use client";
import Image from "next/image";
import { useState } from "react";
import type { Manifest } from "@/lib/konya";
type Figure = Manifest["figures"]["spatial"][number];
export function ScientificFigure({ figure }: { figure: Figure }) {
  const [failed, setFailed] = useState(false);
  return <figure className="scientific-figure panel"><figcaption><h2>{figure.title}</h2><p>{figure.caption}</p></figcaption>{failed ? <p role="alert" className="figure-error">This local figure could not be loaded. Reload the page or regenerate the data package.</p> : <a href={figure.src} target="_blank" rel="noreferrer" aria-label={`Open full-size ${figure.title}`}><Image src={figure.src} alt={figure.title + ". " + figure.caption} width={figure.width} height={figure.height} unoptimized loading="lazy" onError={() => setFailed(true)} /></a>}<div className="figure-source"><span>{figure.source}</span><span>Original scientific figure · open for full size</span></div></figure>;
}
