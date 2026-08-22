import { Claim } from "@/lib/api";

export function VerdictCard({ claim }: { claim: Claim }) {
  return (
    <article className="panel">
      <div className="verdict-row">
        <span className={`badge ${claim.verdict || "unverified"}`}>
          {(claim.verdict || "pending").replaceAll("_", " ")}
        </span>
        <span className="badge">{claim.category.replaceAll("_", " ")}</span>
        {claim.confidence != null ? (
          <span className="badge">{(claim.confidence * 100).toFixed(0)}% confidence</span>
        ) : null}
      </div>
      <h3 style={{ margin: "0 0 0.5rem", fontFamily: "var(--font-display)", fontSize: "1.15rem" }}>
        {claim.text}
      </h3>
      {claim.quoted_gurbani ? (
        <p className="muted" style={{ fontSize: "1.05rem" }}>
          Quoted: {claim.quoted_gurbani}
        </p>
      ) : null}
      <p style={{ marginTop: 0 }}>{claim.summary}</p>
      {claim.correction ? (
        <p>
          <strong>Correction:</strong> {claim.correction}
        </p>
      ) : null}
      {claim.evidence && claim.evidence.length > 0 ? (
        <div className="evidence">
          {claim.evidence.map((ev) => (
            <details key={ev.id}>
              <summary>
                {ev.source} · {ev.reference}
              </summary>
              <p>{ev.excerpt}</p>
              {ev.url ? (
                <p>
                  <a href={ev.url} target="_blank" rel="noreferrer">
                    Open source
                  </a>
                </p>
              ) : null}
            </details>
          ))}
        </div>
      ) : null}
    </article>
  );
}
