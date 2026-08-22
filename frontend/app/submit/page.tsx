"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { submitCase } from "@/lib/api";

export default function SubmitPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      const media = form.get("media");
      if (media instanceof File && media.size === 0) {
        form.delete("media");
      }
      const created = await submitCase(form);
      router.push(`/cases/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
      setPending(false);
    }
  }

  return (
    <section className="section">
      <div className="wrap">
        <h2>Submit content to verify</h2>
        <p className="lead">
          Paste a URL, caption text, and/or screenshot. Meta blocks most public post scraping — text
          and images are the reliable path for Facebook and Instagram.
        </p>

        <form className="panel form-grid" onSubmit={onSubmit}>
          <label>
            URL (website, Facebook, or Instagram)
            <input type="url" name="url" placeholder="https://..." />
          </label>
          <label>
            Caption / article text
            <textarea
              name="text"
              placeholder="Paste the claim, caption, or article excerpt here…"
              required={false}
            />
          </label>
          <label>
            Language hint
            <select name="language_hint" defaultValue="auto">
              <option value="auto">Auto</option>
              <option value="gurmukhi">Gurmukhi</option>
              <option value="english">English</option>
            </select>
          </label>
          <label>
            Screenshot or reel frame (optional)
            <input type="file" name="media" accept="image/*,video/*" />
          </label>

          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}

          <button className="btn btn-primary" type="submit" disabled={pending}>
            {pending ? "Submitting…" : "Run verification"}
          </button>
        </form>

        <div className="disclaimer">
          AI-assisted research tool, not Panthic authority. Low-confidence results are queued for
          human review.
        </div>
      </div>
    </section>
  );
}
