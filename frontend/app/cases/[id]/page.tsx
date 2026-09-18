"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Case, fetchCase } from "@/lib/api";
import { VerdictCard } from "@/components/VerdictCard";

const ACTIVE = new Set(["pending", "processing"]);

const OVERALL_LABEL: Record<string, string> = {
  true: "Consistent with the sources",
  false: "Not supported by the sources",
  misleading: "Misleading",
  unverified: "Could not be verified",
  not_checkable: "No checkable claims found",
};

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
        <div className="wrap narrow">
          <p className="eyebrow">Report</p>
          <h2>We couldn’t find that report</h2>
          <p className="lead">{error}</p>
          <Link className="btn btn-primary" href="/submit">
            Check a post
          </Link>
        </div>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="section">
        <div className="wrap narrow">
          <p className="eyebrow">Report</p>
          <h2>Opening your report…</h2>
        </div>
      </section>
    );
  }

  const processing = ACTIVE.has(data.status);
  const overall = data.overall_verdict || null;

  return (
    <section className="section">
      <div className="wrap narrow">
        <p className="eyebrow">{processing ? "Checking" : "Report"}</p>
        <h2>
          {processing ? (
            <>
              Searching the sources <em>for you.</em>
            </>
          ) : (
            <>
              Here is what <em>the sources say.</em>
            </>
          )}
        </h2>
        <p className="lead">
          {data.page_title ? data.page_title : "Your submission"}
          <span className="muted"> · ref </span>
          <span className="mono muted">{data.id.slice(0, 8)}</span>
        </p>

        {processing ? (
          <div className="panel panel-kesri progress">
            <div className={`progress-step ${step >= 1 ? "active" : ""}`}>
              <span className="dot" />
              <div>
                <strong>Reading the post</strong>
                <div className="muted">Listening to audio, reading captions and on-screen text</div>
              </div>
            </div>
            <div className={`progress-step ${step >= 2 ? "active" : ""}`}>
              <span className="dot" />
              <div>
                <strong>Searching Gurbani and sources</strong>
                <div className="muted">Sri Guru Granth Sahib Ji, Rehat Maryada, curated history</div>
              </div>
            </div>
            <div className={`progress-step ${step >= 3 ? "active" : ""}`}>
              <span className="dot" />
              <div>
                <strong>Writing the report</strong>
                <div className="muted">A verdict for each claim, with the Ang</div>
              </div>
            </div>
          </div>
        ) : null}

        {!processing ? (
          <>
            {overall ? (
              <div className="panel panel-kesri overall">
                <div className="verdict-row" style={{ marginBottom: 0 }}>
                  <span className={`badge ${overall}`}>{overall.replaceAll("_", " ")}</span>
                  {data.overall_confidence != null ? (
                    <span className="badge">{(data.overall_confidence * 100).toFixed(0)}% confidence</span>
                  ) : null}
                  {data.status === "needs_review" ? <span className="badge pending">Sent for Sangat review</span> : null}
                </div>
                <p className="overall-verdict">{OVERALL_LABEL[overall] ?? overall.replaceAll("_", " ")}</p>
                {data.overall_summary ? <p style={{ margin: 0, lineHeight: 1.6 }}>{data.overall_summary}</p> : null}
              </div>
            ) : null}

            {data.error_message && data.claims.length === 0 ? (
              <p className="form-error">{data.error_message}</p>
            ) : null}

            <div className="verdict-stack">
              {data.claims.map((claim) => (
                <VerdictCard key={claim.id} claim={claim} />
              ))}
            </div>

            {data.extracted_text ? (
              <details className="panel raw-panel" style={{ marginTop: "1.25rem" }}>
                <summary>What Sach Khoj read from the post</summary>
                <pre>{data.extracted_text}</pre>
              </details>
            ) : null}

            <div className="cta-row" style={{ marginTop: "1.5rem" }}>
              <Link className="btn btn-primary" href="/submit">
                Check another post
              </Link>
            </div>
          </>
        ) : null}

        <div className="disclaimer">
          Share carefully. Prefer wording like “this claim appears inaccurate based on the sources”
          rather than accusing the person who posted it. Sach Khoj is not Panthic authority.
        </div>
      </div>
    </section>
  );
}
