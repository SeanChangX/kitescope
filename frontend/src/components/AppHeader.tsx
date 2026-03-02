import { Link, useLocation } from "react-router-dom";
import { userFetch, logoutUser, USER_SESSION_EXPIRED_EVENT } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { useEffect, useState } from "react";

type UserInfo = { user_id: number; display_name: string; avatar: string } | null;

export default function AppHeader() {
  const { t, locale, setLocale } = useI18n();
  const location = useLocation();
  const [user, setUser] = useState<UserInfo>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const isHomePage = location.pathname === "/";
  const isNotificationsPage = location.pathname === "/notifications";

  useEffect(() => {
    userFetch("/api/auth/me")
      .then((r) => r.json().catch(() => null))
      .then((d) => (d?.user_id != null ? { user_id: d.user_id, display_name: d.display_name || "", avatar: d.avatar || "" } : null))
      .then((u) => {
        setUser(u);
        setAuthChecked(true);
      })
      .catch(() => {
        setUser(null);
        setAuthChecked(true);
      });
  }, []);

  useEffect(() => {
    function onSessionExpired() {
      setUser(null);
    }
    window.addEventListener(USER_SESSION_EXPIRED_EVENT, onSessionExpired);
    return () => window.removeEventListener(USER_SESSION_EXPIRED_EVENT, onSessionExpired);
  }, []);

  function handleLogout() {
    logoutUser().then(() => setUser(null));
  }

  return (
    <header className="sticky top-0 z-20 border-b border-border-dark bg-bg-secondary">
      <div className="mx-auto flex h-14 min-h-0 max-w-7xl items-center justify-between gap-2 px-4 sm:h-16 sm:px-6">
        <div className="flex min-w-0 shrink items-center gap-2 sm:gap-3">
          <img src="/favicon.svg" alt={t("app.name")} className="h-8 w-8 shrink-0 sm:h-9 sm:w-9 brightness-0 invert" />
          <span className="font-gaming truncate text-base font-semibold text-text-primary sm:text-xl">
            {t("app.name")}
          </span>
        </div>
        <nav className="flex shrink-0 items-center gap-2 sm:gap-6">
          <div className="flex items-center gap-0.5 text-xs text-text-muted font-lang sm:gap-1 sm:text-sm">
            <button
              type="button"
              onClick={() => setLocale("en")}
              className={`rounded px-1 py-0.5 sm:px-1.5 ${locale === "en" ? "text-primary font-medium" : "hover:text-text-secondary"}`}
            >
              EN
            </button>
            <span className="text-border">|</span>
            <button
              type="button"
              onClick={() => setLocale("zh-TW")}
              className={`rounded px-1 py-0.5 sm:px-1.5 ${locale === "zh-TW" ? "text-primary font-medium" : "hover:text-text-secondary"}`}
            >
              繁中
            </button>
          </div>
          {!authChecked ? (
            <span className="ks-btn shrink-0 py-1.5 px-3 text-sm border border-transparent text-transparent select-none pointer-events-none sm:py-2.5 sm:px-5" aria-hidden>
              {t("nav.login")}
            </span>
          ) : user ? (
            <>
              {!isHomePage && (
              <Link
                to="/"
                className="text-xs rounded-md border border-border-dark px-2 py-1 text-text-secondary transition-all duration-200 hover:border-primary hover:text-primary sm:text-sm sm:px-3 sm:py-1.5"
              >
                {t("nav.home")}
              </Link>
              )}
              {!isNotificationsPage && (
              <Link
                to="/notifications"
                className="text-xs rounded-md border border-border-dark px-2 py-1 text-text-secondary transition-all duration-200 hover:border-primary hover:text-primary sm:text-sm sm:px-3 sm:py-1.5"
              >
                {t("nav.notifications")}
              </Link>
              )}
              <span className="hidden max-w-[100px] truncate text-sm text-text-muted sm:block sm:px-1">
                {user.display_name || "User"}
              </span>
              <button
                type="button"
                onClick={handleLogout}
                className="text-xs rounded-md border border-border-dark px-2 py-1 text-text-secondary bg-transparent transition-all duration-200 hover:border-primary hover:text-primary sm:text-sm sm:px-3 sm:py-1.5"
              >
                {t("nav.logout")}
              </button>
            </>
          ) : (
            <Link
              to="/login"
              className="ks-btn ks-btn-primary shrink-0 py-1.5 px-3 text-sm transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98] sm:py-2.5 sm:px-5"
            >
              {t("nav.login")}
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
