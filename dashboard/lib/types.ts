export type Evidence = {
  url?: string;
  date?: string | null;
  strength?: "strong" | "medium" | "weak";
  source_type?: string;
  note?: string;
  checked_in_run?: boolean;
};

export type Brand = {
  _id?: string;
  domain: string;
  name: string;
  website?: string;
  niche?: string;
  sub_niche?: string;
  score?: number;
  saturated?: boolean;
  older_evidence?: boolean;
  sponsor_count?: number;
  creators_90d?: number;
  report_count?: number;
  last_reported?: string | null;
  evidence?: Evidence[];
  evidence_count?: number;
  generated_at?: string;
  updated_at?: string;
};

export type Run = {
  run_id?: number;
  generated_at?: string;
  brands_found?: number;
  total_brands?: number;
  duplicate_rate?: number;
  re_reported?: number;
  youtube_units_used?: number;
  web_calls_used?: number;
  brands_per_niche?: Record<string, number>;
  created_at?: string;
};