"use client";

import { FormEvent, useState } from "react";
import { apiBase, Case } from "@/lib/api";
import { VerdictCard } from "@/components/VerdictCard";

export default function ReviewPage() {
  const [token, setToken] = useState("");
  const [items, setItems] = useState<Case[]>([]);
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
      <div className="wrap">
        <h2>Human review queue</h2>
        <p className="lead">
          Low-confidence and unverified cases land here. Approve, dismiss, or leave notes before
          anything is treated as settled.
        </p>

        <form className="panel form-grid" onSubmit={loadQueue} style={{ marginBottom: "1rem" }}>
          <label>
            Admin token
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Bearer token value"
              required
            />
          </label>
          <button className="btn btn-primary" type="submit">
            Load queue
          </button>
        </form>

        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}

        <div className="verdict-stack">
          {items.map((item) => (
            <div key={item.id} className="panel">
              <div className="verdict-row">
                <span className={`badge ${item.overall_verdict || "unverified"}`}>
                  {(item.overall_verdict || "unknown").replaceAll("_", " ")}
                </span>
                <span className="badge">{item.status}</span>
                <span className="mono muted">{item.id}</span>
              </div>
              <p>{item.overall_summary}</p>
              {item.claims.map((c) => (
                <div key={c.id} style={{ marginBottom: "0.75rem" }}>
                  <VerdictCard claim={c} />
                </div>
              ))}
              <label>
                Reviewer notes
                <textarea
                  value={notes[item.id] || ""}
                  onChange={(e) => setNotes((n) => ({ ...n, [item.id]: e.target.value }))}
                />
              </label>
              <div className="cta-row" style={{ marginTop: "0.75rem" }}>
                <button className="btn btn-primary" type="button" onClick={() => act(item.id, "approve")}>
                  Approve
                </button>
                <button className="btn btn-ghost" type="button" onClick={() => act(item.id, "dismiss")}>
                  Dismiss
                </button>
              </div>
            </div>
          ))}
          {items.length === 0 ? <p className="muted">No pending review items loaded.</p> : null}
        </div>
      </div>
    </section>
  );
}
