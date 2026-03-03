import { useEffect, useState } from "react";
import SuggestForm from "./SuggestForm";
import SourceCard from "../components/SourceCard";
import { useI18n } from "../lib/i18n";

const API = "/api";

/** Refresh interval for both preview images and counts (same tick so they update together). */
const REFRESH_INTERVAL_MS = Number(import.meta.env.VITE_PREVIEW_INTERVAL_MS) || 2000;

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

type Source = { id: number; name: string; type: string; location: string; location_display?: string; enabled: boolean; url?: string; direct_embed?: boolean };
type Counts = Record<number, { count: number; recorded_at: string }>;

export default function GuestView() {
  const { t } = useI18n();
  const [sources, setSources] = useState<Source[]>([]);
  const [counts, setCounts] = useState<Counts>({});
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
    const t = setInterval(() => {
      setPreviewTick((n) => n + 1);
      fetch(`${API}/counts`)
        .then((r) => r.json())
        .then(setCounts)
        .catch(console.error);
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(t);
  }, []);

  return (
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
          <SuggestForm onSuccess={refreshSources} />
        </section>
    </main>
  );
}
