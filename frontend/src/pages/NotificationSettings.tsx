import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { userFetch } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import AppHeader from "../components/AppHeader";

const API = "/api";

type Source = { id: number; name: string; type: string; location: string };
type Sub = {
  id: number;
  source_id: number;
  source_name: string;
  threshold: number;
  release_threshold: number | null;
  channel: string;
  cooldown_minutes: number;
  enabled: boolean;
  last_notified_at: string | null;
};

function formatSubDesc(
  sub: Sub,
  t: (key: string) => string
): string {
  const channelLabel =
    sub.channel === "line" ? t("notifications.channelLine") : t("notifications.channelTelegram");
  return t("notifications.notifyWhenKites")
    .replace("{threshold}", String(sub.threshold))
    .replace("{minutes}", String(sub.cooldown_minutes))
    .replace("{channel}", channelLabel);
}

export default function NotificationSettings() {
  const { t } = useI18n();
  const [subs, setSubs] = useState<Sub[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [unauth, setUnauth] = useState(false);
  const [newSourceId, setNewSourceId] = useState<number | "">("");
  const [newThreshold, setNewThreshold] = useState(5);
  const [newCooldown, setNewCooldown] = useState(30);
  const [adding, setAdding] = useState(false);
  const [message, setMessage] = useState("");
  const [testLoading, setTestLoading] = useState(false);
  const [testMessage, setTestMessage] = useState("");

  function load() {
    setLoading(true);
    setUnauth(false);
    Promise.all([
      userFetch(`${API}/notifications/subscriptions`),
      fetch(`${API}/sources`),
    ])
      .then(([rSubs, rSources]) => {
        if (rSubs.status === 401) {
          setUnauth(true);
          return;
        }
        if (rSubs.ok) rSubs.json().then(setSubs).catch(() => setSubs([]));
        if (rSources.ok) rSources.json().then(setSources).catch(() => setSources([]));
      })
      .catch(() => setSubs([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function addSub(e: React.FormEvent) {
    e.preventDefault();
    if (newSourceId === "") return;
    setAdding(true);
    setMessage("");
    const r = await userFetch(`${API}/notifications/subscriptions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_id: newSourceId,
        threshold: newThreshold,
        cooldown_minutes: newCooldown,
      }),
    });
    const data = await r.json().catch(() => ({}));
    setAdding(false);
    if (r.ok) {
      load();
      setNewSourceId("");
      setMessage(t("notifications.subscribed"));
    } else {
      setMessage((data.detail as string) || t("notifications.failed"));
    }
  }

  async function toggleEnabled(sub: Sub) {
    const r = await userFetch(`${API}/notifications/subscriptions/${sub.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !sub.enabled }),
    });
    if (r.ok) load();
  }

  async function remove(subId: number) {
    if (!confirm(t("notifications.removeSubscriptionConfirm"))) return;
    const r = await userFetch(`${API}/notifications/subscriptions/${subId}`, { method: "DELETE" });
    if (r.ok) load();
  }

  async function sendTest() {
    setTestMessage("");
    setTestLoading(true);
    const r = await userFetch(`${API}/notifications/test`, { method: "POST" });
    const data = await r.json().catch(() => ({}));
    setTestLoading(false);
    if (r.ok) {
      setTestMessage(t("notifications.testSent"));
    } else {
      setTestMessage((data.detail as string) || t("notifications.testFailed"));
    }
  }

  if (unauth) {
    return (
      <div className="min-h-screen bg-bg-primary px-4 py-12">
        <AppHeader />
        <div className="mx-auto max-w-2xl ks-card">
          <p className="text-text-secondary">{t("notifications.loginRequired")}</p>
          <Link to="/login" className="mt-2 inline-block text-primary hover:underline">
            {t("notifications.signIn")}
          </Link>
          <Link to="/" className="ml-4 inline-block text-text-muted hover:text-primary">
            {t("notifications.backToHome")}
          </Link>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-bg-primary">
        <AppHeader />
        <p className="p-8 text-text-muted">{t("common.loading")}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-primary">
      <AppHeader />
      <main className="mx-auto max-w-2xl px-4 py-8 sm:max-w-7xl sm:px-6">
        <h1 className="font-gaming mb-6 text-2xl font-bold text-text-primary sm:text-3xl">
          {t("notifications.title")}
        </h1>
        <p className="mb-6 text-sm text-text-secondary">{t("notifications.description")}</p>
        <div className="mb-8 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={sendTest}
            disabled={testLoading}
            className="ks-btn ks-btn-secondary disabled:opacity-50"
          >
            {testLoading ? t("notifications.sendingTest") : t("notifications.test")}
          </button>
          {testMessage && (
            <span className={`text-sm ${testMessage === t("notifications.testSent") ? "text-ks-success" : "text-ks-danger"}`}>
              {testMessage}
            </span>
          )}
        </div>

        <form onSubmit={addSub} className="ks-card mb-8">
          <h2 className="font-gaming mb-3 font-medium text-text-primary">
            {t("notifications.addSubscription")}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-xs text-text-muted">{t("notifications.stream")}</label>
              <select
                value={newSourceId}
                onChange={(e) => setNewSourceId(e.target.value === "" ? "" : Number(e.target.value))}
                className="ks-input mt-1"
                required
              >
                <option value="">{t("notifications.selectStream")}</option>
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name || s.location || `Source ${s.id}`}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-text-muted">
                {t("notifications.notifyWhenCount")}
              </label>
              <input
                type="number"
                min={1}
                max={100}
                value={newThreshold}
                onChange={(e) => setNewThreshold(Number(e.target.value) || 5)}
                className="ks-input mt-1"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-text-muted">
                {t("notifications.cooldownMinutes")}
              </label>
              <input
                type="number"
                min={1}
                max={1440}
                value={newCooldown}
                onChange={(e) => setNewCooldown(Number(e.target.value) || 30)}
                className="ks-input mt-1"
              />
              <p className="mt-1 text-xs text-text-muted">{t("notifications.cooldownHint")}</p>
            </div>
          </div>
          {message && <p className="mt-2 text-sm text-text-secondary">{message}</p>}
          <button
            type="submit"
            disabled={adding || newSourceId === ""}
            className="ks-btn ks-btn-primary mt-3 disabled:opacity-50"
          >
            {adding ? t("notifications.adding") : t("notifications.add")}
          </button>
        </form>

        <div className="ks-card p-0 overflow-hidden">
          <h2 className="font-gaming border-b border-border-dark p-3 font-medium text-text-primary">
            {t("notifications.yourSubscriptions")}
          </h2>
          {subs.length === 0 ? (
            <p className="p-4 text-text-muted">{t("notifications.noSubscriptionsYet")}</p>
          ) : (
            <ul className="divide-y divide-border-dark">
              {subs.map((sub) => (
                <li
                  key={sub.id}
                  className="flex flex-col gap-3 p-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 flex-1">
                    <span className="font-medium text-text-primary">{sub.source_name}</span>
                    <span className="ml-2 text-sm text-text-muted">
                      {formatSubDesc(sub, t)}
                    </span>
                  </div>
                  <div className="flex shrink-0 justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => toggleEnabled(sub)}
                      className={`ks-btn w-20 py-1.5 text-sm ${
                        sub.enabled
                          ? "ks-btn-secondary"
                          : "bg-ks-success/20 text-ks-success hover:bg-ks-success/30 hover:text-white"
                      }`}
                    >
                      {sub.enabled ? t("notifications.on") : t("notifications.off")}
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(sub.id)}
                      className="ks-btn w-20 py-1.5 text-sm rounded-lg bg-ks-danger/20 text-ks-danger hover:bg-ks-danger hover:text-white"
                    >
                      {t("notifications.remove")}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}
