import Link from "next/link";

export default function HomePage() {
  return (
    <section className="hero">
      <div className="wrap hero-grid">
        <div>
          <h1>
            Sach <em>Khoj</em>
          </h1>
          <p className="hero-lead">
            Check Facebook posts, Instagram reels, and websites for misquoted Gurbani, distorted
            Rehat, and false Sikh history — with Ang citations and curated evidence, not vibes.
          </p>
          <div className="cta-row">
            <Link className="btn btn-primary" href="/submit">
              Check a claim
            </Link>
            <Link className="btn btn-ghost" href="/about">
              How verification works
            </Link>
          </div>
        </div>
        <div className="hero-visual" role="img" aria-label="Abstract sacred geometry backdrop" />
      </div>
    </section>
  );
}
