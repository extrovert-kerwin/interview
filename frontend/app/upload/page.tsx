"use client";

import { motion } from "framer-motion";
import { ArrowRight, Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { PositionPicker } from "@/components/PositionPicker";
import { ResumeDropzone } from "@/components/ResumeDropzone";
import { Spotlight } from "@/components/Spotlight";
import { createSession, getAuthToken } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function UploadPage() {
  const router = useRouter();
  const t = useT();
  const [file, setFile] = useState<File | null>(null);
  const [position, setPosition] = useState("前端工程师");
  const [difficulty, setDifficulty] = useState("mid");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!getAuthToken()) {
      toast.info(t("upload.loginToast"));
      router.push("/login?next=/upload");
    }
  }, [router, t]);

  async function handleStart() {
    if (!file) {
      toast.error(t("upload.noFileToast"));
      return;
    }
    if (!getAuthToken()) {
      router.push("/login?next=/upload");
      return;
    }
    setLoading(true);
    try {
      const session = await createSession(file, position, difficulty);
      toast.success(t("upload.parsedToast"));
      router.push(`/interview/${session.session_id}`);
    } catch (err: any) {
      toast.error(err?.message || t("upload.errorToast"));
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-14">
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55 }}
      >
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-1.5 text-xs text-ink-muted backdrop-blur">
          <Sparkles className="h-3.5 w-3.5 text-accent-cyan" />
          {t("upload.tag")}
        </div>
        <h1 className="mt-5 text-display-sm font-semibold text-display-tight md:text-display">
          {t("upload.title.before")}
          <span className="text-brand">{t("upload.title.brand")}</span>
          {t("upload.title.after")}
        </h1>
        <p className="mt-4 text-base leading-7 text-ink-muted md:text-lg">
          {t("upload.subtitle")}
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, delay: 0.1 }}
        className="mt-10"
      >
        <ResumeDropzone file={file} onChange={setFile} />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, delay: 0.18 }}
        className="mt-10"
      >
        <PositionPicker
          position={position}
          difficulty={difficulty}
          onPosition={setPosition}
          onDifficulty={setDifficulty}
        />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, delay: 0.26 }}
        className="mt-10"
      >
        <Spotlight className="glass-strong relative flex flex-col items-stretch justify-between gap-4 overflow-hidden rounded-2xl p-5 sm:flex-row sm:items-center">
          <div className="noise-layer rounded-2xl" />
          <div className="relative flex items-center gap-3 text-sm text-ink-muted">
            <div className="gradient-ring flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-accent-violet to-accent-cyan shadow-glow-soft">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            {t("upload.savedNotice")}
          </div>
          <button
            onClick={handleStart}
            disabled={loading || !file}
            className="btn-glow tap-shrink shine-on-hover relative group inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-medium"
          >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("upload.parsing")}
            </>
          ) : (
            <>
              {t("upload.enter")}
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
            </>
          )}
          </button>
        </Spotlight>
      </motion.div>
    </div>
  );
}
