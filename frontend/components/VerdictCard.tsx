import { Claim } from "@/lib/api";

const VERDICT_LABEL: Record<string, string> = {
  true: "Consistent with sources",
  false: "Not supported",
  misleading: "Misleading",
  unverified: "Could not verify",
  not_checkable: "Not a checkable claim",
  pending: "Pending",
};

export function VerdictCard({ claim }: { claim: Claim }) {
  const verdict = claim.verdict || "unverified";
  return (
    <article className={`panel verdict-card ${verdict}`}>
      <div className="verdict-row">
        <span className={`badge ${verdict}`}>{VERDICT_LABEL[verdict] ?? verdict.replaceAll("_", " ")}</span>
        <span className="badge">{claim.category.replaceAll("_", " ")}</span>
        {claim.confidence != null ? (
          <span className="badge">{(claim.confidence * 100).toFixed(0)}% confidence</span>
        ) : null}
      </div>
      <h3 className="claim-text">{claim.text}</h3>
      {claim.quoted_gurbani ? <p className="claim-quoted">{claim.quoted_gurbani}</p> : null}
      {claim.summary ? <p className="claim-summary">{claim.summary}</p> : null}
      {claim.correction ? (
        <p className="claim-correction">
          <strong>Share this instead:</strong> {claim.correction}
        </p>
      ) : null}
      {claim.evidence && claim.evidence.length > 0 ? (
        <div className="evidence">
          <p className="evidence-title">Evidence</p>
          {claim.evidence.map((ev) => (
            <details key={ev.id}>
              <summary>
                {ev.source} · {ev.reference}
              </summary>
              <p className="evidence-excerpt">{ev.excerpt}</p>
              {ev.translation ? <p className="evidence-translation">{ev.translation}</p> : null}
              {ev.url ? (
                <p style={{ margin: 0 }}>
                  <a href={ev.url} target="_blank" rel="noreferrer">
                    Read the source
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
