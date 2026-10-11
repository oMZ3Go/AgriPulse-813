"use client";

import { createContext, startTransition, useCallback, useContext, useEffect, useState } from "react";
import { arabic } from "@/lib/translations";

type Language = "en" | "ar";
const LanguageContext = createContext({ language: "en" as Language, setLanguage: (_: Language) => {}, t: (text: string) => text });

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState<Language>("en");
  useEffect(() => {
    // The provider can mount before nested Suspense content hydrates. Let that
    // content hydrate in English before restoring the persisted language.
    try { if (localStorage.getItem("agripulse-language") === "ar") startTransition(() => setLanguage("ar")); } catch { /* Storage is optional. */ }
  }, []);
  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
  }, [language]);
  const choose = useCallback((value: Language) => {
    // Header controls may be interactive while a page boundary is hydrating.
    startTransition(() => setLanguage(value));
    try { localStorage.setItem("agripulse-language", value); } catch { /* Language still works in memory. */ }
  }, []);
  const t = useCallback((text: string) => language === "ar" ? arabic[text] ?? text : text, [language]);
  return <LanguageContext.Provider value={{ language, setLanguage: choose, t }}><a className="skip-link" href="#main-content">{t("Skip to content")}</a>{children}</LanguageContext.Provider>;
}

export const useLanguage = () => useContext(LanguageContext);
export function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();
  return <div className="language-switch" role="group" aria-label={t("Language")} dir="ltr">
    <button lang="en" aria-label="English" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
    <button lang="ar" aria-label="العربية" aria-pressed={language === "ar"} onClick={() => setLanguage("ar")}>AR</button>
  </div>;
}
