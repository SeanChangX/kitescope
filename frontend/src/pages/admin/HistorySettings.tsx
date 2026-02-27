import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";

export default function HistorySettings() {
  const [retentionDays, setRetentionDays] = useState(30);
  const [defaultInterval, setDefaultInterval] = useState<"minute" | "hour" | "day">("hour");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    authFetch("/api/admin/settings/history")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setRetentionDays(d.retention_days ?? 30);
          setDefaultInterval(
            d.default_interval === "minute" || d.default_interval === "day" ? d.default_interval : "hour"
          );
        }
      })
      .finally(() => setLoading(false));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    const r = await authFetch("/api/admin/settings/history", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ retention_days: retentionDays, default_interval: defaultInterval }),
    });
    if (r.ok) setMessage("Saved.");
    else setMessage("Failed to save.");
  }

  if (loading) return <p className="text-text-muted">Loading...</p>;

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">History settings</h3>
      <form onSubmit={submit} className="space-y-3 max-w-sm">
        <div>
          <label className="block text-sm text-text-muted mb-1">Retention (days)</label>
          <input
            type="number"
            min={1}
            max={365}
            value={retentionDays}
            onChange={(e) => setRetentionDays(parseInt(e.target.value, 10) || 30)}
            className="ks-input"
          />
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">Default interval (guest history)</label>
          <select
            value={defaultInterval}
            onChange={(e) => setDefaultInterval(e.target.value as "minute" | "hour" | "day")}
            className="ks-input"
          >
            <option value="minute">Minute</option>
            <option value="hour">Hour</option>
            <option value="day">Day</option>
          </select>
        </div>
        {message && <p className="text-sm text-text-secondary">{message}</p>}
        <button type="submit" className="ks-btn ks-btn-primary">
          Save
        </button>
      </form>
    </div>
  );
}
