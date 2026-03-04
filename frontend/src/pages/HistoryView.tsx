import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const API = "/api";

type HistoryRow = { source_id: number; count: number; recorded_at: string };

type RangeKey = "7" | "30";

const RANGES: { key: RangeKey; label: string; days: number; bucket: "hour" | "day" }[] = [
  { key: "7", label: "Last 7 days (hourly)", days: 7, bucket: "hour" },
  { key: "30", label: "Last 30 days (daily)", days: 30, bucket: "day" },
];

function bucketKey(iso: string, bucket: "hour" | "day"): string {
  if (bucket === "day") return iso.slice(0, 10);
  return iso.slice(0, 13);
}

/** Format bucket key (UTC) as local date/time for display. */
function bucketLabelLocal(key: string, bucket: "hour" | "day"): string {
  const iso = bucket === "day" ? key + "T12:00:00.000Z" : key + ":00:00.000Z";
  const d = new Date(iso);
  return bucket === "day"
    ? d.toLocaleDateString(undefined, { month: "2-digit", day: "2-digit", year: "2-digit" })
    : d.toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function HistoryView() {
  const [data, setData] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<RangeKey>("7");

  const rangeConfig = RANGES.find((r) => r.key === range) ?? RANGES[0];

  useEffect(() => {
    const config = RANGES.find((r) => r.key === range) ?? RANGES[0];
    const from = new Date();
    from.setDate(from.getDate() - config.days);
    setLoading(true);
    fetch(`${API}/history?from=${from.toISOString()}&interval=${config.bucket}`)
      .then((r) => r.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [range]);

  if (loading) return <p className="text-text-muted">Loading history...</p>;

  const byBucket = new Map<string, { sum: number; n: number }>();
  for (const r of data) {
    const key = bucketKey(new Date(r.recorded_at).toISOString(), rangeConfig.bucket);
    const cur = byBucket.get(key) ?? { sum: 0, n: 0 };
    cur.sum += r.count;
    cur.n += 1;
    byBucket.set(key, cur);
  }
  const chartData = Array.from(byBucket.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([key, v]) => ({
      time: bucketLabelLocal(key, rangeConfig.bucket),
      count: v.n ? Math.round((v.sum / v.n) * 10) / 10 : 0,
    }));
  const maxPoints = rangeConfig.bucket === "hour" ? 48 : 31;
  const sliced = chartData.slice(-maxPoints);

  return (
    <div className="ks-card">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="font-gaming font-medium text-text-primary">History</h3>
        <select
          value={range}
          onChange={(e) => setRange(e.target.value as RangeKey)}
          className="ks-input w-auto py-1.5 text-sm"
        >
          {RANGES.map((r) => (
            <option key={r.key} value={r.key}>
              {r.label}
            </option>
          ))}
        </select>
      </div>
      {sliced.length === 0 ? (
        <p className="text-text-muted">No history yet.</p>
      ) : (
        <div className="h-64 chart-line-draw">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sliced}>
              <CartesianGrid stroke="#525252" strokeOpacity={0.25} vertical={false} />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#cccccc" }} />
              <YAxis tick={{ fontSize: 10, fill: "#cccccc" }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1f1f1f", border: "1px solid #374151", borderRadius: "8px" }}
                labelStyle={{ color: "#cccccc" }}
              />
              <Line type="monotone" dataKey="count" stroke="#ff0050" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
