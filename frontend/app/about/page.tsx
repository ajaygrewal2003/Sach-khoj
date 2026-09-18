export default function AboutPage() {
  return (
    <section className="section">
      <div className="wrap">
        <h2>How Sach Khoj verifies claims</h2>
        <p className="lead">
          Every verdict is grounded in retrieved evidence — BaniDB / GurbaniNow for scripture, plus a
          curated Rehat and history corpus. The model is not allowed to invent Ang numbers.
        </p>

        <div className="panel" style={{ display: "grid", gap: "1rem" }}>
          <div>
            <strong>1. Ingest</strong>
            <p className="muted">URL text extraction, caption paste, screenshot OCR (Gurmukhi + English).</p>
          </div>
          <div>
            <strong>2. Extract claims</strong>
            <p className="muted">Split posts into atomic checkable claims across Gurbani, history, Rehat, and propaganda.</p>
          </div>
          <div>
            <strong>3. Retrieve evidence</strong>
            <p className="muted">Search scripture APIs and curated passages. Known-false patterns are matched first.</p>
          </div>
          <div>
            <strong>4. Verdict</strong>
            <p className="muted">
              Structured labels: false, misleading, unverified, true, not_checkable — with citations
              only from retrieved IDs. Low confidence goes to human review.
            </p>
          </div>
        </div>

        <div className="disclaimer">
          This tool assists research. It does not replace scholarly judgment, a Giani, or Panthic
          institutions.
        </div>
      </div>
    </section>
  );
}
