import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";

type BotState = {
  line: { channel_id: string; channel_secret: string; channel_access_token: string; configured: boolean };
  telegram: { bot_token: string; configured: boolean };
};

export default function BotSettings() {
  const [data, setData] = useState<BotState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState({
    line_channel_id: "",
    line_channel_secret: "",
    line_channel_access_token: "",
    telegram_bot_token: "",
  });

  useEffect(() => {
    authFetch("/api/admin/settings/bots")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setData(d);
          setForm((f) => ({
            ...f,
            line_channel_id: d.line?.channel_id ?? "",
            line_channel_secret: "",
            line_channel_access_token: "",
            telegram_bot_token: "",
          }));
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (data) {
      setForm((f) => ({ ...f, line_channel_id: data.line?.channel_id ?? "" }));
    }
  }, [data]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    setSaving(true);
    const body: Record<string, string> = { line_channel_id: form.line_channel_id };
    if (form.line_channel_secret) body.line_channel_secret = form.line_channel_secret;
    if (form.line_channel_access_token) body.line_channel_access_token = form.line_channel_access_token;
    if (form.telegram_bot_token) body.telegram_bot_token = form.telegram_bot_token;
    const r = await authFetch("/api/admin/settings/bots", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setSaving(false);
    if (r.ok) {
      setMessage("Saved.");
      authFetch("/api/admin/settings/bots")
        .then((res) => (res.ok ? res.json() : null))
        .then(setData);
    } else {
      setMessage("Failed to save.");
    }
  }

  if (loading) return <p className="text-text-muted">Loading...</p>;

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">Bot settings (LINE / Telegram)</h3>
      <form onSubmit={submit} className="space-y-4 max-w-lg">
        <div>
          <h4 className="text-sm font-medium text-text-secondary mb-2">LINE</h4>
          <div className="space-y-2">
            <input
              type="text"
              placeholder="Channel ID"
              value={form.line_channel_id}
              onChange={(e) => setForm((f) => ({ ...f, line_channel_id: e.target.value }))}
              className="ks-input"
            />
            <input
              type="password"
              placeholder="Channel secret (leave blank to keep existing)"
              value={form.line_channel_secret}
              onChange={(e) => setForm((f) => ({ ...f, line_channel_secret: e.target.value }))}
              className="ks-input"
            />
            <input
              type="password"
              placeholder="Channel access token (leave blank to keep existing)"
              value={form.line_channel_access_token}
              onChange={(e) => setForm((f) => ({ ...f, line_channel_access_token: e.target.value }))}
              className="ks-input"
            />
            {data?.line?.configured && (
              <p className="text-xs text-text-muted">LINE is configured. Enter new values only to overwrite.</p>
            )}
          </div>
        </div>
        <div>
          <h4 className="text-sm font-medium text-text-secondary mb-2">Telegram</h4>
          <input
            type="password"
            placeholder="Bot token (leave blank to keep existing)"
            value={form.telegram_bot_token}
            onChange={(e) => setForm((f) => ({ ...f, telegram_bot_token: e.target.value }))}
            className="ks-input"
          />
          {data?.telegram?.configured && (
            <p className="text-xs text-text-muted">Telegram is configured. Enter new token only to overwrite.</p>
          )}
        </div>
        {message && <p className="text-sm text-text-secondary">{message}</p>}
        <button
          type="submit"
          disabled={saving}
          className="ks-btn ks-btn-primary disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save"}
        </button>
      </form>
    </div>
  );
}
