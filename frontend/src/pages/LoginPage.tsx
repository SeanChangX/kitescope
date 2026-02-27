import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useI18n } from "../lib/i18n";

const API = "/api";

export default function LoginPage() {
  const { t } = useI18n();
  const [lineUrl, setLineUrl] = useState("");
  const [telegramBot, setTelegramBot] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const redirectUri = `${window.location.origin}/auth/callback`;
    fetch(`${API}/auth/line/login-url?redirect_uri=${encodeURIComponent(redirectUri)}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.url) setLineUrl(d.url);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    fetch(`${API}/auth/telegram/bot-username`)
      .then((r) => r.json())
      .then((d) => setTelegramBot((d.bot_username as string) || ""))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!telegramBot) return;
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", telegramBot);
    script.setAttribute("data-auth-url", `${window.location.origin}/auth/telegram-callback`);
    script.setAttribute("data-request-access", "write");
    script.async = true;
    const wrap = document.getElementById("telegram-widget-wrap");
    if (wrap) {
      wrap.appendChild(script);
      return () => {
        wrap.removeChild(script);
      };
    }
  }, [telegramBot]);

  return (
    <div className="min-h-screen bg-bg-primary px-4 py-12">
      <div className="mx-auto max-w-sm ks-card">
      <h2 className="font-gaming mb-4 text-xl font-semibold text-text-primary">{t("login.title")}</h2>
      <p className="mb-4 text-sm text-text-secondary">
        {t("login.signInDesc")}
      </p>
      {loading ? (
        <p className="text-text-muted">{t("common.loading")}</p>
      ) : (
        <div className="space-y-4">
          {lineUrl ? (
            <a
              href={lineUrl}
              className="block w-full rounded bg-[#06C755] px-4 py-2 text-center font-medium text-white hover:bg-[#05b34a]"
            >
              {t("login.line")}
            </a>
          ) : (
            <p className="text-sm text-text-muted">{t("login.lineUnavailable")}</p>
          )}
          {telegramBot ? (
            <div id="telegram-widget-wrap" className="flex justify-center" />
          ) : (
            <p className="text-sm text-text-muted">{t("login.telegramUnavailable")}</p>
          )}
        </div>
      )}
      <Link to="/" className="mt-6 block text-center text-sm text-text-secondary hover:text-primary">
        {t("login.backToHome")}
      </Link>
      </div>
    </div>
  );
}
