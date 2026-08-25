export type EvidenceItem = {
  id: string;
  source: string;
  reference: string;
  excerpt: string;
  translation?: string | null;
  url?: string | null;
  score?: number | null;
};

export type Claim = {
  id: string;
  ordinal: number;
  text: string;
  category: string;
  quoted_gurbani?: string | null;
  verdict?: string | null;
  confidence?: number | null;
  summary?: string | null;
  correction?: string | null;
  evidence?: EvidenceItem[] | null;
};

export type Case = {
  id: string;
  status: string;
  source_url?: string | null;
  submitted_text?: string | null;
  language_hint?: string | null;
  media_filename?: string | null;
  extracted_text?: string | null;
  page_title?: string | null;
  overall_verdict?: string | null;
  overall_confidence?: number | null;
  overall_summary?: string | null;
  error_message?: string | null;
  pipeline_log?: unknown[] | null;
  review_status?: string | null;
  reviewer_notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  claims: Claim[];
};

export function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

export async function fetchCase(id: string): Promise<Case> {
  const res = await fetch(`${apiBase()}/api/cases/${id}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Case not found");
  }
  return res.json();
}

export async function submitCase(form: FormData): Promise<Case> {
  const res = await fetch(`${apiBase()}/api/submit`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || "Submit failed");
  }
  return res.json();
}
