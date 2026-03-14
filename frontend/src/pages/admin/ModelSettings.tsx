import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

type ModelMode = "onnx" | "tflite";

function getModelMode(name: string | null | undefined): ModelMode | null {
  if (!name) return null;
  const lower = name.toLowerCase();
  if (lower.endsWith(".onnx")) return "onnx";
  if (lower.endsWith(".tflite")) return "tflite";
  return null;
}

function basename(path: string | null | undefined): string | null {
  if (!path) return null;
  return path.split("/").pop() ?? null;
}

export default function ModelSettings() {
  const { t } = useI18n();
  const [models, setModels] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [draftSelected, setDraftSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<ModelMode>("onnx");
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.5);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [switchTarget, setSwitchTarget] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function fetchModels() {
    setError(null);
    try {
      const r = await authFetch("/api/admin/settings/models");
      const d = r.ok ? await r.json() : null;
      if (d) {
        const nextModels = d.models ?? [];
        const nextSelected = d.selected ?? null;
        setModels(nextModels);
        setSelected(nextSelected);
        setDraftSelected((prev) => {
          if (prev && nextModels.includes(prev)) return prev;
          return nextSelected && nextModels.includes(nextSelected) ? nextSelected : null;
        });
        setMode((prev) => {
          const selectedMode = getModelMode(nextSelected);
          if (selectedMode) return selectedMode;
          const hasPrev = nextModels.some((name: string) => getModelMode(name) === prev);
          if (hasPrev) return prev;
          return nextModels.some((name: string) => getModelMode(name) === "onnx") ? "onnx" : "tflite";
        });
        const c = Number(d.confidence_threshold);
        setConfidenceThreshold(Number.isFinite(c) ? Math.max(0, Math.min(1, c)) : 0.5);
      }
    } catch {
      setError(t("admin.modelLoadFailed"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchModels();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const visibleModels = models.filter((name) => getModelMode(name) === mode);
    if (visibleModels.length === 0) {
      setDraftSelected((prev) => (prev && getModelMode(prev) === mode ? prev : null));
      return;
    }
    setDraftSelected((prev) => {
      if (prev && visibleModels.includes(prev)) return prev;
      if (selected && visibleModels.includes(selected)) return selected;
      return visibleModels[0];
    });
  }, [mode, models, selected]);

  useEffect(() => {
    if (!switching || !switchTarget) return;
    let cancelled = false;
    let timerId: number | undefined;
    const startedAt = Date.now();

    async function pollStatus() {
      try {
        const r = await authFetch("/api/admin/system/status");
        const d = r.ok ? await r.json() : null;
        const configuredModel = basename(d?.vision?.model_path);
        if (!cancelled && d?.vision_reachable && configuredModel === switchTarget) {
          setSwitching(false);
          setSwitchTarget(null);
          setMessage(t("admin.modelSwitchComplete"));
          setError(null);
          fetchModels();
          return;
        }
      } catch {
        // Keep polling while vision is restarting.
      }
      if (cancelled) return;
      if (Date.now() - startedAt >= 30_000) {
        setSwitching(false);
        setSwitchTarget(null);
        setError(t("admin.modelSwitchTimeout"));
        return;
      }
      timerId = window.setTimeout(pollStatus, 1500);
    }

    timerId = window.setTimeout(pollStatus, 1200);
    return () => {
      cancelled = true;
      if (timerId) window.clearTimeout(timerId);
    };
  }, [switchTarget, switching, t]);

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
        await fetchModels();
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
        if (selected === filename) {
          setSelected(null);
          setDraftSelected(null);
        }
        await fetchModels();
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
        body: JSON.stringify({ confidence_threshold: confidenceThreshold }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        setMessage(t("admin.saved"));
      } else {
        setError((data.detail as string) || t("admin.saveFailed"));
      }
    } catch {
      setError(t("admin.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function switchModel() {
    if (!draftSelected || switching) return;
    setMessage(null);
    setError(null);
    setSaving(true);
    try {
      const r = await authFetch("/api/admin/settings/models", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected: draftSelected }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        if (data.switching) {
          setSwitching(true);
          setSwitchTarget(draftSelected);
          setMessage(t("admin.modelSwitching"));
        } else {
          setMessage(t("admin.modelSavedAndApplied"));
          await fetchModels();
        }
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

  const onnxModels = models.filter((name) => getModelMode(name) === "onnx");
  const tfliteModels = models.filter((name) => getModelMode(name) === "tflite");
  const visibleModels = mode === "onnx" ? onnxModels : tfliteModels;
  const canSwitch = !!draftSelected && draftSelected !== selected && !saving && !switching;

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
          <p className="text-sm text-text-muted mb-2">{t("admin.modelMode")}</p>
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              type="button"
              className={`ks-btn ${mode === "onnx" ? "ks-btn-primary" : "ks-btn-secondary"}`}
              onClick={() => setMode("onnx")}
            >
              {t("admin.modelModeOnnx")}
            </button>
            <button
              type="button"
              className={`ks-btn ${mode === "tflite" ? "ks-btn-primary" : "ks-btn-secondary"}`}
              onClick={() => setMode("tflite")}
            >
              {t("admin.modelModeTflite")}
            </button>
          </div>
          <p className="mb-2 text-sm text-text-muted">
            {t("admin.modelCurrentApplied")}: {selected ?? "—"}
          </p>
          {switching && switchTarget && (
            <p className="mb-2 text-sm text-text-secondary">
              {t("admin.modelSwitchingStatus")} {switchTarget}
            </p>
          )}
          <p className="text-sm text-text-muted mb-2">{t("admin.modelSelect")}</p>
          {models.length === 0 ? (
            <p className="text-sm text-text-muted">{t("admin.noModels")}</p>
          ) : visibleModels.length === 0 ? (
            <p className="text-sm text-text-muted">{t("admin.noModelsInMode")}</p>
          ) : (
            <ul className="space-y-2">
              {visibleModels.map((name) => {
                const isInUse = selected === name;
                return (
                <li
                  key={name}
                  className={`flex items-center gap-3 rounded-xl border-2 px-4 py-3 transition-colors ${
                    draftSelected === name
                      ? "border-primary bg-primary/10"
                      : "border-border-dark bg-bg-tertiary/50 hover:border-border"
                  }`}
                >
                  <input
                    type="radio"
                    name="model"
                    id={`model-${name}`}
                    value={name}
                    checked={draftSelected === name}
                    onChange={() => setDraftSelected(name)}
                    className="ks-radio shrink-0"
                  />
                  <label
                    htmlFor={`model-${name}`}
                    className="min-w-0 flex-1 cursor-pointer truncate text-sm font-medium text-text-primary"
                  >
                    {name}
                    {isInUse ? <span className="ml-2 text-xs text-text-muted">({t("admin.modelInUse")})</span> : null}
                  </label>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      onDelete(name);
                    }}
                    disabled={isInUse}
                    title={isInUse ? t("admin.modelDeleteInUse") : undefined}
                    className="shrink-0 text-sm text-red-500 transition-colors hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-red-500"
                  >
                    {t("admin.delete")}
                  </button>
                </li>
                );
              })}
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
        <div className="flex flex-wrap gap-2">
          <button type="button" className="ks-btn ks-btn-primary" disabled={!canSwitch} onClick={switchModel}>
            {switching ? t("admin.modelSwitchingButton") : t("admin.modelSwitch")}
          </button>
          <button type="submit" className="ks-btn ks-btn-secondary" disabled={saving || switching}>
            {saving ? t("admin.saving") : t("admin.save")}
          </button>
        </div>
        <p className="text-xs text-text-muted">{t("admin.modelSwitchHint")}</p>
      </form>
    </div>
  );
}
