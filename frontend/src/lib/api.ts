// Typed client for the Proteus read-only local API (api/server.py).
// Every value returned here traces back to results/results.pkl or proteus/data_full.py
// via the FastAPI layer. Endpoints that lack real backend data resolve to
// `{ available: false, reason }` — callers must render an explicit empty state for those,
// never fabricate numbers to fill the shape.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type NotAvailable = { available: false; reason: string };

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json();
}

export type ExperimentLatest =
  | ({ available: true } & {
      data_source: string;
      class_names: string[];
      class_distribution: Record<string, number>;
      n_features: number;
      rare_classes: string[];
      n_timesteps: number;
      drift_schedule: number[];
      gan_degraded: boolean;
      gan_error: string | null;
      runtime_seconds: number;
      single_seed: boolean;
      conditions: string[];
    })
  | NotAvailable;

export type ClassReport = Record<
  string,
  { precision: number; recall: number; "f1-score": number; support: number }
> & { accuracy?: number };

export type ConditionSeries = { macro_f1: number[]; per_class_f1: number[][] };

export type ExperimentConditions =
  | ({ available: true } & {
      class_names: string[];
      drift_schedule: number[];
      retrain_timesteps: number[];
      conditions: Record<string, ConditionSeries>;
    })
  | NotAvailable;

export type FinalReports =
  | ({ available: true } & { class_names: string[]; final_reports: Record<string, ClassReport> })
  | NotAvailable;

export type DriftEvent = {
  timestep: number;
  fired: boolean;
  statistic: number;
  p_value: number;
  alpha: number;
};

export type RetrainEvent =
  | { timestep: number; f1_before: number; f1_after: number; n_admitted: number }
  | { timestep: number; error: string };

export type DriftEvents =
  | ({ available: true } & {
      method: string;
      events: DriftEvent[];
      drift_schedule: number[];
      retrain_events: RetrainEvent[];
    })
  | NotAvailable;

export type GanLoss =
  | ({ available: true } & {
      degraded: boolean;
      error: string | null;
      rare_classes: string[];
      loss_log: { step: number; g_loss: number; d_loss: number }[];
    })
  | NotAvailable;

export type GateEntry = { step: number; mmd_score: number; admitted: boolean; n_samples: number };

export type GateLog =
  | ({ available: true } & {
      method: string;
      threshold: number;
      static_gate_log: GateEntry[];
      closed_loop_gate_log: GateEntry[];
    })
  | NotAvailable;

export type AdaptationEvents = ({ available: true } & { retrain_events: RetrainEvent[] }) | NotAvailable;

export type MetricsFinal =
  | ({ available: true } & {
      class_names: string[];
      report: ClassReport;
      confusion_matrix: number[][];
      macro_f1: number;
    })
  | NotAvailable;

export type DatasetSummary =
  | ({ available: true } & {
      generated_at: string;
      datasets: {
        name: string;
        available: boolean;
        error?: string;
        data_source?: string;
        n_rows_total?: number;
        n_features?: number;
        class_names?: string[];
        class_distribution?: Record<string, number>;
        split_sizes?: { train: number; val: number; test: number };
        feature_columns?: string[];
        schema?: { label_column: string; categorical_columns: string[]; identifier_columns: string[] };
        load_seconds?: number;
      }[];
    })
  | NotAvailable;

export type ModelsInfo = {
  demo_model: {
    name: string;
    trained_on: string;
    n_features: number;
    class_names: string[];
    conditions_trained: string[];
  } | null;
  full_scale_model: NotAvailable;
  insdn_model: NotAvailable;
};

export const api = {
  health: () => get<{ status: string; results_available: boolean; server_time: string }>("/api/health"),
  experimentsLatest: () => get<ExperimentLatest>("/api/experiments/latest"),
  experimentsConditions: () => get<ExperimentConditions>("/api/experiments/conditions"),
  experimentsFinalReports: () => get<FinalReports>("/api/experiments/final-reports"),
  driftEvents: () => get<DriftEvents>("/api/drift/events"),
  ganLoss: () => get<GanLoss>("/api/gan/loss"),
  gateLog: () => get<GateLog>("/api/gate/log"),
  adaptationEvents: () => get<AdaptationEvents>("/api/adaptation/events"),
  metricsFinal: () => get<MetricsFinal>("/api/metrics/final"),
  topology: () => get<NotAvailable>("/api/topology"),
  datasetsSummary: () => get<DatasetSummary>("/api/datasets/summary"),
  models: () => get<ModelsInfo>("/api/models"),
};
