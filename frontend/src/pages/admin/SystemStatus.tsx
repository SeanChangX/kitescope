import { useEffect, useState } from "react";
import type { TooltipProps } from "recharts";
import {
  BarChart,
  Bar,
  Cell,
  ResponsiveContainer,
  Tooltip,
  YAxis,
  XAxis,
} from "recharts";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

const TOOLTIP_STYLE: React.CSSProperties = {
  margin: 0,
  padding: "6px 10px",
  fontSize: 12,
  borderRadius: 8,
  backgroundColor: "rgba(10, 10, 10, 0.96)",
  border: "none",
  textAlign: "left",
  boxShadow: "0 8px 24px rgba(0, 0, 0, 0.65)",
};

const LOAD_GREEN = "#22c55e";
const LOAD_YELLOW = "#eab308";
const LOAD_RED = "#ef4444";
const LOAD_EMPTY = "rgba(148, 163, 184, 0.25)";

function getBarColor(metric: "inference" | "cpu" | "memory", value: number | null): string {
  if (value == null) return LOAD_EMPTY;
  if (metric === "inference") {
    return value < 60 ? LOAD_GREEN : value < 120 ? LOAD_YELLOW : LOAD_RED;
  }
  return value < 60 ? LOAD_GREEN : value < 85 ? LOAD_YELLOW : LOAD_RED;
}

const BAR_ROLL_DURATION_MS = 220;
const BAR_ROLL_STAGGER_MS = 12;

function renderBarShape(props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  fill?: string;
  index?: number;
  radius?: number | number[];
}) {
  const { x = 0, y = 0, width = 0, height = 0, fill, index = 0 } = props;
  const delaySec = (index * BAR_ROLL_STAGGER_MS) / 1000;
  const durSec = BAR_ROLL_DURATION_MS / 1000;
  const bottomY = y + height;
  return (
    <rect x={x} y={bottomY} width={width} height={0} fill={fill} rx={1} ry={1}>
      <animate
        attributeName="y"
        from={bottomY}
        to={y}
        dur={`${durSec}s`}
        begin={`${delaySec}s`}
        fill="freeze"
        calcMode="spline"
        keySplines="0 0 0.58 1"
        keyTimes="0;1"
      />
      <animate
        attributeName="height"
        from={0}
        to={height}
        dur={`${durSec}s`}
        begin={`${delaySec}s`}
        fill="freeze"
        calcMode="spline"
        keySplines="0 0 0.58 1"
        keyTimes="0;1"
      />
    </rect>
  );
}

function makeChartTooltipContent(unit: string, labelName: string) {
  return function ChartTooltipContent(props: TooltipProps<number, string>) {
    const { active, payload, label } = props;
    if (!active || !payload?.length || payload[0].value == null) return null;
    return (
      <div style={TOOLTIP_STYLE}>
        <div style={{ color: "rgba(248, 250, 252, 0.9)" }}>{label}</div>
        <div style={{ color: "rgb(248, 250, 252)" }}>
          {labelName}: {payload[0].value}
          {unit}
        </div>
      </div>
    );
  };
}

interface VisionConfig {
  model_path?: string;
  model_loaded?: boolean;
  model_exists?: boolean;
  detector_device?: string;
  detect_device_env?: string;
  tpu_detected?: boolean;
  tpu_devices?: Array<{ type?: string; path?: string }>;
  confidence_threshold?: number;
  skip_frames?: number;
  ingestion_concurrency?: number;
  inference_speed_ms?: number | null;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  memory_mb?: number | null;
}

type HistoryPoint = {
  t: number;
  inference_speed_ms?: number | null;
  cpu_percent?: number | null;
  memory_percent?: number | null;
};

interface SystemStatusResponse {
  vision_reachable: boolean;
  vision_error?: string;
  vision: VisionConfig | null;
  history?: HistoryPoint[];
}

const STATUS_REFRESH_INTERVAL_MS = 60_000;
const CHART_SLOTS = 60;

function buildChartData(history: HistoryPoint[]) {
  const filled = history.map((p) => ({
    time: new Date(p.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    inference: p.inference_speed_ms ?? null,
    cpu: p.cpu_percent ?? null,
    memory: p.memory_percent ?? null,
  }));
  const pad = Math.max(0, CHART_SLOTS - filled.length);
  const empty = Array(pad).fill(null).map(() => ({
    time: "",
    inference: null as number | null,
    cpu: null as number | null,
    memory: null as number | null,
  }));
  return [...empty, ...filled];
}

export default function SystemStatus() {
  const { t } = useI18n();
  const [data, setData] = useState<SystemStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    function fetchStatus() {
      authFetch("/api/admin/system/status")
        .then((r) => (r.ok ? r.json() : null))
        .then((d: SystemStatusResponse | null) => {
          if (!cancelled && d) setData(d);
        })
        .catch(() => {
          if (!cancelled) setData(null);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }
    fetchStatus();
    const interval = setInterval(fetchStatus, STATUS_REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (loading) return <p className="text-text-muted">{t("common.loading")}</p>;
  if (!data) return null;

  const v = data.vision;
  const history = data.history ?? [];
  const detectorLabel =
    v?.detector_device === "edgetpu" ? t("admin.detectorEdgetpu") : t("admin.detectorCpu");
  const detectorPillLabel = v?.detector_device === "edgetpu" ? "Coral Edge TPU" : "CPU (ONNX)";

  const chartData = buildChartData(history);
  const hasAnyBars = chartData.some((r) => r.inference != null || r.cpu != null || r.memory != null);

  const currentInference = v?.inference_speed_ms != null && v.inference_speed_ms > 0 ? v.inference_speed_ms : null;
  const currentCpu = v?.cpu_percent != null ? v.cpu_percent : null;
  const currentMemory = v?.memory_percent != null ? v.memory_percent : null;

  return (
    <div className="ks-card min-w-0">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm min-w-0">
        <h3 className="font-gaming font-medium text-text-primary w-full sm:w-auto shrink-0">{t("admin.systemStatus")}</h3>
        <span
          className="inline-flex h-8 items-center gap-2 rounded-full border border-border-dark bg-bg-secondary/70 pl-2 pr-3"
          title={t("admin.visionStatusLabel")}
        >
          <span className="inline-flex items-center rounded-full bg-bg-tertiary/80 px-3 py-0.5 text-xs font-medium leading-none text-text-secondary">
            <span className="mt-px">Vision</span>
          </span>
          <span className="inline-flex items-center gap-1.5 text-xs text-text-secondary">
            <span
              className={`h-2 w-2 shrink-0 rounded-full self-center ${
                data.vision_reachable ? "bg-green-500" : "bg-red-500"
              }`}
              aria-hidden
            />
            <span className="translate-y-[1px] leading-none">{data.vision_reachable
              ? "Online"
              : `Offline${data.vision_error ? ` (${data.vision_error})` : ""}`}</span>
          </span>
        </span>
        {v && (
          <>
            <span
              className="inline-flex h-8 items-center gap-2 rounded-full border border-border-dark bg-bg-secondary/70 pl-2 pr-3"
              title={t("admin.detectorDevice")}
            >
              <span className="inline-flex items-center rounded-full bg-bg-tertiary/80 px-3 py-0.5 text-xs font-medium leading-none text-text-secondary">
                <span className="mt-px">Detector</span>
              </span>
              <span className="inline-flex items-center text-xs text-text-secondary mt-px">
                {detectorPillLabel}
              </span>
            </span>
            {v.model_path && (
              <span
                className="inline-flex h-8 items-center gap-2 rounded-full border border-border-dark bg-bg-secondary/70 pl-2 pr-3"
                title={v.model_path}
              >
                <span className="inline-flex items-center rounded-full bg-bg-tertiary/80 px-3 py-0.5 text-xs font-medium leading-none text-text-secondary">
                  <span className="mt-px">Model</span>
                </span>
                <span className="inline-flex max-w-[10rem] sm:max-w-[12rem] items-center truncate text-xs font-mono text-text-secondary mt-px min-w-0">
                  {v.model_path.split("/").pop()}
                </span>
              </span>
            )}
          </>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-3">
        <div className="min-w-0 rounded-lg border border-border-dark bg-bg-tertiary/50 p-4 sm:p-3">
          <p className="mb-1 text-left text-sm font-medium text-text-primary">
            {t("admin.detectorInferenceSpeedTitle")}
          </p>
          <p className="mb-2 text-lg font-medium text-text-primary">
            {currentInference != null ? `${currentInference}${t("admin.ms")}` : "—"}
          </p>
          <div className="h-24 overflow-hidden">
            {!hasAnyBars ? (
              <div className="flex h-full items-center justify-center text-xs text-text-muted">
                {t("admin.systemStatusHistoryCollecting")}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 4, right: 4, left: 2, bottom: 0 }}
                  barCategoryGap={2}
                  barSize={4}
                >
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis width={34} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    content={makeChartTooltipContent(` ${t("admin.ms")}`, t("admin.inferenceSpeed"))}
                    cursor={{ fill: "transparent" }}
                    offset={0}
                    position={{ y: 0 }}
                    wrapperStyle={{ border: "none", outline: "none" }}
                  />
                  <Bar
                    dataKey="inference"
                    radius={[1, 1, 0, 0]}
                    isAnimationActive={false}
                    shape={renderBarShape}
                  >
                    {chartData.map((entry, idx) => (
                      <Cell key={idx} fill={getBarColor("inference", entry.inference)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="min-w-0 rounded-lg border border-border-dark bg-bg-tertiary/50 p-4 sm:p-3">
          <p className="mb-1 text-left text-sm font-medium text-text-primary">
            {t("admin.detectorCpuUsageTitle")}
          </p>
          <p className="mb-2 text-lg font-medium text-text-primary">
            {currentCpu != null ? `${currentCpu}%` : "—"}
          </p>
          <div className="h-24 overflow-hidden">
            {!hasAnyBars ? (
              <div className="flex h-full items-center justify-center text-xs text-text-muted">
                {t("admin.systemStatusHistoryCollecting")}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 4, right: 4, left: 2, bottom: 0 }}
                  barCategoryGap={2}
                  barSize={4}
                >
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis width={34} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    content={makeChartTooltipContent("%", t("admin.detectorCpuUsage"))}
                    cursor={{ fill: "transparent" }}
                    offset={0}
                    position={{ y: 0 }}
                    wrapperStyle={{ border: "none", outline: "none" }}
                  />
                  <Bar
                    dataKey="cpu"
                    radius={[1, 1, 0, 0]}
                    isAnimationActive={false}
                    shape={renderBarShape}
                  >
                    {chartData.map((entry, idx) => (
                      <Cell key={idx} fill={getBarColor("cpu", entry.cpu)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="min-w-0 rounded-lg border border-border-dark bg-bg-tertiary/50 p-4 sm:p-3">
          <p className="mb-1 text-left text-sm font-medium text-text-primary">
            {t("admin.detectorMemoryUsageTitle")}
          </p>
          <p className="mb-2 text-lg font-medium text-text-primary">
            {currentMemory != null ? `${currentMemory}%` : "—"}
          </p>
          <div className="h-24 overflow-hidden">
            {!hasAnyBars ? (
              <div className="flex h-full items-center justify-center text-xs text-text-muted">
                {t("admin.systemStatusHistoryCollecting")}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 4, right: 4, left: 2, bottom: 0 }}
                  barCategoryGap={2}
                  barSize={4}
                >
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis width={34} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    content={makeChartTooltipContent("%", t("admin.detectorMemoryUsage"))}
                    cursor={{ fill: "transparent" }}
                    offset={0}
                    position={{ y: 0 }}
                    wrapperStyle={{ border: "none", outline: "none" }}
                  />
                  <Bar
                    dataKey="memory"
                    radius={[1, 1, 0, 0]}
                    isAnimationActive={false}
                    shape={renderBarShape}
                  >
                    {chartData.map((entry, idx) => (
                      <Cell key={idx} fill={getBarColor("memory", entry.memory)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
