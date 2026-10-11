"use client";
import { LanguageSwitcher, useLanguage } from "./language-provider";
import Link from "next/link";
import { MapPinned } from "lucide-react";
import { Brand } from "@/components/brand";

export function Header({ scene = false }: { scene?: boolean }) {
  const { t } = useLanguage();
  return (
    <header className="site-header">
      <Brand />
      <span className="header-context">{t(scene ? "Area selection" : "Beyond The Limit")}</span>
      <nav aria-label={t("Main navigation")} className="header-nav">
        <Link className={scene ? "nav-link active" : "nav-link"} href="#country-selection" aria-current={scene ? "page" : undefined}><MapPinned size={15} />{t("Explore Earth")}</Link>
      <LanguageSwitcher /></nav>
    </header>
  );
}
