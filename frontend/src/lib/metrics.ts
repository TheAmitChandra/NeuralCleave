/**
 * Parsing helpers for GET /api/v1/metrics/snapshot.
 *
 * The gateway's MetricsRegistry.snapshot() returns a nested shape, not flat
 * numbers — every metric carries its type, description, and a `values` map
 * keyed by a sorted "label=value,label2=value2" string (empty string for
 * unlabelled metrics):
 *
 *   {
 *     "generation_requests_total": {
 *       "type": "counter",
 *       "description": "...",
 *       "values": { "model=gemini-2.0-flash": 3 }
 *     },
 *     "generation_latency_ms": {
 *       "type": "histogram",
 *       "values": { "model=gemini-2.0-flash": { sum: 825, count: 3, buckets: [...] } }
 *     }
 *   }
 */

export interface HistogramValue {
  sum: number;
  count: number;
  buckets: [number, number][];
}

export interface MetricEntry {
  type: "counter" | "gauge" | "histogram";
  description: string;
  values: Record<string, number | HistogramValue>;
}

export type MetricsSnapshot = Record<string, MetricEntry>;

function parseLabelKey(key: string): Record<string, string> {
  if (!key) return {};
  const labels: Record<string, string> = {};
  for (const pair of key.split(",")) {
    const [k, v] = pair.split("=");
    if (k) labels[k] = v ?? "";
  }
  return labels;
}

/** Sum a counter or gauge's values across every label combination. */
export function sumMetric(snapshot: MetricsSnapshot | undefined, name: string): number {
  const metric = snapshot?.[name];
  if (!metric || metric.type === "histogram") return 0;
  let total = 0;
  for (const v of Object.values(metric.values)) {
    if (typeof v === "number") total += v;
  }
  return total;
}

/** Average of a histogram's observations across every label combination. */
export function avgHistogram(
  snapshot: MetricsSnapshot | undefined,
  name: string
): number | null {
  const metric = snapshot?.[name];
  if (!metric || metric.type !== "histogram") return null;
  let sum = 0;
  let count = 0;
  for (const v of Object.values(metric.values)) {
    if (typeof v === "object" && v !== null) {
      sum += v.sum;
      count += v.count;
    }
  }
  return count > 0 ? sum / count : null;
}

export interface TokenUsageRow {
  model: string;
  input: number;
  output: number;
}

/**
 * Breaks tokens_total (labelled by model + direction) into one row per
 * model, sorted by total tokens descending.
 */
export function tokensByModel(snapshot: MetricsSnapshot | undefined): TokenUsageRow[] {
  const metric = snapshot?.["tokens_total"];
  if (!metric || metric.type !== "counter") return [];

  const byModel: Record<string, TokenUsageRow> = {};
  for (const [labelKey, value] of Object.entries(metric.values)) {
    if (typeof value !== "number") continue;
    const labels = parseLabelKey(labelKey);
    const model = labels.model ?? "unknown";
    byModel[model] ??= { model, input: 0, output: 0 };
    if (labels.direction === "input") byModel[model].input += value;
    else if (labels.direction === "output") byModel[model].output += value;
  }

  return Object.values(byModel).sort(
    (a, b) => b.input + b.output - (a.input + a.output)
  );
}
