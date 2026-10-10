import { Header } from "@/components/header";
import { SceneExperience } from "@/components/scene-experience";
import { Suspense } from "react";

export default function HomePage() {
  return <div className="site-page"><Header /><Suspense fallback={<main id="main-content">Preparing Earth view…</main>}><SceneExperience variant="landing" /></Suspense></div>;
}
