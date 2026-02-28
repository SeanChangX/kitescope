import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

export default function NotifyFormatSettings() {
  const { t } = useI18n();
  const [format, setFormat] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    authFetch("/api/admin/settings/notify-format")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d && typeof d.format === "string") setFormat(d.format);
      })
      .finally(() => setLoading(false));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    setSaving(true);
    const r = await authFetch("/api/admin/settings/notify-format", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format }),
    });
    setSaving(false);
    if (r.ok) setMessage(t("admin.saved"));
    else setMessage(t("admin.saveFailed"));
  }

  if (loading) return <p className="text-text-muted">{t("common.loading")}</p>;

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">{t("admin.notifyFormat")}</h3>
      <p className="mb-3 text-sm text-text-secondary">{t("admin.notifyFormatDesc")}</p>
      <form onSubmit={submit} className="space-y-3 max-w-xl">
        <textarea
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          className="ks-input min-h-[120px] font-mono text-sm"
          rows={5}
          spellCheck={false}
        />
        <p className="text-xs text-text-muted">{t("admin.notifyFormatPlaceholders")}</p>
        {message && <p className="text-sm text-text-secondary">{message}</p>}
        <button type="submit" className="ks-btn ks-btn-primary" disabled={saving}>
          {saving ? t("admin.saving") : t("admin.save")}
        </button>
      </form>
    </div>
  );
}
