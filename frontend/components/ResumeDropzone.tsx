"use client";

import { FileText, UploadCloud } from "lucide-react";
import { useCallback } from "react";
import { useDropzone } from "react-dropzone";

import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface Props {
  file: File | null;
  onChange: (file: File | null) => void;
}

export function ResumeDropzone({ file, onChange }: Props) {
  const t = useT();
  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted[0]) onChange(accepted[0]);
    },
    [onChange],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        [".docx"],
      "text/plain": [".txt", ".md"],
    },
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "glass group relative flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-8 py-14 transition",
        isDragActive
          ? "border-accent-violet/60 bg-accent-violet/5"
          : "border-border hover:border-ink/30",
      )}
    >
      <input {...getInputProps()} />
      {file ? (
        <>
          <div className="rounded-xl border border-border bg-surface p-3">
            <FileText className="h-7 w-7 text-accent-cyan" />
          </div>
          <p className="mt-4 text-base font-medium">{file.name}</p>
          <p className="mt-1 text-xs text-ink-muted">
            {(file.size / 1024).toFixed(1)} KB · {t("dropzone.replace")}
          </p>
        </>
      ) : (
        <>
          <div className="rounded-xl border border-border bg-surface p-3 transition group-hover:scale-105">
            <UploadCloud className="h-7 w-7 text-accent-violet" />
          </div>
          <p className="mt-4 text-base font-medium">
            {isDragActive ? t("dropzone.dropToUpload") : t("dropzone.dragOrPick")}
          </p>
          <p className="mt-1 text-xs text-ink-muted">
            {t("dropzone.hint")}
          </p>
        </>
      )}
    </div>
  );
}
