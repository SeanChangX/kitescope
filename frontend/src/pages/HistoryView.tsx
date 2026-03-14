import { useEffect, useState, type CSSProperties } from "react";
import type { TooltipProps } from "recharts";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { buildFilledChartData, type HistoryRow } from "../lib/historyChart";

const API = "/api";

type RangeKey = "7" | "30";

const RANGES: { key: RangeKey; label: string; days: number; bucket: "hour" | "day" }[] = [
  { key: "7", label: "Last 7 days (hourly)", days: 7, bucket: "hour" },
  { key: "30", label: "Last 30 days (daily)", days: 30, bucket: "day" },
];

const CHART_TOOLTIP_STYLE: CSSProperties = {
  margin: 0,
  padding: "6px 10px",
  fontSize: 12,
  borderRadius: 8,
  backgroundColor: "rgba(10, 10, 10, 0.96)",
  border: "none",
  textAlign: "left",
  boxShadow: "0 8px 24px rgba(0, 0, 0, 0.65)",
};

function HistoryTooltipContent(props: TooltipProps<number, string>) {
  const { active, payload, label } = props;
  if (!active || !payload?.length || payload[0].value == null) return null;
  return (
    <div style={CHART_TOOLTIP_STYLE}>
      <div style={{ color: "rgba(248, 250, 252, 0.9)" }}>{label}</div>
      <div style={{ color: "rgb(248, 250, 252)" }}>kites: {payload[0].value}</div>
    </div>
  );
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

  const from = new Date();
  from.setDate(from.getDate() - rangeConfig.days);
  const maxPoints = rangeConfig.bucket === "hour" ? rangeConfig.days * 24 + 1 : rangeConfig.days + 1;
  const sliced = buildFilledChartData(data, rangeConfig.bucket, from, new Date(), maxPoints);

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
                content={<HistoryTooltipContent />}
                cursor={{ fill: "transparent" }}
                wrapperStyle={{ border: "none", outline: "none" }}
              />
              <Line type="monotone" dataKey="count" stroke="#ff0050" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
