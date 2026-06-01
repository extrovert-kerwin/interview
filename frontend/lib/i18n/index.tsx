"use client";

import { Globe } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { dictionaries, Locale } from "./dict";

const LOCALE_KEY = "aurora_locale";
const DEFAULT_LOCALE: Locale = "zh";

type Vars = Record<string, string | number>;

interface I18nValue {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: (key: string, vars?: Vars) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

function interpolate(template: string, vars?: Vars) {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, name) => {
    const v = vars[name];
    return v == null ? `{${name}}` : String(v);
  });
}

function pickInitialLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const saved = window.localStorage.getItem(LOCALE_KEY);
  if (saved === "zh" || saved === "en") return saved;
  const nav = window.navigator?.language?.toLowerCase() || "";
  if (nav.startsWith("en")) return "en";
  return DEFAULT_LOCALE;
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const next = pickInitialLocale();
    setLocaleState(next);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready || typeof document === "undefined") return;
    document.documentElement.setAttribute("lang", locale === "zh" ? "zh-CN" : "en");
    document.title = dictionaries[locale]["doc.title"] ?? document.title;
  }, [locale, ready]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(LOCALE_KEY, next);
    }
  }, []);

  const t = useCallback(
    (key: string, vars?: Vars) => {
      const dict = dictionaries[locale] || dictionaries[DEFAULT_LOCALE];
      const template = dict[key] ?? dictionaries[DEFAULT_LOCALE][key] ?? key;
      return interpolate(template, vars);
    },
    [locale],
  );

  const value = useMemo<I18nValue>(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    return {
      locale: DEFAULT_LOCALE,
      setLocale: () => undefined,
      t: (key, vars) => interpolate(dictionaries[DEFAULT_LOCALE][key] ?? key, vars),
    };
  }
  return ctx;
}

export function useT() {
  return useI18n().t;
}

export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();
  const next: Locale = locale === "zh" ? "en" : "zh";
  return (
    <button
      type="button"
      onClick={() => setLocale(next)}
      className={
        className ??
        "tap-shrink inline-flex h-9 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-xs text-ink-muted transition hover:border-accent-cyan/40 hover:text-ink"
      }
      title={t("shell.lang.label")}
      aria-label={t("shell.lang.label")}
    >
      <Globe className="h-3.5 w-3.5" />
      <span className="font-medium">{locale === "zh" ? t("shell.lang.zh") : t("shell.lang.en")}</span>
      <span className="text-[10px] text-ink-dim">→ {next === "zh" ? t("shell.lang.zh") : t("shell.lang.en")}</span>
    </button>
  );
}

export type { Locale } from "./dict";
