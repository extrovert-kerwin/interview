"use client";

import { FileText, Home, LogIn, LogOut, Moon, Plus, Sparkles, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { BrandMark } from "@/components/BrandMark";
import { getStoredUser, InterviewRecord, listMySessions, logout } from "@/lib/api";
import { LanguageSwitcher, useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", labelKey: "shell.nav.home", icon: Home },
  { href: "/upload", labelKey: "shell.nav.start", icon: Plus },
  { href: "/records", labelKey: "shell.nav.records", icon: FileText },
] as const;

const THEME_KEY = "aurora_theme";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useT();
  const [user, setUser] = useState<ReturnType<typeof getStoredUser>>(null);
  const [records, setRecords] = useState<InterviewRecord[]>([]);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    setUser(getStoredUser());
    const saved = window.localStorage.getItem(THEME_KEY) as "dark" | "light" | null;
    const next = saved || "dark";
    setTheme(next);
    applyTheme(next);
  }, []);

  useEffect(() => {
    const refresh = async () => {
      const current = getStoredUser();
      setUser(current);
      if (!current) {
        setRecords([]);
        return;
      }
      try {
        setRecords(await listMySessions());
      } catch {
        setRecords([]);
      }
    };
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, [pathname]);

  const initials = useMemo(() => {
    const name = user?.display_name || user?.email || "GU";
    return name.slice(0, 2).toUpperCase();
  }, [user]);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    window.localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  }

  async function handleLogout() {
    await logout();
    setUser(null);
    setRecords([]);
    toast.success(t("shell.logout.toast"));
    router.push("/login");
  }

  return (
    <div className="min-h-screen">
      <header className="fixed inset-x-0 top-0 z-50 border-b border-border bg-background/70 backdrop-blur-xl">
        <div className="flex h-16 items-center justify-between gap-4 px-4 lg:pl-5 lg:pr-6">
          <BrandMark />
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <button
              onClick={toggleTheme}
              className="tap-shrink inline-flex h-9 w-9 items-center justify-center rounded-full border border-border bg-surface text-ink-muted transition hover:border-accent-cyan/40 hover:text-ink"
              title={theme === "dark" ? t("shell.theme.toLight") : t("shell.theme.toDark")}
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            {user ? (
              <>
                <div className="hidden text-right text-xs sm:block">
                  <div className="text-ink">{user.display_name}</div>
                  <div className="text-ink-dim">{user.email}</div>
                </div>
                <button
                  onClick={handleLogout}
                  className="tap-shrink inline-flex h-9 w-9 items-center justify-center rounded-full border border-border bg-surface text-ink-muted transition hover:border-accent-rose/40 hover:text-ink"
                  title={t("shell.logout.tip")}
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </>
            ) : (
              <Link
                href="/login"
                className="btn-soft tap-shrink inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm"
              >
                <LogIn className="h-4 w-4" />
                {t("shell.login")}
              </Link>
            )}
          </div>
        </div>
      </header>

      <aside className="fixed bottom-0 left-0 top-16 z-40 hidden w-72 border-r border-border bg-background/50 px-4 py-5 backdrop-blur-xl lg:block">
        <section className="glass-strong relative overflow-hidden rounded-2xl p-4">
          <div className="noise-layer rounded-2xl" />
          <div className="relative flex items-center gap-3">
            <div className="gradient-ring animate-float flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-violet via-accent-cyan to-accent-emerald font-semibold text-white shadow-glow-soft">
              {initials}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-ink">{user?.display_name || t("shell.profile.guestName")}</div>
              <div className="truncate text-xs text-ink-dim">{user?.email || t("shell.profile.guestSub")}</div>
            </div>
          </div>
        </section>


        <nav className="mt-5 space-y-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "tap-shrink group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition",
                  active
                    ? "bg-gradient-to-r from-accent-violet/20 via-accent-cyan/15 to-transparent text-ink shadow-glow-soft"
                    : "text-ink-muted hover:bg-surface hover:text-ink",
                )}
              >
                <item.icon
                  className={cn(
                    "h-4 w-4 transition",
                    active ? "text-accent-cyan" : "group-hover:text-accent-violet",
                  )}
                />
                {t(item.labelKey)}
                {active && (
                  <span className="ml-auto inline-block h-1.5 w-1.5 rounded-full bg-accent-cyan shadow-glow-cyan" />
                )}
              </Link>
            );
          })}
        </nav>

        <section className="mt-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-ink-dim">
              <Sparkles className="h-3 w-3 text-accent-cyan" />
              {t("shell.recent.title")}
            </h2>
            <Link href="/records" className="text-xs text-accent-cyan transition hover:text-ink">
              {t("shell.recent.all")}
            </Link>
          </div>
          <div className="space-y-2">
            {!user ? (
              <Link
                href="/login"
                className="block rounded-xl border border-border bg-surface p-3 text-sm text-ink-muted transition hover:border-accent-cyan/40 hover:text-ink"
              >
                {t("shell.recent.loginCta")}
              </Link>
            ) : records.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border bg-surface/60 p-3 text-sm text-ink-muted">
                {t("shell.recent.empty")}
              </div>
            ) : (
              records.slice(0, 6).map((record) => (
                <Link
                  key={record.session_id}
                  href={record.report_ready ? `/report/${record.session_id}` : `/interview/${record.session_id}`}
                  className="lift-hover block rounded-xl border border-border bg-surface p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate text-sm text-ink">{record.position || t("shell.recent.position.generic")}</div>
                    {record.score != null && (
                      <div className="font-mono text-sm text-accent-cyan">{record.score}</div>
                    )}
                  </div>
                  <div className="mt-1 truncate text-xs text-ink-dim">
                    {record.report_ready ? t("shell.recent.reportReady") : t("shell.recent.keepGoing")} ·{" "}
                    {new Date(record.updated_at).toLocaleDateString()}
                  </div>
                </Link>
              ))
            )}
          </div>
        </section>
      </aside>

      <div className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t border-border bg-background/85 backdrop-blur-xl lg:hidden">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "tap-shrink flex flex-col items-center gap-1 px-2 py-2.5 text-xs transition",
                active ? "text-accent-cyan" : "text-ink-dim",
              )}
            >
              <item.icon className={cn("h-4 w-4", active && "drop-shadow-[0_0_8px_rgba(34,211,238,0.6)]")} />
              {t(item.labelKey)}
            </Link>
          );
        })}
      </div>

      <main className="relative z-10 min-h-screen pt-16 lg:pl-72">{children}</main>
    </div>
  );
}

function applyTheme(theme: "dark" | "light") {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.classList.toggle("light", theme === "light");
}
