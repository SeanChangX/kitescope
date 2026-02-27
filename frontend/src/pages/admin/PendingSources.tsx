import { useEffect, useRef, useState } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

const API = "/api";

type Pending = {
  id: number;
  url: string;
  type: string;
  name: string;
  location: string;
  created_at: string;
};

function PreviewImage({ id }: { id: number }) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState(false);
  const urlRef = useRef<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    authFetch(`${API}/admin/sources/pending/${id}/preview`)
      .then((r) => {
        if (cancelled || !r.ok) return null;
        return r.blob();
      })
      .then((blob) => {
        if (cancelled || !blob) {
          if (!cancelled) setErr(true);
          return;
        }
        const u = URL.createObjectURL(blob);
        urlRef.current = u;
        setSrc(u);
      })
      .catch(() => !cancelled && setErr(true));
    return () => {
      cancelled = true;
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
      }
    };
  }, [id]);
  if (err) return <div className="text-xs text-text-muted">Preview unavailable</div>;
  if (!src) return <div className="h-20 w-32 animate-pulse rounded bg-bg-tertiary" />;
  return <img src={src} alt="Preview" className="h-20 w-32 rounded object-cover" />;
}

export default function PendingSources() {
  const { t } = useI18n();
  const [list, setList] = useState<Pending[]>([]);
  const [loading, setLoading] = useState(true);

  function load() {
    authFetch(`${API}/admin/sources/pending`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setList)
      .catch(() => setList([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function approve(id: number) {
    const r = await authFetch(`${API}/admin/sources/pending/${id}/approve`, { method: "POST" });
    if (r.ok) load();
  }

  async function remove(id: number) {
    if (!confirm(t("admin.deleteSuggestionConfirm"))) return;
    const r = await authFetch(`${API}/admin/sources/pending/${id}`, { method: "DELETE" });
    if (r.ok) load();
  }

  if (loading) return <p className="text-text-muted">{t("common.loading")}</p>;

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">{t("admin.pendingSources")}</h3>
      {list.length === 0 ? (
        <p className="text-text-muted">{t("admin.noPending")}</p>
      ) : (
        <div className="space-y-3">
          {list.map((p) => (
            <div
              key={p.id}
              className="flex flex-col gap-3 rounded border border-border p-3"
            >
              <div className="flex flex-wrap items-start gap-3 text-sm">
                <PreviewImage id={p.id} />
                <div className="min-w-0 flex-1">
                  <span className="font-medium text-text-primary">{p.name || `#${p.id}`}</span>
                  <span className="ml-2 text-text-muted">{p.type}</span>
                  <div className="truncate text-text-muted">{p.url}</div>
                  {p.location && <div className="text-text-muted">Location: {p.location}</div>}
                </div>
              </div>
              <div className="flex w-full gap-2">
                <button
                  onClick={() => approve(p.id)}
                  className="ks-btn flex-1 min-w-0 py-1.5 rounded bg-ks-success/20 text-ks-success hover:bg-ks-success hover:text-bg-primary"
                >
                  {t("admin.approve")}
                </button>
                <button
                  onClick={() => remove(p.id)}
                  className="ks-btn flex-1 min-w-0 py-1.5 rounded bg-ks-danger/20 text-ks-danger hover:bg-ks-danger hover:text-white"
                >
                  {t("admin.delete")}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
