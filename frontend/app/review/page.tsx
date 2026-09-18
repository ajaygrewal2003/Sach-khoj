"use client";

import { FormEvent, useState } from "react";
import { apiBase, Case } from "@/lib/api";
import { VerdictCard } from "@/components/VerdictCard";

export default function ReviewPage() {
  const [token, setToken] = useState("");
  const [items, setItems] = useState<Case[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  async function loadQueue(e?: FormEvent) {
    e?.preventDefault();
    setError(null);
    try {
      const res = await fetch(`${apiBase()}/api/review/queue`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      const body = await res.json();
      setItems(body.items || []);
      setLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load queue");
    }
  }

  async function act(caseId: string, action: "approve" | "dismiss" | "override") {
    setError(null);
    try {
      const res = await fetch(`${apiBase()}/api/review/${caseId}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ action, notes: notes[caseId] || null }),
      });
      if (!res.ok) throw new Error(await res.text());
      await loadQueue();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  }

  return (
    <section className="section">
      <div className="wrap narrow">
        <p className="eyebrow">Sangat review</p>
        <h2>
          The cases the tool <em>wasn’t sure about.</em>
        </h2>
        <p className="lead">
          Low-confidence and unverified cases wait here for a human reader. Approve, dismiss, or
          leave notes before anything is treated as settled. This page is for reviewers with an
          admin token.
        </p>

        <form className="panel panel-kesri form-grid" onSubmit={loadQueue} style={{ marginBottom: "1.25rem" }}>
          <label>
            Reviewer token
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste your admin token"
              required
            />
          </label>
          <div className="cta-row">
            <button className="btn btn-navy" type="submit">
              Open the queue
            </button>
          </div>
        </form>

        {error ? <p className="form-error">{error}</p> : null}

        <div className="verdict-stack">
          {items.map((item) => (
            <div key={item.id} className="panel">
              <div className="verdict-row">
                <span className={`badge ${item.overall_verdict || "unverified"}`}>
                  {(item.overall_verdict || "unknown").replaceAll("_", " ")}
                </span>
                <span className="badge">{item.status.replaceAll("_", " ")}</span>
                <span className="mono muted">{item.id}</span>
              </div>
              {item.overall_summary ? <p>{item.overall_summary}</p> : null}
              <div className="verdict-stack" style={{ marginBottom: "1rem" }}>
                {item.claims.map((c) => (
                  <VerdictCard key={c.id} claim={c} />
                ))}
              </div>
              <label>
                Reviewer notes
                <textarea
                  value={notes[item.id] || ""}
                  onChange={(e) => setNotes((n) => ({ ...n, [item.id]: e.target.value }))}
                  placeholder="What did you check, and what should the Sangat know?"
                />
              </label>
              <div className="cta-row" style={{ marginTop: "0.9rem" }}>
                <button className="btn btn-primary" type="button" onClick={() => act(item.id, "approve")}>
                  Approve
                </button>
                <button className="btn btn-ghost" type="button" onClick={() => act(item.id, "dismiss")}>
                  Dismiss
                </button>
              </div>
            </div>
          ))}
          {loaded && items.length === 0 ? (
            <p className="muted">Nothing waiting for review right now.</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
