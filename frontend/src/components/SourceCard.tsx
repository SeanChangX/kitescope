import { useEffect, useRef, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useI18n } from "../lib/i18n";

const API = "/api";

const ICON_SIZE = 14;

const IconTemp = () => (
  <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden>
    <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z" />
  </svg>
);

const IconWind = () => (
  <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden>
    <path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2" />
  </svg>
);

const IconRecognitionDisabled = () => (
  <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden>
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
);

const IconCondition = ({ desc }: { desc: string }) => {
  const d = (desc || "").toLowerCase();
  if (d === "clear") return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden>
      <circle cx="12" cy="12" r="5" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  );
  if (d === "rain" || d === "storm") return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden>
      <path d="M18 10a4 4 0 0 0-8 0c0 1.1.9 2 2 2h4a2 2 0 0 1 2 2v2H6a4 4 0 0 1 0-8 4 4 0 0 0 0-8" /><path d="M8 18v4M12 18v4M16 18v4" />
    </svg>
  );
  if (d === "snow" || d === "fog") return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden>
      <path d="M18 10a4 4 0 0 0-8 0 4 4 0 0 0 0 8h8a4 4 0 0 0 0-8" />
    </svg>
  );
  return (
    <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden>
      <path d="M18 10a4 4 0 0 0-8 0 4 4 0 0 0 0 8h8a4 4 0 0 0 0-8" />
    </svg>
  );
};

type HistoryRow = { source_id: number; count: number; recorded_at: string };

function bucketKey(iso: string): string {
  return iso.slice(0, 13);
}

/** Format UTC hour key (e.g. "2026-02-17T16") as local date/time for chart display. */
function bucketLabelLocal(key: string): string {
  const d = new Date(key + ":00:00.000Z");
  return d.toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** Display kite count: at most one decimal, no long float. */
function formatKiteCount(n: number): string {
  const r = Math.round(n * 10) / 10;
  return r % 1 === 0 ? String(Math.round(r)) : r.toFixed(1);
}

type Source = {
  id: number;
  name: string;
  type: string;
  location: string;
  location_display?: string;
  enabled: boolean;
  url?: string;
  direct_embed?: boolean;
};
type Count = { count: number; recorded_at: string } | undefined;

type WeatherDetail = {
  temp_c?: number;
  weather_desc?: string;
  wind_speed_10m_kmh?: number;
  wind_direction_10m?: string | null;
  wind_speed_80m_kmh?: number;
  wind_direction_80m?: string | null;
};

export function isDirectEmbeddableUrl(url: string | undefined): boolean {
  if (!url) return false;
  const u = url.toLowerCase();
  return u.indexOf("youtube.com") === -1 && u.indexOf("youtu.be") === -1;
}

/** Delay between starting each card's preview request (ms). From env VITE_PREVIEW_STAGGER_MS (e.g. in docker-compose). */
const PREVIEW_STAGGER_MS = Number(import.meta.env.VITE_PREVIEW_STAGGER_MS) || 300;

type Props = { source: Source; count: Count; previewTick: number; staggerIndex?: number };

export default function SourceCard({ source, count, previewTick, staggerIndex = 0 }: Props) {
  const { t } = useI18n();
  const directEmbed = source.direct_embed === true;
  const useEmbeddedUrl = directEmbed && isDirectEmbeddableUrl(source.url) && !!source.url;
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [weatherText, setWeatherText] = useState("");
  const [weatherDetail, setWeatherDetail] = useState<WeatherDetail | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState<number | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  const previewCancelledRef = useRef(false);

  // Fetch proxy preview when not using embedded image URL. Stagger by staggerIndex so cards load one by one.
  useEffect(() => {
    if (useEmbeddedUrl) return;
    previewCancelledRef.current = false;
    const delayMs = staggerIndex * PREVIEW_STAGGER_MS;
    const overlay = directEmbed ? 0 : 1;
    const url = `${API}/sources/${source.id}/preview?overlay=${overlay}&t=${previewTick}`;
    const timeoutId = setTimeout(() => {
      fetch(url)
        .then((res) => {
          if (previewCancelledRef.current) return null;
          if (!res.ok) throw new Error(String(res.status));
          const c = res.headers.get("X-Detection-Count");
          if (c != null) setFrameCount(parseInt(c, 10));
          return res.blob();
        })
        .then((blob) => {
          if (blob == null || previewCancelledRef.current) return;
          setPreviewError(false);
          setPreviewBlobUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            const u = URL.createObjectURL(blob);
            blobUrlRef.current = u;
            return u;
          });
        })
        .catch(() => {
          if (!previewCancelledRef.current) setPreviewError(true);
        });
    }, delayMs);
    return () => {
      clearTimeout(timeoutId);
      previewCancelledRef.current = true;
    };
  }, [source.id, useEmbeddedUrl, directEmbed, previewTick, staggerIndex]);

  useEffect(() => {
    if (useEmbeddedUrl) {
      setFrameCount(null);
      setPreviewBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        blobUrlRef.current = null;
        return null;
      });
    }
  }, [useEmbeddedUrl]);

  useEffect(() => {
    return () => {
      if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current);
    };
  }, []);

  useEffect(() => {
    const from = new Date();
    from.setDate(from.getDate() - 7);
    fetch(
      `${API}/history?source_id=${source.id}&from=${from.toISOString()}&interval=hour`
    )
      .then((r) => r.json())
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [source.id]);

  useEffect(() => {
    if (!source.location?.trim()) {
      setWeatherText("");
      setWeatherDetail(null);
      return;
    }
    fetch(`${API}/weather?location=${encodeURIComponent(source.location.trim())}`)
      .then((r) => r.json())
      .then((d) => {
        setWeatherText((d.text as string) || "");
        setWeatherDetail((d.detail as WeatherDetail) || null);
      })
      .catch(() => {
        setWeatherText("");
        setWeatherDetail(null);
      });
  }, [source.location]);

  const byBucket = new Map<string, { sum: number; n: number }>();
  for (const r of history) {
    const key = bucketKey(new Date(r.recorded_at).toISOString());
    const cur = byBucket.get(key) ?? { sum: 0, n: 0 };
    cur.sum += r.count;
    cur.n += 1;
    byBucket.set(key, cur);
  }
  const chartData = Array.from(byBucket.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .slice(-24)
    .map(([key, v]) => ({
      time: bucketLabelLocal(key),
      count: v.n ? Math.round((v.sum / v.n) * 10) / 10 : 0,
    }));

  return (
    <article className="ks-card overflow-hidden p-0 flex flex-col">
      <div className="aspect-video w-full bg-bg-tertiary shrink-0 relative flex items-center justify-center overflow-hidden">
        {previewError ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-bg-tertiary p-4 text-center">
            <span className="text-text-muted text-sm font-medium">{t("card.signalInterrupted")}</span>
            <span className="text-text-muted text-xs">{t("card.previewUnavailable")}</span>
          </div>
        ) : useEmbeddedUrl ? (
          <img
            src={`${source.url}${source.url!.includes("?") ? "&" : "?"}t=${previewTick}`}
            alt={`Live ${source.name || `Source ${source.id}`}`}
            className="w-full h-full object-contain"
            onError={() => setPreviewError(true)}
          />
        ) : previewBlobUrl ? (
          <img
            src={previewBlobUrl}
            alt={`Live ${source.name || `Source ${source.id}`}`}
            className="w-full h-full object-contain"
            onError={() => setPreviewError(true)}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-bg-tertiary">
            <span className="text-text-muted text-sm">{t("card.loadingPreview")}</span>
          </div>
        )}
      </div>
      <div className="p-4 flex flex-col gap-3 flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="font-gaming font-medium text-text-primary truncate">
            {source.name || `Source ${source.id}`}
          </h3>
          {directEmbed ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/50 bg-amber-500/10 px-2.5 py-1 text-sm font-medium text-amber-400 shrink-0">
              <IconRecognitionDisabled />
              {t("card.recognitionDisabled")}
            </span>
          ) : (
            <span className="text-lg font-semibold text-primary shrink-0">
              {frameCount != null ? `${formatKiteCount(frameCount)} kites` : count != null ? `${formatKiteCount(count.count)} kites` : "—"}
            </span>
          )}
        </div>
        <div className="flex flex-col gap-1.5 text-sm text-text-muted">
          {(source.location_display ?? source.location) && (
            <span className="truncate" title={source.location_display ?? source.location}>
              {source.location_display ?? source.location}
            </span>
          )}
          {weatherDetail && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {weatherDetail.temp_c != null && (
                <span className="inline-flex items-center gap-1.5">
                  <IconTemp />
                  <span>{t("card.temp")}: {weatherDetail.temp_c}C</span>
                </span>
              )}
              {(weatherDetail.wind_speed_10m_kmh != null || weatherDetail.wind_direction_10m) && (
                <span className="inline-flex items-center gap-1.5">
                  <IconWind />
                  <span>
                    {t("card.wind10m")}: {[weatherDetail.wind_direction_10m, weatherDetail.wind_speed_10m_kmh != null && `${weatherDetail.wind_speed_10m_kmh} km/h`].filter(Boolean).join(" ")}
                  </span>
                </span>
              )}
              {(weatherDetail.wind_speed_80m_kmh != null || weatherDetail.wind_direction_80m) && (
                <span className="inline-flex items-center gap-1.5">
                  <IconWind />
                  <span>
                    {t("card.wind80m")}: {[weatherDetail.wind_direction_80m, weatherDetail.wind_speed_80m_kmh != null && `${weatherDetail.wind_speed_80m_kmh} km/h`].filter(Boolean).join(" ")}
                  </span>
                </span>
              )}
              {weatherDetail.weather_desc && (
                <span className="inline-flex items-center gap-1.5">
                  <IconCondition desc={weatherDetail.weather_desc} />
                  <span>{t("card.condition")}: {weatherDetail.weather_desc}</span>
                </span>
              )}
            </div>
          )}
          {!weatherDetail && weatherText && <span>{weatherText}</span>}
          {!source.location && !weatherText && !weatherDetail && <span>{source.type}</span>}
        </div>
        <div className="h-24 mt-1">
          {chartData.length === 0 ? (
            <p className="text-text-muted text-sm">No history yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#374151" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 9, fill: "#888888" }}
                  tickFormatter={(v) => v.slice(5)}
                />
                <YAxis
                  width={24}
                  tick={{ fontSize: 9, fill: "#888888" }}
                  tickFormatter={(v) => (Number(v) === v ? String(v) : "")}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1f1f1f",
                    border: "1px solid #374151",
                    borderRadius: "6px",
                    fontSize: "12px",
                  }}
                  formatter={(v: number) => [formatKiteCount(Number(v)), "kites"]}
                  labelFormatter={(label: string) => label}
                />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#ff0050"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </article>
  );
}
