import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { userFetch } from "../lib/auth";
import { useI18n } from "../lib/i18n";

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

export default function NotificationSettings() {
  const { t } = useI18n();
  const [subs, setSubs] = useState<Sub[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [unauth, setUnauth] = useState(false);
  const [newSourceId, setNewSourceId] = useState<number | "">("");
  const [newThreshold, setNewThreshold] = useState(5);
  const [newChannel, setNewChannel] = useState<"telegram" | "line">("telegram");
  const [newCooldown, setNewCooldown] = useState(30);
  const [adding, setAdding] = useState(false);
  const [message, setMessage] = useState("");

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
        channel: newChannel,
        cooldown_minutes: newCooldown,
      }),
    });
    const data = await r.json().catch(() => ({}));
    setAdding(false);
    if (r.ok) {
      load();
      setNewSourceId("");
      setMessage("Subscribed.");
    } else {
      setMessage((data.detail as string) || "Failed.");
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
    if (!confirm("Remove this subscription?")) return;
    const r = await userFetch(`${API}/notifications/subscriptions/${subId}`, { method: "DELETE" });
    if (r.ok) load();
  }

  if (unauth) {
    return (
      <div className="min-h-screen bg-bg-primary px-4 py-12">
        <div className="mx-auto max-w-2xl ks-card">
          <p className="text-text-secondary">Login required to manage notifications.</p>
          <Link to="/login" className="mt-2 inline-block text-primary hover:underline">
            Sign in
          </Link>
          <Link to="/" className="ml-4 inline-block text-text-muted hover:text-primary">
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  if (loading) return <p className="min-h-screen bg-bg-primary p-8 text-text-muted">{t("common.loading")}</p>;

  return (
    <div className="min-h-screen bg-bg-primary">
      <header className="border-b border-border-dark bg-bg-secondary shadow-lg">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="font-gaming text-xl font-semibold text-text-primary">
            {t("app.name")}
          </Link>
          <nav className="flex gap-4">
            <Link to="/" className="text-sm text-text-secondary hover:text-primary">
              Home
            </Link>
            <Link to="/login" className="text-sm text-text-secondary hover:text-primary">
              {t("nav.login")}
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-4 py-8">
        <h1 className="font-gaming mb-6 text-2xl font-bold text-text-primary">{t("notifications.title")}</h1>
        <p className="mb-6 text-sm text-text-secondary">
          Get notified when kite count reaches your threshold for a stream. Set channel (LINE or Telegram) and cooldown.
        </p>

        <form onSubmit={addSub} className="ks-card mb-8">
          <h2 className="font-gaming mb-3 font-medium text-text-primary">Add subscription</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-xs text-text-muted">Stream</label>
              <select
                value={newSourceId}
                onChange={(e) => setNewSourceId(e.target.value === "" ? "" : Number(e.target.value))}
                className="ks-input mt-1"
                required
              >
                <option value="">Select stream</option>
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name || s.location || `Source ${s.id}`}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-text-muted">Notify when count &gt;=</label>
              <input
                type="number"
                min={1}
                max={100}
                value={newThreshold}
                onChange={(e) => setNewThreshold(Number(e.target.value) || 5)}
                className="ks-input mt-1"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted">Channel</label>
              <select
                value={newChannel}
                onChange={(e) => setNewChannel(e.target.value as "telegram" | "line")}
                className="ks-input mt-1"
              >
                <option value="telegram">Telegram</option>
                <option value="line">LINE</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-text-muted">Cooldown (minutes)</label>
              <input
                type="number"
                min={1}
                max={1440}
                value={newCooldown}
                onChange={(e) => setNewCooldown(Number(e.target.value) || 30)}
                className="ks-input mt-1"
              />
            </div>
          </div>
          {message && <p className="mt-2 text-sm text-text-secondary">{message}</p>}
          <button
            type="submit"
            disabled={adding || newSourceId === ""}
            className="ks-btn ks-btn-primary mt-3 disabled:opacity-50"
          >
            {adding ? "Adding..." : "Add"}
          </button>
        </form>

        <div className="ks-card p-0 overflow-hidden">
          <h2 className="font-gaming border-b border-border-dark p-3 font-medium text-text-primary">Your subscriptions</h2>
          {subs.length === 0 ? (
            <p className="p-4 text-text-muted">No subscriptions yet. Add one above.</p>
          ) : (
            <ul className="divide-y divide-border-dark">
              {subs.map((sub) => (
                <li key={sub.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                  <div>
                    <span className="font-medium text-text-primary">{sub.source_name}</span>
                    <span className="ml-2 text-sm text-text-muted">
                      Notify when &gt;= {sub.threshold} kites, cooldown {sub.cooldown_minutes} min, {sub.channel}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => toggleEnabled(sub)}
                      className={`ks-btn text-sm ${sub.enabled ? "bg-bg-tertiary text-text-primary" : "bg-ks-success/20 text-ks-success"}`}
                    >
                      {sub.enabled ? "On" : "Off"}
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(sub.id)}
                      className="ks-btn rounded bg-ks-danger/20 px-2 py-1 text-sm text-ks-danger hover:bg-ks-danger hover:text-white"
                    >
                      Remove
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
