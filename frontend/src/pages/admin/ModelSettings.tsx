import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

export default function ModelSettings() {
  const { t } = useI18n();
  const [models, setModels] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.5);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function fetchModels() {
    setError(null);
    authFetch("/api/admin/settings/models")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setModels(d.models ?? []);
          setSelected(d.selected ?? null);
          const c = Number(d.confidence_threshold);
          setConfidenceThreshold(Number.isFinite(c) ? Math.max(0, Math.min(1, c)) : 0.5);
        }
      })
      .catch(() => setError(t("admin.modelLoadFailed")))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    fetchModels();
  }, []);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".onnx") && !lower.endsWith(".tflite")) {
      setError(t("admin.modelUploadOnnxOnly"));
      return;
    }
    setUploading(true);
    setError(null);
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const r = await authFetch("/api/admin/settings/models/upload", {
        method: "POST",
        body: form,
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        setMessage(t("admin.modelUploaded"));
        fetchModels();
      } else {
        setError((data.detail as string) || t("admin.modelUploadFailed"));
      }
    } catch {
      setError(t("admin.modelUploadFailed"));
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function onDelete(filename: string) {
    if (!confirm(t("admin.modelDeleteConfirm"))) return;
    setError(null);
    try {
      const r = await authFetch(`/api/admin/settings/models/${encodeURIComponent(filename)}`, {
        method: "DELETE",
      });
      if (r.ok) {
        if (selected === filename) setSelected(null);
        fetchModels();
      } else {
        const data = await r.json().catch(() => ({}));
        setError((data.detail as string) || t("admin.modelDeleteFailed"));
      }
    } catch {
      setError(t("admin.modelDeleteFailed"));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    setError(null);
    setSaving(true);
    try {
      const r = await authFetch("/api/admin/settings/models", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selected: selected || "",
          confidence_threshold: confidenceThreshold,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        setMessage(data.message === "Saved and applied" ? t("admin.modelSavedAndApplied") : t("admin.saved"));
      } else {
        setError((data.detail as string) || t("admin.saveFailed"));
      }
    } catch {
      setError(t("admin.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="text-text-muted">{t("common.loading")}</p>;

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">{t("admin.modelSettings")}</h3>
      <p className="mb-3 text-sm text-text-secondary">{t("admin.modelSettingsDesc")}</p>
      <form onSubmit={submit} className="space-y-3 max-w-xl">
        <div className="flex flex-wrap items-center gap-2">
          <label className="ks-btn ks-btn-primary cursor-pointer disabled:opacity-50">
            {uploading ? t("admin.uploading") : t("admin.modelUpload")}
            <input
              type="file"
              accept=".onnx,.tflite"
              className="sr-only"
              disabled={uploading}
              onChange={onUpload}
            />
          </label>
        </div>
        <div>
          <p className="text-sm text-text-muted mb-2">{t("admin.modelSelect")}</p>
          {models.length === 0 ? (
            <p className="text-sm text-text-muted">{t("admin.noModels")}</p>
          ) : (
            <ul className="space-y-2">
              {models.map((name) => (
                <li
                  key={name}
                  className={`flex items-center gap-3 rounded-xl border-2 px-4 py-3 transition-colors ${
                    selected === name
                      ? "border-primary bg-primary/10"
                      : "border-border-dark bg-bg-tertiary/50 hover:border-border"
                  }`}
                >
                  <input
                    type="radio"
                    name="model"
                    id={`model-${name}`}
                    value={name}
                    checked={selected === name}
                    onChange={() => setSelected(name)}
                    className="ks-radio shrink-0"
                  />
                  <label
                    htmlFor={`model-${name}`}
                    className="min-w-0 flex-1 cursor-pointer truncate text-sm font-medium text-text-primary"
                  >
                    {name}
                  </label>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      onDelete(name);
                    }}
                    className="shrink-0 text-sm text-red-500 hover:text-red-400 transition-colors"
                  >
                    {t("admin.delete")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">{t("admin.confidenceThreshold")}</label>
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={confidenceThreshold}
            onChange={(e) => setConfidenceThreshold(Number(e.target.value) || 0.5)}
            className="ks-input w-24"
          />
          <p className="text-xs text-text-muted mt-1">{t("admin.confidenceThresholdHint")}</p>
        </div>
        {message && <p className="text-sm text-text-secondary">{message}</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}
        <button type="submit" className="ks-btn ks-btn-primary" disabled={saving}>
          {saving ? t("admin.saving") : t("admin.save")}
        </button>
      </form>
    </div>
  );
}
