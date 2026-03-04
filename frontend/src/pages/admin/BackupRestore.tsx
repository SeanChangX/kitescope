import { useState, useRef } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

export default function BackupRestore() {
  const { t } = useI18n();
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function downloadBackup() {
    setMessage(null);
    const r = await authFetch("/api/admin/settings/backup");
    if (!r.ok) {
      setMessage(t("admin.backupFailed"));
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const disp = r.headers.get("Content-Disposition");
    const match = disp?.match(/filename=(.+)/);
    a.download = match ? match[1].trim().replace(/^["']|["']$/g, "") : `kitescope-backup-${new Date().toISOString().slice(0, 10)}.zip`;
    a.click();
    URL.revokeObjectURL(url);
    setMessage(t("admin.backupDownloaded"));
  }

  async function restore(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setMessage(null);
    setRestoreLoading(true);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as { backup?: unknown } | Record<string, unknown>;
      const backup = typeof parsed === "object" && parsed !== null && "backup" in parsed ? parsed.backup : parsed;
      const r = await authFetch("/api/admin/settings/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backup }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        setMessage(t("admin.restoreDone"));
      } else {
        setMessage((data.detail as string) || t("admin.restoreFailed"));
      }
    } catch {
      setMessage(t("admin.restoreFailed"));
    } finally {
      setRestoreLoading(false);
    }
  }

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">{t("admin.backupRestore")}</h3>
      <p className="mb-3 text-sm text-text-secondary">{t("admin.backupRestoreDesc")}</p>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={downloadBackup}
          className="ks-btn ks-btn-secondary"
        >
          {t("admin.backupSettings")}
        </button>
        <label className="ks-btn ks-btn-primary cursor-pointer">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            className="sr-only"
            disabled={restoreLoading}
            onChange={restore}
          />
          {restoreLoading ? t("admin.restoring") : t("admin.restoreSettings")}
        </label>
      </div>
      {message && (
        <p className={`mt-2 text-sm ${message === t("admin.backupDownloaded") || message === t("admin.restoreDone") ? "text-ks-success" : "text-ks-danger"}`}>
          {message}
        </p>
      )}
    </div>
  );
}
