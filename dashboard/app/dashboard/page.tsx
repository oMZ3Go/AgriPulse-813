import type { Metadata } from "next";
import { Suspense } from "react";
import { DashboardShell } from "@/components/dashboard-shell";

export const metadata: Metadata = { title: "Scene workspace" };

export default function DashboardPage() {
  return <Suspense fallback={<main id="main-content" className="workspace-loading">Preparing the scene workspace…</main>}><DashboardShell /></Suspense>;
}
