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
import { buildFilledChartData, type ChartInterval, type HistoryRow } from "../lib/historyChart";

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

/** Max data points to show on chart, derived from guestHistoryHours and interval. */
function maxChartPoints(interval: string, guestHistoryHours: number): number {
  const hours = Math.max(1, guestHistoryHours);
  if (interval === "minute") return Math.min(1440, Math.ceil(hours * 60));
  if (interval === "5min") return Math.min(576, Math.ceil(hours * 12));
  if (interval === "10min") return Math.min(288, Math.ceil(hours * 6));
  if (interval === "30min") return Math.min(96, Math.ceil(hours * 2));
  if (interval === "hour") return Math.min(720, Math.ceil(hours));
  if (interval === "day") return Math.min(365, Math.ceil(hours / 24));
  return Math.min(720, Math.ceil(hours));
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

type Props = {
  source: Source;
  count: Count;
  previewTick: number;
  staggerIndex?: number;
  guestHistoryHours?: number;
  guestHistoryInterval?: string;
};

export default function SourceCard({
  source,
  count,
  previewTick,
  staggerIndex = 0,
  guestHistoryHours = 24,
  guestHistoryInterval = "hour",
}: Props) {
  const { t } = useI18n();
  const directEmbed = source.direct_embed === true;
  const useEmbeddedUrl = directEmbed && isDirectEmbeddableUrl(source.url) && !!source.url;
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [weatherText, setWeatherText] = useState("");
  const [weatherDetail, setWeatherDetail] = useState<WeatherDetail | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState<number | null>(null);
  const [chartAnimationDone, setChartAnimationDone] = useState(false);
  const blobUrlRef = useRef<string | null>(null);
  const previewCancelledRef = useRef(false);
  const historyLastRecordedRef = useRef<string | null>(null);
  const historyKeyRef = useRef<string>("");

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
    const key = `${source.id}-${guestHistoryHours}-${guestHistoryInterval}`;
    const windowStart = new Date();
    windowStart.setHours(windowStart.getHours() - guestHistoryHours);
    const isFullFetch = historyKeyRef.current !== key;
    if (isFullFetch) {
      historyKeyRef.current = key;
      historyLastRecordedRef.current = null;
    }
    const from = historyLastRecordedRef.current
      ? new Date(historyLastRecordedRef.current)
      : windowStart;
    fetch(
      `${API}/history?source_id=${source.id}&from=${from.toISOString()}&interval=${encodeURIComponent(guestHistoryInterval)}`
    )
      .then((r) => r.json())
      .then((rows: HistoryRow[]) => {
        if (isFullFetch || rows.length === 0) {
          setHistory(rows);
          if (rows.length > 0) {
            const last = rows.reduce((a, b) => (a.recorded_at > b.recorded_at ? a : b));
            historyLastRecordedRef.current = last.recorded_at;
          }
          return;
        }
        setHistory((prev) => {
          const cut = windowStart.toISOString();
          const seen = new Set<string>();
          const merged = [...prev, ...rows]
            .filter((r) => r.recorded_at >= cut)
            .sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));
          const deduped = merged.filter((r) => {
            if (seen.has(r.recorded_at)) return false;
            seen.add(r.recorded_at);
            return true;
          });
          if (deduped.length > 0) {
            historyLastRecordedRef.current = deduped[deduped.length - 1].recorded_at;
          }
          return deduped;
        });
      })
      .catch(() => setHistory([]));
  }, [source.id, guestHistoryHours, guestHistoryInterval, previewTick]);

  useEffect(() => {
    if (source.id !== undefined) setChartAnimationDone(false);
  }, [source.id, guestHistoryHours, guestHistoryInterval]);

  useEffect(() => {
    if (history.length === 0) {
      setChartAnimationDone(false);
      return;
    }
    if (chartAnimationDone) return;
    const t = setTimeout(() => setChartAnimationDone(true), 5000);
    return () => clearTimeout(t);
  }, [history.length, chartAnimationDone]);

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

  const interval = guestHistoryInterval as ChartInterval;
  const maxPoints = maxChartPoints(interval, guestHistoryHours);
  const chartStart = new Date();
  chartStart.setHours(chartStart.getHours() - guestHistoryHours);
  const chartData = buildFilledChartData(history, interval, chartStart, new Date(), maxPoints);

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
            <p className="text-text-muted text-sm">{t("card.noDataInRange")}</p>
          ) : (
            <div className={`chart-line-draw h-full w-full${chartAnimationDone ? " chart-line-draw-done" : ""}`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#525252" strokeOpacity={0.25} vertical={false} />
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
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
