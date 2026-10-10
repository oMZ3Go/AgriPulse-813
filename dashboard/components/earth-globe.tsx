"use client";

import dynamic from "next/dynamic";
import { Component, useEffect, useState } from "react";
import { Globe2 } from "lucide-react";
import type { SceneId } from "@/lib/scenes";

export type EarthGlobeProps = { selected: SceneId | null; onSelect: (scene: SceneId) => void };

const GlobeCanvas = dynamic(() => import("./globe-canvas"), {
  ssr: false,
  loading: () => <GlobePlaceholder />,
});

function GlobePlaceholder({ unavailable = false }: { unavailable?: boolean }) {
  return <div className="globe-placeholder" role="status"><div className="globe-outline"><Globe2 size={64} strokeWidth={0.6} /></div><p>{unavailable ? "Earth view unavailable on this device" : "Preparing the Earth view"}</p><span>{unavailable ? "Use the region controls to continue." : "Regional context · Konya and Syria"}</span></div>;
}

class GlobeBoundary extends Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <GlobePlaceholder unavailable /> : this.props.children; }
}

export function EarthGlobe(props: EarthGlobeProps) {
  const [supported, setSupported] = useState<boolean | null>(null);
  useEffect(() => {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2");
    setSupported(Boolean(context));
    context?.getExtension("WEBGL_lose_context")?.loseContext();
  }, []);
  return <div className="earth-view"><GlobeBoundary>{supported === null ? <GlobePlaceholder /> : supported ? <GlobeCanvas {...props} /> : <GlobePlaceholder unavailable />}</GlobeBoundary></div>;
}
