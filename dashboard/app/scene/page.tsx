import type { Metadata } from "next";
import { Header } from "@/components/header";
import { SceneExperience } from "@/components/scene-experience";
import { Suspense } from "react";

export const metadata: Metadata = { title: "Choose a scene" };

export default function ScenePage() {
  return <div className="site-page"><Header scene /><Suspense fallback={<main id="main-content">Preparing geographic selection…</main>}><SceneExperience variant="selection" /></Suspense></div>;
}
