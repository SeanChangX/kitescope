import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

type IntervalValue = "minute" | "5min" | "10min" | "30min" | "hour" | "day";

export default function HistorySettings() {
  const { t } = useI18n();
  const [retentionDays, setRetentionDays] = useState(30);
  const [guestHours, setGuestHours] = useState(24);
  const [defaultInterval, setDefaultInterval] = useState<IntervalValue>("hour");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    authFetch("/api/admin/settings/history")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setRetentionDays(d.retention_days ?? 30);
          setGuestHours(Math.max(1, Math.min(8760, d.guest_hours ?? 24)));
          const di = d.default_interval;
          setDefaultInterval(
            ["minute", "5min", "10min", "30min", "hour", "day"].includes(di) ? di : "hour"
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
      body: JSON.stringify({
        retention_days: retentionDays,
        guest_hours: guestHours,
        default_interval: defaultInterval,
      }),
    });
    if (r.ok) setMessage(t("admin.saved"));
    else setMessage(t("admin.saveFailed"));
  }

  async function clearHistory() {
    if (!window.confirm(t("admin.clearHistoryConfirm"))) return;
    setMessage(null);
    setClearing(true);
    try {
      const r = await authFetch("/api/admin/history/clear", { method: "POST" });
      if (r.ok) setMessage(t("admin.historyCleared"));
      else setMessage(t("admin.clearHistoryFailed"));
    } finally {
      setClearing(false);
    }
  }

  if (loading) return <p className="text-text-muted">{t("common.loading")}</p>;

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">{t("admin.historySettings")}</h3>
      <form onSubmit={submit} className="space-y-3 max-w-sm">
        <div>
          <label className="block text-sm text-text-muted mb-1">{t("admin.retentionDays")}</label>
          <p className="text-xs text-text-muted mb-1.5">{t("admin.retentionDaysDesc")}</p>
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
          <label className="block text-sm text-text-muted mb-1">{t("admin.guestHistoryHours")}</label>
          <p className="text-xs text-text-muted mb-1.5">{t("admin.guestHistoryHoursDesc")}</p>
          <input
            type="number"
            min={1}
            max={8760}
            value={guestHours}
            onChange={(e) => setGuestHours(Math.max(1, Math.min(8760, parseInt(e.target.value, 10) || 24)))}
            className="ks-input"
          />
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">{t("admin.defaultIntervalGuestHistory")}</label>
          <p className="text-xs text-text-muted mb-1.5">{t("admin.defaultIntervalGuestHistoryDesc")}</p>
          <select
            value={defaultInterval}
            onChange={(e) => setDefaultInterval(e.target.value as IntervalValue)}
            className="ks-input"
          >
            <option value="minute">{t("admin.intervalMinute")}</option>
            <option value="5min">{t("admin.interval5min")}</option>
            <option value="10min">{t("admin.interval10min")}</option>
            <option value="30min">{t("admin.interval30min")}</option>
            <option value="hour">{t("admin.intervalHour")}</option>
            <option value="day">{t("admin.intervalDay")}</option>
          </select>
        </div>
        {message && <p className="text-sm text-text-secondary">{message}</p>}
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="ks-btn ks-btn-primary">
            {t("admin.save")}
          </button>
          <button
            type="button"
            onClick={clearHistory}
            disabled={clearing}
            className="ks-btn ks-btn-secondary"
          >
            {clearing ? t("common.loading") : t("admin.clearHistory")}
          </button>
        </div>
      </form>
    </div>
  );
}
