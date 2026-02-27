import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

const API = "/api";

type Source = {
  id: number;
  name: string;
  type: string;
  location: string;
  enabled: boolean;
  direct_embed?: boolean;
  url: string;
};

export default function ManageSources() {
  const { t } = useI18n();
  const [list, setList] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editLocation, setEditLocation] = useState("");
  const [editEnabled, setEditEnabled] = useState(true);
  const [editDirectEmbed, setEditDirectEmbed] = useState(false);
  const [editUrl, setEditUrl] = useState("");

  function load() {
    setLoading(true);
    authFetch(`${API}/admin/sources`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setList)
      .catch(() => setList([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  function startEdit(s: Source) {
    setEditingId(s.id);
    setEditName(s.name || "");
    setEditLocation(s.location || "");
    setEditEnabled(s.enabled);
    setEditDirectEmbed(s.direct_embed ?? false);
    setEditUrl(s.url || "");
  }

  function cancelEdit() {
    setEditingId(null);
  }

  async function saveEdit() {
    if (editingId == null) return;
    const r = await authFetch(`${API}/admin/sources/${editingId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: editName,
        location: editLocation,
        enabled: editEnabled,
        direct_embed: editDirectEmbed,
        url: editUrl || undefined,
      }),
    });
    if (r.ok) {
      setEditingId(null);
      load();
    }
  }

  async function remove(id: number) {
    if (!confirm(t("admin.deleteConfirm"))) return;
    const r = await authFetch(`${API}/admin/sources/${id}`, { method: "DELETE" });
    if (r.ok) load();
  }

  if (loading) return <p className="text-text-muted">{t("common.loading")}</p>;

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">{t("admin.liveStreams")}</h3>
      <p className="text-sm text-text-muted mb-4">
        {t("admin.editStreamsDesc")}
      </p>
      {list.length === 0 ? (
        <p className="text-text-muted">{t("admin.noStreams")}</p>
      ) : (
        <div className="space-y-3">
          {list.map((s) => (
            <div
              key={s.id}
              className="flex flex-col gap-3 rounded border border-border p-3"
            >
              {editingId === s.id ? (
                <>
                  <div className="min-w-0 flex flex-col gap-3">
                    <div className="flex flex-wrap gap-3">
                      <input
                        type="text"
                        placeholder={t("admin.name")}
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className="ks-input max-w-xs"
                      />
                      <input
                        type="text"
                        placeholder={t("admin.location")}
                        value={editLocation}
                        onChange={(e) => setEditLocation(e.target.value)}
                        className="ks-input max-w-xs"
                      />
                    </div>
                    <div className="flex flex-col gap-2">
                      <label className="text-sm text-text-secondary">
                        {t("admin.streamUrl")}
                        <input
                          type="url"
                          value={editUrl}
                          onChange={(e) => setEditUrl(e.target.value)}
                          placeholder="https://..."
                          className="ks-input mt-1 w-full max-w-2xl block"
                        />
                      </label>
                      <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
                        <input
                          type="checkbox"
                          checked={editEnabled}
                          onChange={(e) => setEditEnabled(e.target.checked)}
                          className="ks-checkbox"
                        />
                        {t("admin.enabled")}
                      </label>
                      <label className="block cursor-pointer">
                        <span className="flex items-center gap-2 text-sm text-text-secondary">
                          <input
                            type="checkbox"
                            checked={editDirectEmbed}
                            onChange={(e) => setEditDirectEmbed(e.target.checked)}
                            className="ks-checkbox"
                          />
                          {t("admin.directEmbed")}
                        </span>
                        <span className="ml-7 block text-xs text-text-muted">{t("admin.directEmbedHint")}</span>
                      </label>
                    </div>
                  </div>
                  <div className="flex w-full gap-2">
                    <button type="button" onClick={saveEdit} className="ks-btn ks-btn-primary flex-1 min-w-0 py-1.5">
                      {t("admin.save")}
                    </button>
                    <button type="button" onClick={cancelEdit} className="ks-btn ks-btn-secondary flex-1 min-w-0 py-1.5">
                      {t("admin.cancel")}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="min-w-0">
                    <span className="font-medium text-text-primary">{s.name || `Source ${s.id}`}</span>
                    <span className="ml-2 text-text-muted text-sm">{s.type}</span>
                    {s.location && (
                      <div className="text-sm text-text-muted truncate" title={s.location}>
                        {s.location}
                      </div>
                    )}
                    <div className="text-xs text-text-muted truncate" title={s.url}>
                      {s.url}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <span
                        className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${
                          s.enabled ? "bg-ks-success/20 text-ks-success" : "bg-bg-tertiary text-text-muted"
                        }`}
                      >
                        {s.enabled ? t("admin.enabled") : t("admin.disabled")}
                      </span>
                      {s.direct_embed && (
                        <span className="inline-flex rounded bg-bg-tertiary px-1.5 py-0.5 text-xs text-text-muted">
                          {t("admin.directEmbed")}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex w-full gap-2">
                    <button type="button" onClick={() => startEdit(s)} className="ks-btn ks-btn-secondary flex-1 min-w-0 py-1.5 text-sm">
                      {t("admin.edit")}
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(s.id)}
                      className="ks-btn flex-1 min-w-0 py-1.5 text-sm rounded-lg bg-ks-danger/20 text-ks-danger hover:bg-ks-danger hover:text-white"
                    >
                      {t("admin.delete")}
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
