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
          Paste a link to a reel, video, or post (Instagram, Facebook, TikTok, YouTube, X) — the AI
          downloads it, transcribes the speech, reads the visuals, and fact-checks everything. You
          can also paste text or upload a video/screenshot directly if a platform blocks the link.
        </p>

        <form className="panel form-grid" onSubmit={onSubmit}>
          <label>
            URL (reel, video, post, or article)
            <input type="url" name="url" placeholder="https://www.instagram.com/reel/…" />
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
            Video or screenshot upload (optional)
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
