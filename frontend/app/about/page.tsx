import Link from "next/link";

export default function AboutPage() {
  return (
    <section className="section">
      <div className="wrap narrow">
        <p className="eyebrow">About Sach Khoj</p>
        <h2>
          A small seva: <em>pointing people back to the sources.</em>
        </h2>
        <p className="lead">
          Sach Khoj (ਸੱਚ ਖੋਜ, “search for truth”) reads a post, finds the claims in it, and checks
          each one against Sri Guru Granth Sahib Ji, the Sikh Rehat Maryada, and a curated record of
          Sikh history. It is not allowed to invent an Ang number or a line of Gurbani. Whatever it
          cites, you can open and read yourself.
        </p>

        <div className="panel panel-kesri about-steps">
          <div className="about-step">
            <span className="step-num">1</span>
            <div>
              <strong>Reading the post</strong>
              <p>
                Links are opened, audio is transcribed, on-screen text and captions are read. This
                works in Punjabi (Gurmukhi) and English, and handles screenshots too.
              </p>
            </div>
          </div>
          <div className="about-step">
            <span className="step-num">2</span>
            <div>
              <strong>Finding the claims</strong>
              <p>
                A post often makes several claims at once: a quotation, a date, a “Sikhs must…”.
                Each is separated out so it can be checked on its own.
              </p>
            </div>
          </div>
          <div className="about-step">
            <span className="step-num">3</span>
            <div>
              <strong>Searching the sources</strong>
              <p>
                Gurbani is searched through BaniDB and GurbaniNow, the same databases behind many
                Gurbani apps. History and Rehat claims are checked against curated passages and a
                record of stories already known to be false.
              </p>
            </div>
          </div>
          <div className="about-step">
            <span className="step-num">4</span>
            <div>
              <strong>Writing the verdict</strong>
              <p>
                Each claim is marked consistent with sources, not supported, misleading, or could
                not verify, always with the passages it relied on. When confidence is low, the case
                goes to a human review queue for Sangat.
              </p>
            </div>
          </div>
        </div>

        <div className="disclaimer">
          Sach Khoj assists research. It does not replace scholarly judgment, a Giani, or Panthic
          institutions. Treat its output as a starting point for your own reading, not a ruling.
        </div>

        <div className="cta-row" style={{ marginTop: "1.75rem" }}>
          <Link className="btn btn-primary" href="/submit">
            Check a post
          </Link>
          <Link className="btn btn-ghost" href="/">
            Back home
          </Link>
        </div>
      </div>
    </section>
  );
}
