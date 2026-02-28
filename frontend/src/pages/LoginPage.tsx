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
    Promise.all([
      fetch(`${API}/auth/line/login-url?redirect_uri=${encodeURIComponent(redirectUri)}`)
        .then((r) => r.json())
        .then((d) => (d.url ? d.url : ""))
        .catch(() => ""),
      fetch(`${API}/auth/telegram/bot-username`)
        .then((r) => r.json())
        .then((d) => (d.bot_username as string) || "")
        .catch(() => ""),
    ]).then(([url, bot]) => {
      setLineUrl(url);
      setTelegramBot(bot);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!telegramBot) return;
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", telegramBot);
    script.setAttribute("data-auth-url", `${window.location.origin}/auth/telegram-callback`);
    script.setAttribute("data-request-access", "write");
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "8");
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
        <div className="flex flex-col items-center gap-4">
          {lineUrl ? (
            <a
              href={lineUrl}
              className="flex min-h-[42px] w-[240px] max-w-full items-center justify-center gap-2 rounded-lg bg-[#06C755] px-4 text-lg font-semibold text-white hover:bg-[#05b34a]"
            >
              <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M19.365 9.863c.349 0 .63.285.63.631 0 .345-.281.63-.63.63H17.61v1.125h1.755c.349 0 .63.283.63.63 0 .344-.281.629-.63.629h-2.386c-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63h2.386c.346 0 .627.285.627.63 0 .349-.281.63-.63.63H17.61v1.125h1.755zm-3.855 3.016c0 .27-.174.51-.432.596-.064.021-.133.031-.199.031-.211 0-.391-.09-.51-.25l-2.443-3.317v2.94c0 .344-.279.629-.631.629-.346 0-.626-.285-.626-.629V8.108c0-.27.173-.51.43-.595.06-.023.136-.033.194-.033.195 0 .375.104.495.254l2.462 3.33V8.108c0-.345.282-.63.63-.63.345 0 .63.285.63.63v4.771zm-5.741 0c0 .344-.282.629-.631.629-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63.346 0 .628.285.628.63v4.771zm-2.466.629H4.917c-.345 0-.63-.285-.63-.629V8.108c0-.345.285-.63.63-.63.349 0 .63.285.63.63v4.141h1.756c.348 0 .629.283.629.63 0 .344-.281.629-.629.629M24 10.314C24 4.943 18.615.572 12 .572S0 4.943 0 10.314c0 4.811 4.27 8.842 10.035 9.608.391.082.923.258 1.058.59.12.301.079.766.039 1.084l-.164 1.02c-.045.301-.24 1.186 1.049.645 1.291-.539 6.916-4.078 9.436-6.975C23.176 14.393 24 12.458 24 10.314" />
              </svg>
              {t("login.line")}
            </a>
          ) : (
            <p className="text-sm text-text-muted">{t("login.lineUnavailable")}</p>
          )}
          {telegramBot ? (
            <div
              id="telegram-widget-wrap"
              className="flex min-h-[42px] w-[240px] max-w-full items-center justify-center"
            />
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
