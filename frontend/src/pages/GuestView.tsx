import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import SuggestForm from "./SuggestForm";
import SourceCard from "../components/SourceCard";
import { userFetch, clearUserToken, USER_SESSION_EXPIRED_EVENT } from "../lib/auth";
import { useI18n } from "../lib/i18n";

const API = "/api";

const PREVIEW_INTERVAL_MS = Number(import.meta.env.VITE_PREVIEW_INTERVAL_MS) || 3000;
const COUNTS_INTERVAL_MS = Number(import.meta.env.VITE_COUNTS_INTERVAL_MS) || 3000;

const COORDS_REGEX = /^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/;

function parseCoords(location: string): { lat: number; lon: number } | null {
  const m = (location || "").trim().match(COORDS_REGEX);
  if (!m) return null;
  const lat = parseFloat(m[1]);
  const lon = parseFloat(m[2]);
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
}

function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const x =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

type Source = { id: number; name: string; type: string; location: string; location_display?: string; enabled: boolean; url?: string };
type Counts = Record<number, { count: number; recorded_at: string }>;
type UserInfo = { user_id: number; display_name: string; avatar: string } | null;

export default function GuestView() {
  const { t, locale, setLocale } = useI18n();
  const [sources, setSources] = useState<Source[]>([]);
  const [counts, setCounts] = useState<Counts>({});
  const [user, setUser] = useState<UserInfo>(null);
  const [previewTick, setPreviewTick] = useState(0);
  const [userCoords, setUserCoords] = useState<{ lat: number; lon: number } | null>(null);

  function refreshSources() {
    fetch(`${API}/sources`)
      .then((r) => r.json())
      .then(setSources)
      .catch(console.error);
  }

  useEffect(() => {
    refreshSources();
    const retryMs = 3000;
    const retries = [1, 2, 3, 4, 5].map((i) => window.setTimeout(() => refreshSources(), i * retryMs));
    return () => retries.forEach((id) => clearTimeout(id));
  }, []);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setUserCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => {},
      { enableHighAccuracy: false, timeout: 5000, maximumAge: 300000 }
    );
  }, []);

  useEffect(() => {
    userFetch(`${API}/auth/me`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    function onSessionExpired() {
      clearUserToken();
      setUser(null);
    }
    window.addEventListener(USER_SESSION_EXPIRED_EVENT, onSessionExpired);
    return () => window.removeEventListener(USER_SESSION_EXPIRED_EVENT, onSessionExpired);
  }, []);

  function handleLogout() {
    clearUserToken();
    setUser(null);
  }

  useEffect(() => {
    const t = setInterval(() => {
      fetch(`${API}/counts`)
        .then((r) => r.json())
        .then(setCounts)
        .catch(console.error);
    }, COUNTS_INTERVAL_MS);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const t = setInterval(() => setPreviewTick((n) => n + 1), PREVIEW_INTERVAL_MS);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="min-h-screen bg-bg-primary">
      <header className="border-b border-border-dark bg-bg-secondary">
        <div className="mx-auto flex h-14 min-h-0 max-w-7xl items-center justify-between gap-2 px-4 sm:h-16 sm:px-6">
          <div className="flex min-w-0 shrink items-center gap-2 sm:gap-3">
            <img src="/favicon.svg" alt={t("app.name")} className="h-8 w-8 shrink-0 sm:h-9 sm:w-9" />
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
            {user ? (
              <>
                <Link
                  to="/notifications"
                  className="text-xs rounded-md border border-border-dark px-2 py-1 text-text-secondary transition-all duration-200 hover:border-primary hover:text-primary sm:text-sm sm:px-3 sm:py-1.5"
                >
                  {t("nav.notifications")}
                </Link>
                <span className="hidden max-w-[100px] truncate text-sm text-text-muted sm:block sm:px-1">{user.display_name || "User"}</span>
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

      <main className="mx-auto max-w-7xl px-6 py-10 sm:py-12">
        <section className="mb-2">
          <h1 className="font-gaming text-2xl sm:text-3xl font-bold text-text-primary">
            {t("home.title")}
          </h1>
          <p className="mt-1 text-sm text-text-muted">
            {t("home.subtitle")}
          </p>
        </section>

        {sources.length === 0 ? (
          <p className="mt-8 text-text-muted">
            {t("home.noStreams")}
          </p>
        ) : (
          <section
            className="mt-8 grid gap-6 sm:gap-8 sm:grid-cols-2 xl:grid-cols-3"
            aria-label="Stream cards"
          >
            {[...sources]
              .sort((a, b) => {
                if (!userCoords) return 0;
                const coordsA = parseCoords(a.location);
                const coordsB = parseCoords(b.location);
                if (!coordsA && !coordsB) return 0;
                if (!coordsA) return 1;
                if (!coordsB) return -1;
                return haversineKm(userCoords, coordsA) - haversineKm(userCoords, coordsB);
              })
              .map((s, index) => (
                <SourceCard
                  key={s.id}
                  source={s}
                  count={counts[s.id]}
                  previewTick={previewTick}
                  staggerIndex={index}
                />
              ))}
          </section>
        )}

        <section
          className="mt-20 pt-10 border-t border-border-dark"
          aria-label={t("home.suggestTitle")}
        >
          <h2 className="font-gaming text-lg font-medium text-text-secondary mb-4">
            {t("home.suggestTitle")}
          </h2>
          <p className="text-sm text-text-muted mb-6 max-w-xl">
            {t("home.suggestDesc")}
          </p>
          <SuggestForm onSuccess={refreshSources} hasUser={!!user} />
        </section>
      </main>
    </div>
  );
}
