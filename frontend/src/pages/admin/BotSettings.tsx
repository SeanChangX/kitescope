import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

const MASK = "••••••••••••••";

type BotState = {
  line: {
    channel_id: string;
    channel_secret: string;
    channel_access_token: string;
    login_channel_id?: string;
    login_channel_secret?: string;
    configured: boolean;
  };
  telegram: { bot_token: string; configured: boolean };
  public_app_url: string;
};

export default function BotSettings() {
  const { t } = useI18n();
  const [data, setData] = useState<BotState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState({
    line_channel_id: "",
    line_channel_secret: "",
    line_channel_access_token: "",
    line_login_channel_id: "",
    line_login_channel_secret: "",
    telegram_bot_token: "",
    public_app_url: "",
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
            line_login_channel_id: d.line?.login_channel_id ?? "",
            line_login_channel_secret: "",
            telegram_bot_token: "",
            public_app_url: d.public_app_url ?? "",
          }));
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (data) {
      setForm((f) => ({
        ...f,
        line_channel_id: data.line?.channel_id ?? "",
        line_login_channel_id: data.line?.login_channel_id ?? "",
        public_app_url: data.public_app_url ?? "",
      }));
    }
  }, [data]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    setSaving(true);
    const body: Record<string, string> = { line_channel_id: form.line_channel_id };
    if (form.line_channel_secret && form.line_channel_secret !== MASK) body.line_channel_secret = form.line_channel_secret;
    if (form.line_channel_access_token && form.line_channel_access_token !== MASK) body.line_channel_access_token = form.line_channel_access_token;
    if (form.line_login_channel_id !== undefined) body.line_login_channel_id = form.line_login_channel_id;
    if (form.line_login_channel_secret && form.line_login_channel_secret !== MASK) body.line_login_channel_secret = form.line_login_channel_secret;
    if (form.telegram_bot_token && form.telegram_bot_token !== MASK) body.telegram_bot_token = form.telegram_bot_token;
    if (form.public_app_url !== undefined) body.public_app_url = form.public_app_url;
    const r = await authFetch("/api/admin/settings/bots", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setSaving(false);
    if (r.ok) {
      setMessage(t("admin.saved"));
      authFetch("/api/admin/settings/bots")
        .then((res) => (res.ok ? res.json() : null))
        .then(setData);
    } else {
      setMessage(t("admin.saveFailed"));
    }
  }

  if (loading) return <p className="text-text-muted">{t("common.loading")}</p>;

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">{t("admin.botSettings")}</h3>
      <form onSubmit={submit} className="space-y-4 max-w-lg">
        <div>
          <h4 className="text-sm font-medium text-text-secondary mb-2">{t("admin.line")}</h4>
          <div className="space-y-2">
            <p className="text-xs font-medium text-text-muted mt-2 first:mt-0">{t("admin.lineMessagingApi")}</p>
            <input
              type="text"
              placeholder={t("admin.channelId")}
              value={form.line_channel_id}
              onChange={(e) => setForm((f) => ({ ...f, line_channel_id: e.target.value }))}
              className="ks-input"
            />
            <input
              type="password"
              placeholder={t("admin.channelSecretPlaceholder")}
              value={form.line_channel_secret || (data?.line?.configured ? MASK : "")}
              onChange={(e) => setForm((f) => ({ ...f, line_channel_secret: e.target.value === MASK ? "" : e.target.value }))}
              className="ks-input"
            />
            <input
              type="password"
              placeholder={t("admin.channelAccessTokenPlaceholder")}
              value={form.line_channel_access_token || (data?.line?.configured ? MASK : "")}
              onChange={(e) => setForm((f) => ({ ...f, line_channel_access_token: e.target.value === MASK ? "" : e.target.value }))}
              className="ks-input"
            />
            <p className="text-xs font-medium text-text-muted mt-2">{t("admin.lineLoginSection")}</p>
            <input
              type="text"
              placeholder={t("admin.lineLoginChannelIdPlaceholder")}
              value={form.line_login_channel_id}
              onChange={(e) => setForm((f) => ({ ...f, line_login_channel_id: e.target.value }))}
              className="ks-input"
            />
            <input
              type="password"
              placeholder={t("admin.lineLoginChannelSecretPlaceholder")}
              value={form.line_login_channel_secret || (data?.line?.login_channel_id ? MASK : "")}
              onChange={(e) => setForm((f) => ({ ...f, line_login_channel_secret: e.target.value === MASK ? "" : e.target.value }))}
              className="ks-input"
            />
            {data?.line?.configured && (
              <p className="text-xs text-text-muted">{t("admin.lineConfiguredHint")}</p>
            )}
          </div>
        </div>
        <div>
          <h4 className="text-sm font-medium text-text-secondary mb-2">{t("admin.telegram")}</h4>
          <input
            type="password"
            placeholder={t("admin.telegramBotTokenPlaceholder")}
            value={form.telegram_bot_token || (data?.telegram?.configured ? MASK : "")}
            onChange={(e) => setForm((f) => ({ ...f, telegram_bot_token: e.target.value === MASK ? "" : e.target.value }))}
            className="ks-input"
          />
          {data?.telegram?.configured && (
            <p className="text-xs text-text-muted">{t("admin.telegramConfiguredHint")}</p>
          )}
        </div>
        <div>
          <h4 className="text-sm font-medium text-text-secondary mb-2">{t("admin.publicAppUrl")}</h4>
          <input
            type="url"
            placeholder={t("admin.publicAppUrlPlaceholder")}
            value={form.public_app_url}
            onChange={(e) => setForm((f) => ({ ...f, public_app_url: e.target.value }))}
            className="ks-input"
          />
          <p className="text-xs text-text-muted mt-1">{t("admin.publicAppUrlHint")}</p>
        </div>
        {message && <p className="text-sm text-text-secondary">{message}</p>}
        <button
          type="submit"
          disabled={saving}
          className="ks-btn ks-btn-primary disabled:opacity-50"
        >
          {saving ? t("admin.saving") : t("admin.save")}
        </button>
      </form>
    </div>
  );
}
