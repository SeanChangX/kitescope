import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { userFetch } from "../lib/auth";
import { useI18n } from "../lib/i18n";

const API = "/api";

const THRESHOLD_MIN = 1;
const THRESHOLD_MAX = 100;
const COOLDOWN_MIN = 1;
const COOLDOWN_MAX = 1440;

/** Allow empty inputs while typing; validation happens on submit. */
type NumInput = number | "";

/** Returns a valid integer within [min, max], or null when empty/out of range. */
function validInt(value: NumInput, min: number, max: number): number | null {
  if (value === "" || Number.isNaN(value)) return null;
  const n = Math.trunc(value);
  if (n < min || n > max) return null;
  return n;
}

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
  const [newThreshold, setNewThreshold] = useState<NumInput>(5);
  const [newCooldown, setNewCooldown] = useState<NumInput>(30);
  const [adding, setAdding] = useState(false);
  const [message, setMessage] = useState("");
  const [lineAddFriendUrl, setLineAddFriendUrl] = useState("");
  const [togglingMap, setTogglingMap] = useState<Record<number, boolean>>({});
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editThreshold, setEditThreshold] = useState<NumInput>(5);
  const [editCooldown, setEditCooldown] = useState<NumInput>(30);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState("");

  async function load(options?: { showLoading?: boolean }) {
    if (options?.showLoading) setLoading(true);
    setUnauth(false);
    try {
      const [rSubs, rSources, rMe, rLineUrl] = await Promise.all([
        userFetch(`${API}/notifications/subscriptions`),
        fetch(`${API}/sources`),
        userFetch(`${API}/auth/me`),
        fetch(`${API}/auth/line/add-friend-url`),
      ]);

      if (rSubs.status === 401) {
        setUnauth(true);
        return;
      }

      if (rSubs.ok) {
        const nextSubs = await rSubs.json().catch(() => []);
        setSubs(Array.isArray(nextSubs) ? nextSubs : []);
      } else {
        setSubs([]);
      }

      if (rSources.ok) {
        const nextSources = await rSources.json().catch(() => []);
        setSources(Array.isArray(nextSources) ? nextSources : []);
      }

      if (rMe?.ok && rLineUrl?.ok) {
        const [me, lineUrl] = await Promise.all([
          rMe.json().catch(() => ({})),
          rLineUrl.json().catch(() => ({})),
        ]) as [{ line_id?: boolean }, { url?: string }];
        if (me.line_id && lineUrl.url) setLineAddFriendUrl(lineUrl.url);
      }
    } catch {
      setSubs([]);
    } finally {
      if (options?.showLoading) setLoading(false);
    }
  }

  useEffect(() => {
    void load({ showLoading: true });
  }, []);

  async function addSub(e: React.FormEvent) {
    e.preventDefault();
    if (newSourceId === "") return;
    const threshold = validInt(newThreshold, THRESHOLD_MIN, THRESHOLD_MAX);
    if (threshold === null) {
      setMessage(t("notifications.thresholdInvalid"));
      return;
    }
    const cooldown = validInt(newCooldown, COOLDOWN_MIN, COOLDOWN_MAX);
    if (cooldown === null) {
      setMessage(t("notifications.cooldownInvalid"));
      return;
    }
    setAdding(true);
    setMessage("");
    const r = await userFetch(`${API}/notifications/subscriptions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_id: newSourceId,
        threshold,
        cooldown_minutes: cooldown,
      }),
    });
    const data = await r.json().catch(() => ({}));
    setAdding(false);
    if (r.ok) {
      await load();
      setNewSourceId("");
      setNewThreshold(5);
      setNewCooldown(30);
      setMessage(t("notifications.subscribed"));
    } else {
      setMessage((data.detail as string) || t("notifications.failed"));
    }
  }

  async function toggleEnabled(sub: Sub) {
    if (togglingMap[sub.id]) return;
    const nextEnabled = !sub.enabled;
    setTogglingMap((prev) => ({ ...prev, [sub.id]: true }));
    setSubs((prev) => prev.map((s) => (s.id === sub.id ? { ...s, enabled: nextEnabled } : s)));
    try {
      const r = await userFetch(`${API}/notifications/subscriptions/${sub.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      if (!r.ok) {
        setSubs((prev) => prev.map((s) => (s.id === sub.id ? { ...s, enabled: sub.enabled } : s)));
        setMessage(t("notifications.failed"));
      }
    } catch {
      setSubs((prev) => prev.map((s) => (s.id === sub.id ? { ...s, enabled: sub.enabled } : s)));
      setMessage(t("notifications.failed"));
    } finally {
      setTogglingMap((prev) => {
        const next = { ...prev };
        delete next[sub.id];
        return next;
      });
    }
  }

  async function remove(subId: number) {
    if (!confirm(t("notifications.removeSubscriptionConfirm"))) return;
    const snapshot = subs;
    setSubs((prev) => prev.filter((s) => s.id !== subId));
    const r = await userFetch(`${API}/notifications/subscriptions/${subId}`, { method: "DELETE" });
    if (!r.ok) {
      setSubs(snapshot);
      setMessage(t("notifications.failed"));
    }
  }

  function startEdit(sub: Sub) {
    setEditingId(sub.id);
    setEditThreshold(sub.threshold);
    setEditCooldown(sub.cooldown_minutes);
    setEditError("");
  }

  function cancelEdit() {
    setEditingId(null);
    setEditError("");
  }

  async function saveEdit(sub: Sub) {
    const threshold = validInt(editThreshold, THRESHOLD_MIN, THRESHOLD_MAX);
    if (threshold === null) {
      setEditError(t("notifications.thresholdInvalid"));
      return;
    }
    const cooldown = validInt(editCooldown, COOLDOWN_MIN, COOLDOWN_MAX);
    if (cooldown === null) {
      setEditError(t("notifications.cooldownInvalid"));
      return;
    }
    setSavingEdit(true);
    setEditError("");
    // Keep hysteresis consistent with create logic (release = threshold - 2).
    const releaseThreshold = Math.max(0, threshold - 2);
    const snapshot = subs;
    setSubs((prev) =>
      prev.map((s) =>
        s.id === sub.id
          ? { ...s, threshold, cooldown_minutes: cooldown, release_threshold: releaseThreshold }
          : s
      )
    );
    try {
      const r = await userFetch(`${API}/notifications/subscriptions/${sub.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          threshold,
          cooldown_minutes: cooldown,
          release_threshold: releaseThreshold,
        }),
      });
      if (!r.ok) {
        setSubs(snapshot);
        setEditError(t("notifications.failed"));
        return;
      }
      setEditingId(null);
      setMessage(t("notifications.saved"));
    } catch {
      setSubs(snapshot);
      setEditError(t("notifications.failed"));
    } finally {
      setSavingEdit(false);
    }
  }

  if (unauth) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-12">
        <div className="ks-card">
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
    return <p className="p-8 text-text-muted">{t("common.loading")}</p>;
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 sm:max-w-7xl sm:px-6">
        <h1 className="font-gaming mb-6 text-2xl font-bold text-text-primary sm:text-3xl">
          {t("notifications.title")}
        </h1>
        <p className="mb-6 text-sm text-text-secondary">{t("notifications.description")}</p>

        {lineAddFriendUrl && (
          <div className="mb-6 rounded-lg border border-border bg-bg-secondary/50 px-4 py-3 text-sm text-text-secondary">
            <p className="mb-2">{t("notifications.lineAddFriendHint")}</p>
            <a
              href={lineAddFriendUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block rounded-md border border-primary bg-primary/10 px-3 py-1.5 font-medium text-primary hover:bg-primary/20"
            >
              {t("notifications.lineAddFriend")}
            </a>
          </div>
        )}

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
                min={THRESHOLD_MIN}
                max={THRESHOLD_MAX}
                value={newThreshold}
                onChange={(e) => setNewThreshold(e.target.value === "" ? "" : Number(e.target.value))}
                className="ks-input mt-1"
              />
              <p className="mt-1 text-xs text-text-muted">{t("notifications.thresholdRange")}</p>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-text-muted">
                {t("notifications.cooldownMinutes")}
              </label>
              <input
                type="number"
                min={COOLDOWN_MIN}
                max={COOLDOWN_MAX}
                value={newCooldown}
                onChange={(e) => setNewCooldown(e.target.value === "" ? "" : Number(e.target.value))}
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
              {subs.map((sub) => {
                const isEditing = editingId === sub.id;
                return (
                  <li
                    key={sub.id}
                    className="flex flex-col gap-3 p-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0 flex-1">
                      <span className="font-medium text-text-primary">{sub.source_name}</span>
                      {isEditing ? (
                        <div className="mt-2 flex flex-wrap items-end gap-3">
                          <div>
                            <label className="block text-xs text-text-muted">
                              {t("notifications.notifyWhenCount")}
                            </label>
                            <input
                              type="number"
                              min={THRESHOLD_MIN}
                              max={THRESHOLD_MAX}
                              value={editThreshold}
                              onChange={(e) =>
                                setEditThreshold(e.target.value === "" ? "" : Number(e.target.value))
                              }
                              className="ks-input mt-1 w-28"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-text-muted">
                              {t("notifications.cooldownMinutes")}
                            </label>
                            <input
                              type="number"
                              min={COOLDOWN_MIN}
                              max={COOLDOWN_MAX}
                              value={editCooldown}
                              onChange={(e) =>
                                setEditCooldown(e.target.value === "" ? "" : Number(e.target.value))
                              }
                              className="ks-input mt-1 w-28"
                            />
                          </div>
                          {editError && (
                            <p className="w-full text-xs text-ks-danger">{editError}</p>
                          )}
                        </div>
                      ) : (
                        <span className="ml-2 text-sm text-text-muted">{formatSubDesc(sub, t)}</span>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-wrap justify-end gap-2">
                      {isEditing ? (
                        <>
                          <button
                            type="button"
                            onClick={() => saveEdit(sub)}
                            disabled={savingEdit}
                            className="ks-btn ks-btn-primary w-20 py-1.5 text-sm disabled:opacity-50"
                          >
                            {t("notifications.save")}
                          </button>
                          <button
                            type="button"
                            onClick={cancelEdit}
                            disabled={savingEdit}
                            className="ks-btn ks-btn-secondary w-20 py-1.5 text-sm disabled:opacity-50"
                          >
                            {t("notifications.cancel")}
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => toggleEnabled(sub)}
                            disabled={!!togglingMap[sub.id]}
                            className={`ks-btn w-20 py-1.5 text-sm ${
                              sub.enabled
                                ? "bg-ks-success/20 text-ks-success hover:bg-ks-success hover:text-bg-primary"
                                : "ks-btn-secondary"
                            } ${togglingMap[sub.id] ? "opacity-60 cursor-not-allowed" : ""}`}
                          >
                            {sub.enabled ? t("notifications.on") : t("notifications.off")}
                          </button>
                          <button
                            type="button"
                            onClick={() => startEdit(sub)}
                            className="ks-btn w-20 py-1.5 text-sm bg-primary/10 text-primary hover:bg-primary hover:text-white"
                          >
                            {t("notifications.edit")}
                          </button>
                          <button
                            type="button"
                            onClick={() => remove(sub.id)}
                            className="ks-btn w-20 py-1.5 text-sm rounded-lg bg-ks-danger/20 text-ks-danger hover:bg-ks-danger hover:text-white"
                          >
                            {t("notifications.remove")}
                          </button>
                        </>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
    </main>
  );
}
