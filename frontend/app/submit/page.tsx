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
      <div className="wrap narrow">
        <p className="eyebrow">Check a post</p>
        <h2>
          What did you see? <em>Bring it here.</em>
        </h2>
        <p className="lead">
          Paste a link to a reel, video or post, or the text of a forward. If a platform blocks the
          link, upload a screen recording or screenshot instead. Sach Khoj will listen, read, and
          check every claim against Gurbani and trusted sources.
        </p>

        <form className="panel panel-kesri form-grid" onSubmit={onSubmit}>
          <label>
            Link to the reel, video, post or article
            <input type="url" name="url" placeholder="https://www.instagram.com/reel/…" />
            <span className="hint">Instagram, TikTok, YouTube, Facebook, X, or any article.</span>
          </label>

          <div className="or-divider">or</div>

          <label>
            Paste the caption, forward, or claim
            <textarea
              name="text"
              placeholder="e.g. “Guru Nanak Dev Ji said that…” — paste the words as you saw them."
              required={false}
            />
          </label>

          <label>
            Upload a screenshot or video (optional)
            <input type="file" name="media" accept="image/*,video/*" />
            <span className="hint">Useful when a reel cannot be opened from the link.</span>
          </label>

          <label>
            Language of the content
            <select name="language_hint" defaultValue="auto">
              <option value="auto">Let Sach Khoj detect it</option>
              <option value="gurmukhi">Punjabi (Gurmukhi)</option>
              <option value="english">English</option>
            </select>
          </label>

          {error ? <p className="form-error">{error}</p> : null}

          <div className="cta-row">
            <button className="btn btn-primary btn-lg" type="submit" disabled={pending}>
              {pending ? "Sending…" : "Check this"}
            </button>
            <span className="muted" style={{ fontSize: "0.9rem" }}>
              Usually takes under a minute.
            </span>
          </div>
        </form>

        <div className="disclaimer">
          Sach Khoj is an AI-assisted research tool, not Panthic authority. Where it is unsure, the
          case is sent to Sangat for human review rather than treated as settled.
        </div>
      </div>
    </section>
  );
}
