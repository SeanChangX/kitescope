export type HistoryRow = { source_id: number; count: number; recorded_at: string };

export type ChartInterval = "minute" | "5min" | "10min" | "30min" | "hour" | "day";

export function bucketKey(iso: string, interval: ChartInterval): string {
  const d = new Date(iso);
  if (interval === "day") return iso.slice(0, 10);
  if (interval === "hour") return iso.slice(0, 13);
  if (interval === "minute") return iso.slice(0, 16);
  const min = d.getUTCMinutes();
  const step = interval === "5min" ? 5 : interval === "10min" ? 10 : 30;
  d.setUTCMinutes(Math.floor(min / step) * step, 0, 0);
  return d.toISOString().slice(0, 16);
}

export function bucketLabelLocal(key: string, interval: ChartInterval): string {
  const iso = key.length === 10 ? key + "T12:00:00.000Z" : key.length === 13 ? key + ":00:00.000Z" : key + ":00.000Z";
  const d = new Date(iso);
  return interval === "day"
    ? d.toLocaleDateString(undefined, { month: "2-digit", day: "2-digit", year: "2-digit" })
    : d.toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function floorBucketStart(date: Date, interval: ChartInterval): Date {
  const d = new Date(date);
  d.setUTCSeconds(0, 0);
  if (interval === "day") {
    d.setUTCHours(0, 0, 0, 0);
    return d;
  }
  if (interval === "hour") {
    d.setUTCMinutes(0, 0, 0);
    return d;
  }
  if (interval === "minute") {
    return d;
  }
  const step = interval === "5min" ? 5 : interval === "10min" ? 10 : 30;
  d.setUTCMinutes(Math.floor(d.getUTCMinutes() / step) * step, 0, 0);
  return d;
}

function nextBucket(date: Date, interval: ChartInterval): Date {
  const d = new Date(date);
  if (interval === "day") {
    d.setUTCDate(d.getUTCDate() + 1);
    return d;
  }
  if (interval === "hour") {
    d.setUTCHours(d.getUTCHours() + 1);
    return d;
  }
  if (interval === "minute") {
    d.setUTCMinutes(d.getUTCMinutes() + 1);
    return d;
  }
  const step = interval === "5min" ? 5 : interval === "10min" ? 10 : 30;
  d.setUTCMinutes(d.getUTCMinutes() + step);
  return d;
}

export function buildFilledChartData(
  rows: HistoryRow[],
  interval: ChartInterval,
  from: Date,
  to: Date,
  maxPoints?: number
): { time: string; count: number }[] {
  const byBucket = new Map<string, { sum: number; n: number }>();
  for (const r of rows) {
    const key = bucketKey(new Date(r.recorded_at).toISOString(), interval);
    const cur = byBucket.get(key) ?? { sum: 0, n: 0 };
    cur.sum += r.count;
    cur.n += 1;
    byBucket.set(key, cur);
  }

  const start = floorBucketStart(from, interval);
  const end = floorBucketStart(to, interval);
  const result: { time: string; count: number }[] = [];

  for (let cursor = start; cursor <= end; cursor = nextBucket(cursor, interval)) {
    const key = bucketKey(cursor.toISOString(), interval);
    const bucket = byBucket.get(key);
    result.push({
      time: bucketLabelLocal(key, interval),
      count: bucket && bucket.n ? Math.round((bucket.sum / bucket.n) * 10) / 10 : 0,
    });
  }

  return maxPoints && result.length > maxPoints ? result.slice(-maxPoints) : result;
}
