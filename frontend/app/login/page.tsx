"use client";

import { motion } from "framer-motion";
import { Loader2, LogIn, Sparkles } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { toast } from "sonner";

import { Spotlight } from "@/components/Spotlight";
import { login, register } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function LoginPage() {
  const t = useT();
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center text-ink-muted">
          {t("login.loading")}
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}

function LoginContent() {
  const router = useRouter();
  const params = useSearchParams();
  const t = useT();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
        toast.success(t("login.welcomeToast"));
      } else {
        await register(email, password, displayName);
        toast.success(t("login.registeredToast"));
      }
      router.push(params.get("next") || "/records");
    } catch (err: any) {
      toast.error(err?.message || t("login.errorToast"));
    } finally {
      setLoading(false);
    }
  }

  const isLogin = mode === "login";

  return (
    <div className="relative mx-auto flex min-h-screen max-w-md flex-col px-6 py-12">
      <div className="mesh-orb pointer-events-none absolute -top-20 left-1/2 -z-10 h-72 w-72 -translate-x-1/2 opacity-60" />

      <motion.form
        onSubmit={submit}
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: "easeOut" }}
      >
        <Spotlight className="glass-strong shimmer-border tilt-hover relative mt-8 overflow-hidden rounded-3xl p-7">
        <div className="noise-layer rounded-3xl" />
        <div className="relative mb-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-[11px] text-ink-muted">
            <Sparkles className="h-3 w-3 text-accent-cyan" />
            {t("login.tag")}
          </div>

          <div className="mt-4 inline-flex rounded-full border border-border bg-surface p-1 text-sm">
            <button
              type="button"
              onClick={() => setMode("login")}
              className={`tap-shrink rounded-full px-5 py-1.5 transition ${
                isLogin
                  ? "bg-gradient-to-r from-accent-violet to-accent-cyan text-white shadow-glow-soft"
                  : "text-ink-muted"
              }`}
            >
              {t("login.login")}
            </button>
            <button
              type="button"
              onClick={() => setMode("register")}
              className={`tap-shrink rounded-full px-5 py-1.5 transition ${
                !isLogin
                  ? "bg-gradient-to-r from-accent-violet to-accent-cyan text-white shadow-glow-soft"
                  : "text-ink-muted"
              }`}
            >
              {t("login.register")}
            </button>
          </div>

          <h1 className="mt-5 text-3xl font-semibold text-display-tight md:text-4xl">
            {isLogin ? (
              <>
                {t("login.welcome.before")}
                <span className="text-brand">{t("login.welcome.brand")}</span>
              </>
            ) : (
              <>
                {t("login.start.before")}
                <span className="text-brand">{t("login.start.brand")}</span>
              </>
            )}
          </h1>
          <p className="mt-3 text-sm leading-7 text-ink-muted">
            {isLogin ? t("login.subtitle.login") : t("login.subtitle.register")}
          </p>
        </div>

        <div className="relative space-y-4">
          <label className="block text-sm text-ink-muted">
            {t("login.email")}
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              required
              placeholder="you@example.com"
              className="input-field mt-2 w-full rounded-xl px-4 py-3"
            />
          </label>
          <label className="block text-sm text-ink-muted">
            {t("login.password")}
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              required
              minLength={6}
              placeholder={t("login.passwordHint")}
              className="input-field mt-2 w-full rounded-xl px-4 py-3"
            />
          </label>
          {!isLogin && (
            <label className="block text-sm text-ink-muted">
              {t("login.displayName")}
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={t("login.displayNameHint")}
                className="input-field mt-2 w-full rounded-xl px-4 py-3"
              />
            </label>
          )}
        </div>

        <button
          disabled={loading}
          className="btn-glow glow-halo tap-shrink shine-on-hover relative mt-7 inline-flex w-full items-center justify-center gap-2 rounded-full px-5 py-3.5 text-sm font-medium"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
          {isLogin ? t("login.submit.login") : t("login.submit.register")}
        </button>

        <p className="relative mt-5 text-center text-xs text-ink-dim">
          {isLogin ? t("login.noAccount") : t("login.hasAccount")}
          <button
            type="button"
            onClick={() => setMode(isLogin ? "register" : "login")}
            className="ml-1 text-accent-cyan transition hover:text-ink"
          >
            {isLogin ? t("login.goRegister") : t("login.goLogin")}
          </button>
        </p>
        </Spotlight>
      </motion.form>
    </div>
  );
}
