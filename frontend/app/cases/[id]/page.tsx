"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Case, fetchCase } from "@/lib/api";
import { VerdictCard } from "@/components/VerdictCard";

const ACTIVE = new Set(["pending", "processing"]);

export default function CasePage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<Case | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function load() {
      try {
        const c = await fetchCase(params.id);
        if (cancelled) return;
        setData(c);
        if (ACTIVE.has(c.status)) {
          timer = setTimeout(load, 1500);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load");
      }
    }

    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [params.id]);

  const step = useMemo(() => {
    if (!data) return 0;
    if (data.status === "pending") return 1;
    if (data.status === "processing") return 2;
    return 3;
  }, [data]);

  if (error) {
    return (
      <section className="section">
        <div className="wrap">
          <h2>Report unavailable</h2>
          <p className="lead">{error}</p>
        </div>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="section">
        <div className="wrap">
          <h2>Loading report…</h2>
        </div>
      </section>
    );
  }

  const processing = ACTIVE.has(data.status);

  return (
    <section className="section">
      <div className="wrap">
        <h2>{processing ? "Processing" : "Verification report"}</h2>
        <p className="lead">
          Case <span className="mono">{data.id}</span>
          {data.page_title ? ` · ${data.page_title}` : ""}
        </p>

        {processing ? (
          <div className="panel progress">
            <div className={`progress-step ${step >= 1 ? "active" : ""}`}>
              <span className="dot" />
              <div>
                <strong>Ingest</strong>
                <div className="muted">URL fetch, text paste, OCR</div>
              </div>
            </div>
            <div className={`progress-step ${step >= 2 ? "active" : ""}`}>
              <span className="dot" />
              <div>
                <strong>Retrieve</strong>
                <div className="muted">BaniDB / GurbaniNow / curated corpus</div>
              </div>
            </div>
            <div className={`progress-step ${step >= 3 ? "active" : ""}`}>
              <span className="dot" />
              <div>
                <strong>Verify</strong>
                <div className="muted">Evidence-grounded verdicts with citations</div>
              </div>
            </div>
          </div>
        ) : null}

        {!processing ? (
          <>
            <div className="panel" style={{ marginBottom: "1rem" }}>
              <div className="verdict-row">
                <span className={`badge ${data.overall_verdict || "unverified"}`}>
                  {(data.overall_verdict || "unknown").replaceAll("_", " ")}
                </span>
                {data.overall_confidence != null ? (
                  <span className="badge">confidence {(data.overall_confidence * 100).toFixed(0)}%</span>
                ) : null}
                <span className="badge">{data.status.replaceAll("_", " ")}</span>
              </div>
              <p style={{ margin: 0 }}>{data.overall_summary || data.error_message}</p>
              {data.source_url ? (
                <p className="muted" style={{ marginBottom: 0 }}>
                  Source: {data.source_url}
                </p>
              ) : null}
            </div>

            <div className="verdict-stack">
              {data.claims.map((claim) => (
                <VerdictCard key={claim.id} claim={claim} />
              ))}
            </div>

            {data.extracted_text ? (
              <details className="panel" style={{ marginTop: "1rem" }}>
                <summary>Extracted text</summary>
                <pre style={{ whiteSpace: "pre-wrap" }}>{data.extracted_text}</pre>
              </details>
            ) : null}
          </>
        ) : null}

        <div className="disclaimer">
          Share carefully. Prefer wording like “this claim appears inaccurate based on retrieved
          sources” — not personal accusations.
        </div>
      </div>
    </section>
  );
}
