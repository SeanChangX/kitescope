import { useState } from "react";
import { Link } from "react-router-dom";
import { userFetch } from "../lib/auth";
import { useI18n } from "../lib/i18n";

const API = "/api";

type Props = { onSuccess?: () => void; hasUser?: boolean };

export default function SuggestForm({ onSuccess, hasUser: _hasUser }: Props) {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [location, setLocation] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const urlError =
    url.trim() && !/^(https?|rtsp):\/\/.+/i.test(url.trim()) && !/go2rtc|youtube\.com|youtu\.be/i.test(url.trim())
      ? "Enter a valid URL (http/https/rtsp, or go2rtc/YouTube link)."
      : url.length > 2048
        ? "URL too long (max 2048 characters)."
        : null;
  const locationError = location.length > 512 ? "Location too long (max 512 characters)." : null;
  const nameError = name.length > 256 ? "Name too long (max 256 characters)." : null;
  const canSubmit =
    url.trim() &&
    !urlError &&
    !locationError &&
    !nameError;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setLoading(true);
    setMessage("");
    try {
      const r = await userFetch(`${API}/sources/suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), location: location.trim(), name: name.trim() }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        setMessage(t("suggest.submitted"));
        setUrl("");
        setLocation("");
        setName("");
        onSuccess?.();
      } else {
        setMessage(r.status === 401 ? t("suggest.loginRequired") : (data.detail || t("suggest.failed")));
      }
    } catch {
      setMessage(t("suggest.networkError"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="ks-card">
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">
            {t("suggest.urlRequired")}
          </label>
          <input
            type="url"
            placeholder={t("suggest.urlPlaceholder")}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="ks-input"
            required
          />
          <p className="mt-1 text-xs text-text-muted">
            {t("suggest.example")}
          </p>
          {urlError && <p className="mt-1 text-xs text-ks-danger">{urlError}</p>}
        </div>
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">
            {t("suggest.locationForWeather")}
          </label>
          <input
            type="text"
            placeholder={t("suggest.locationPlaceholder")}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className="ks-input"
            maxLength={513}
          />
          <p className="mt-1 text-xs text-text-muted">
            {t("suggest.locationHint")}
          </p>
          {locationError && <p className="mt-1 text-xs text-ks-danger">{locationError}</p>}
        </div>
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">
            {t("suggest.nameLabel")}
          </label>
          <input
            type="text"
            placeholder={t("suggest.namePlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="ks-input"
            maxLength={257}
          />
          <p className="mt-1 text-xs text-text-muted">
            {t("suggest.nameHint")}
          </p>
          {nameError && <p className="mt-1 text-xs text-ks-danger">{nameError}</p>}
        </div>
      </div>
      {message && (
        <p className="mt-2 text-sm text-text-secondary">
          {message}
          {message === t("suggest.loginRequired") && (
            <>
              {" "}
              <Link to="/login" className="text-primary hover:underline">{t("nav.login")}</Link>
            </>
          )}
        </p>
      )}
      <button type="submit" disabled={loading || !canSubmit} className="ks-btn ks-btn-primary mt-3 disabled:opacity-50">
        {loading ? t("suggest.submitting") : t("suggest.submit")}
      </button>
    </form>
  );
}
