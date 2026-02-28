import { useState, useEffect } from "react";
import { Routes, Route, Link, NavLink } from "react-router-dom";
import { authFetch, logoutAdmin, ADMIN_SESSION_EXPIRED_EVENT } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";
import AdminLogin from "./AdminLogin";
import PendingSources from "./PendingSources";
import ManageSources from "./ManageSources";
import ChangePassword from "./ChangePassword";
import BotSettings from "./BotSettings";
import HistorySettings from "./HistorySettings";
import BackupRestore from "./BackupRestore";
import UserList from "./UserList";
import Broadcast from "./Broadcast";

function AdminDashboard() {
  const { t } = useI18n();
  return (
    <div className="space-y-6">
      <h2 className="font-gaming text-xl font-semibold text-text-primary">{t("admin.dashboard")}</h2>
      <PendingSources />
      <Broadcast />
    </div>
  );
}

function AdminSettings() {
  const { t } = useI18n();
  return (
    <div className="space-y-6">
      <h2 className="font-gaming text-xl font-semibold text-text-primary">{t("admin.settings")}</h2>
      <ChangePassword />
      <BotSettings />
      <HistorySettings />
      <BackupRestore />
    </div>
  );
}

export default function AdminLayout() {
  const { t, locale, setLocale } = useI18n();
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    authFetch("/api/admin/settings/bots")
      .then((r) => setLoggedIn(r.ok))
      .catch(() => setLoggedIn(false));
  }, []);

  useEffect(() => {
    function onSessionExpired() {
      setLoggedIn(false);
    }
    window.addEventListener(ADMIN_SESSION_EXPIRED_EVENT, onSessionExpired);
    return () => window.removeEventListener(ADMIN_SESSION_EXPIRED_EVENT, onSessionExpired);
  }, []);

  function handleLogin() {
    setLoggedIn(true);
  }

  function handleLogout() {
    logoutAdmin().then(() => setLoggedIn(false));
  }

  if (loggedIn === null) return null;
  if (!loggedIn) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-primary px-4">
        <AdminLogin onLogin={handleLogin} />
      </div>
    );
  }

  const navBtn =
    "text-sm whitespace-nowrap rounded-md border px-2 py-1 transition-all duration-200 " +
    "border-border-dark text-text-secondary hover:border-primary hover:text-primary hover:scale-[1.02] active:scale-[0.98]";
  const navBtnActive = "border-primary text-primary";
  const navBtnPrimary =
    "ks-btn ks-btn-primary text-sm whitespace-nowrap px-2 py-1 rounded-md transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98]";

  const navLinks = (
    <>
      <NavLink
        to="/admin"
        end
        onClick={() => setMenuOpen(false)}
        className={({ isActive }) => `${navBtn} ${isActive ? navBtnActive : ""}`}
      >
        {t("admin.dashboard")}
      </NavLink>
      <NavLink
        to="/admin/sources"
        onClick={() => setMenuOpen(false)}
        className={({ isActive }) => `${navBtn} ${isActive ? navBtnActive : ""}`}
      >
        {t("admin.sources")}
      </NavLink>
      <NavLink
        to="/admin/users"
        onClick={() => setMenuOpen(false)}
        className={({ isActive }) => `${navBtn} ${isActive ? navBtnActive : ""}`}
      >
        {t("admin.users")}
      </NavLink>
      <NavLink
        to="/admin/settings"
        onClick={() => setMenuOpen(false)}
        className={({ isActive }) => `${navBtn} ${isActive ? navBtnActive : ""}`}
      >
        {t("admin.settings")}
      </NavLink>
      <Link to="/" className={navBtnPrimary} onClick={() => setMenuOpen(false)}>
        {t("nav.backToApp")}
      </Link>
      <button
        type="button"
        onClick={() => { handleLogout(); setMenuOpen(false); }}
        className={`${navBtnPrimary} cursor-pointer`}
      >
        {t("nav.logout")}
      </button>
    </>
  );

  return (
    <div className="flex min-h-screen flex-col bg-bg-primary">
      <header className="shrink-0 border-b border-border-dark bg-bg-secondary shadow-lg">
        <div className="mx-auto flex min-h-14 max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <Link to="/" className="font-gaming text-lg font-semibold text-text-primary shrink-0">
            {t("app.name")} Admin
          </Link>
          <div className="hidden sm:flex flex-wrap items-center justify-end gap-2 min-w-0 flex-1">
            <div className="flex items-center gap-1 text-sm text-text-muted font-lang shrink-0">
              <button type="button" onClick={() => setLocale("en")} className={`px-1.5 py-0.5 rounded ${locale === "en" ? "text-primary font-medium" : "hover:text-text-secondary"}`}>EN</button>
              <span className="text-border">|</span>
              <button type="button" onClick={() => setLocale("zh-TW")} className={`px-1.5 py-0.5 rounded ${locale === "zh-TW" ? "text-primary font-medium" : "hover:text-text-secondary"}`}>繁中</button>
            </div>
            <nav className="flex flex-wrap items-center gap-2">
              {navLinks}
            </nav>
          </div>
          <div className="sm:hidden flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMenuOpen((o) => !o)}
              className="p-2 text-text-secondary hover:text-primary rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-bg-secondary"
              aria-label="Menu"
              aria-expanded={menuOpen}
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                {menuOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </div>
        {menuOpen && (
          <div className="sm:hidden border-t border-border-dark bg-bg-secondary px-4 py-3 flex flex-col gap-2">
            {navLinks}
          </div>
        )}
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto px-4 py-8">
        <div className="mx-auto max-w-6xl">
          <Routes>
            <Route index element={<AdminDashboard />} />
            <Route path="sources" element={<ManageSources />} />
            <Route path="users" element={<UserList />} />
            <Route path="settings" element={<AdminSettings />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
