import type { Metadata } from "next";
import { Header } from "@/components/header";
import { SceneExperience } from "@/components/scene-experience";

export const metadata: Metadata = { title: "Choose a scene" };

export default function ScenePage() {
  return <div className="site-page"><Header scene /><SceneExperience variant="selection" /></div>;
}
