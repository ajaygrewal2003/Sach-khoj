import Link from "next/link";
import { IkOnkar } from "@/components/IkOnkar";

const worries = [
  {
    icon: "ਗੁ",
    title: "“Guru Sahib said…” with no Ang",
    body:
      "A reel quotes a line as Gurbani, but nobody shows where it is in Sri Guru Granth Sahib Ji. Sometimes it is real. Sometimes it is a poem, a Sakhi, or simply made up.",
    quote: "ਕਬੀਰ ਜੀ ਦੀ ਬਾਣੀ? ਭਗਤ ਜੀ ਦੀ? ਜਾਂ ਕਿਸੇ ਦੀ ਵੀ ਨਹੀਂ?",
  },
  {
    icon: "ਇ",
    title: "History that keeps changing",
    body:
      "Dates, places and names of Gurus and Shaheeds get mixed up on WhatsApp forwards. A story gets retold until nobody remembers where it came from.",
    quote: "ਸਾਖੀ ਜਾਂ ਇਤਿਹਾਸ?",
  },
  {
    icon: "ਰ",
    title: "Rehat rulings from strangers",
    body:
      "Posts declare what a Sikh “must” or “must not” do, as if it were settled, with no reference to the Sikh Rehat Maryada or any Panthic source.",
    quote: "ਰਹਿਤ ਮਰਯਾਦਾ ਕੀ ਕਹਿੰਦੀ ਹੈ?",
  },
  {
    icon: "ਸ",
    title: "Divisive content in Sikhi’s name",
    body:
      "Some content borrows Gurbani to push agendas against other communities, or against Sikhs themselves. It spreads fast because it looks devotional.",
    quote: "ਨਾ ਕੋ ਬੈਰੀ ਨਹੀ ਬਿਗਾਨਾ ॥",
  },
];

export default function HomePage() {
  return (
    <>
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="hero">
        <div className="wrap hero-grid">
          <div>
            <p className="hero-gurmukhi">ਸੱਚ ਖੋਜ</p>
            <h1>
              Before you share it, <em>check it against Gurbani.</em>
            </h1>
            <p className="hero-lead">
              Saw a reel quoting Guru Sahib? A post about Sikh history that didn’t feel right? Paste
              the link. Sach Khoj checks it against Sri Guru Granth Sahib Ji and trusted Sikh
              sources, and shows you the Ang so you can read it yourself.
            </p>
            <div className="cta-row">
              <Link className="btn btn-primary btn-lg" href="/submit">
                Check a post
              </Link>
              <Link className="btn btn-ghost btn-lg" href="#how">
                How it works
              </Link>
            </div>
            <p className="hero-note">
              Works with Instagram, TikTok, YouTube, Facebook, X, articles, screenshots and plain text.
              Free to use. No account needed.
            </p>
          </div>

          <div className="pothi" aria-label="Gurbani quotation">
            <span className="pothi-corner tl" />
            <span className="pothi-corner tr" />
            <span className="pothi-corner bl" />
            <span className="pothi-corner br" />
            <IkOnkar className="pothi-onkar" />
            <p className="pothi-tuk">ਕੂੜੁ ਨਿਖੁਟੇ ਨਾਨਕਾ ਓੜਕਿ ਸਚਿ ਰਹੀ ॥</p>
            <p className="pothi-translit">Koorh nikhutte Nanaka, orrak sach rahee.</p>
            <p className="pothi-meaning">
              Falsehood shall come to an end, O Nanak; in the end, Truth alone shall remain.
            </p>
            <p className="pothi-ang">Sri Guru Granth Sahib Ji · Ang 953</p>
          </div>
        </div>
      </section>

      {/* ── Sounds familiar ──────────────────────────────────── */}
      <section className="section" id="why">
        <div className="wrap">
          <div className="section-head">
            <p className="eyebrow">Sounds familiar?</p>
            <h2>
              So much is shared in Sikhi’s name. <em>Not all of it is true.</em>
            </h2>
            <p className="lead">
              Most of us have paused over a forward and thought, “Is that really in Gurbani?”
              Sach Khoj was built for exactly that moment.
            </p>
          </div>
          <div className="card-grid">
            {worries.map((w) => (
              <article className="card" key={w.title}>
                <div className="card-icon">{w.icon}</div>
                <h3>{w.title}</h3>
                <p>{w.body}</p>
                <p className="card-quote">{w.quote}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────── */}
      <section className="section" id="how">
        <div className="wrap">
          <div className="section-head center">
            <p className="eyebrow">How it works</p>
            <h2>
              Three steps. <em>No expertise needed.</em>
            </h2>
            <p className="lead">
              You do not need to know Raags, Angs or Gurmukhi to use Sach Khoj. Just bring the post.
            </p>
          </div>
          <div className="steps">
            <div className="step">
              <span className="step-num">1</span>
              <h3>Paste the link or screenshot</h3>
              <p>
                Share a reel, video, post, article, screenshot, or just type what you heard. Sach
                Khoj listens to the audio, reads the text on screen, and picks out the actual claims.
              </p>
            </div>
            <div className="step">
              <span className="step-num">2</span>
              <h3>It searches the sources</h3>
              <p>
                Each claim is checked against Sri Guru Granth Sahib Ji, the Sikh Rehat Maryada, and
                a curated record of Sikh history and well-known false stories.
              </p>
            </div>
            <div className="step">
              <span className="step-num">3</span>
              <h3>You get the answer, with the Ang</h3>
              <p>
                A clear verdict for every claim, the actual Shabad or source alongside it, and a
                gentle correction you can share instead of an argument.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Sample report ────────────────────────────────────── */}
      <section className="section" id="sample">
        <div className="wrap sample-grid">
          <div>
            <p className="eyebrow">What a check looks like</p>
            <h2>
              Not just “true” or “false”. <em>The Shabad itself.</em>
            </h2>
            <p className="lead">
              Here is a common one. A post credits a well-loved tuk to the wrong Guru Sahib. Sach
              Khoj finds the line, names the Bani, and shows you the Ang.
            </p>
            <div className="sample-post" aria-label="Example social media post">
              <div className="sample-post-head">
                <span className="sample-avatar" />
                <span>sikhi_quotes_daily · Reel</span>
              </div>
              <p style={{ margin: 0 }}>
                “Guru Gobind Singh Ji wrote:{" "}
                <span className="gurmukhi">ਸੋ ਕਿਉ ਮੰਦਾ ਆਖੀਐ ਜਿਤੁ ਜੰਮਹਿ ਰਾਜਾਨ</span> 🙏 Share if
                you agree!”
              </p>
            </div>
          </div>

          <article className="panel verdict-card misleading" aria-label="Example verdict">
            <div className="verdict-row">
              <span className="badge misleading">Misleading</span>
              <span className="badge">Gurbani attribution</span>
              <span className="badge">Example</span>
            </div>
            <h3 className="claim-text">
              The tuk “So kio manda aakhiai jit jammeh raajaan” was written by Guru Gobind Singh Ji.
            </h3>
            <p className="claim-quoted">ਸੋ ਕਿਉ ਮੰਦਾ ਆਖੀਐ ਜਿਤੁ ਜੰਮਹਿ ਰਾਜਾਨ ॥</p>
            <p className="claim-summary">
              The line is genuine Gurbani, but it is by Guru Nanak Dev Ji, not Guru Gobind Singh Ji.
              It appears in Asa Ki Vaar in Sri Guru Granth Sahib Ji.
            </p>
            <p className="claim-correction">
              <strong>Share this instead:</strong> “This tuk is from Guru Nanak Dev Ji’s Asa Ki
              Vaar, Ang 473: ‘Why call her bad, from whom kings are born?’”
            </p>
            <div className="evidence">
              <p className="evidence-title">Evidence</p>
              <details open>
                <summary>Sri Guru Granth Sahib Ji · Ang 473 · Asa Ki Vaar, Mahalla 1</summary>
                <p className="evidence-excerpt">ਸੋ ਕਿਉ ਮੰਦਾ ਆਖੀਐ ਜਿਤੁ ਜੰਮਹਿ ਰਾਜਾਨ ॥</p>
                <p className="evidence-translation">
                  So why call her bad? From her, kings are born.
                </p>
              </details>
            </div>
          </article>
        </div>
      </section>

      {/* ── Values ───────────────────────────────────────────── */}
      <section className="section">
        <div className="wrap">
          <div className="values">
            <p className="eyebrow" style={{ color: "var(--kesri)" }}>
              Built with respect
            </p>
            <h2>
              Made for Sangat, <em>with humility.</em>
            </h2>
            <p className="lead">
              Sach Khoj is a research helper, not a judge. It is here to point you back to the
              sources, never to replace them.
            </p>
            <div className="values-grid">
              <div className="value">
                <h3>Always shows the Ang</h3>
                <p>
                  Every Gurbani reference comes from the actual text of Sri Guru Granth Sahib Ji. It
                  is not allowed to invent an Ang number or a line.
                </p>
              </div>
              <div className="value">
                <h3>Not Panthic authority</h3>
                <p>
                  Verdicts are claim assessments, not rulings. For matters of faith and Rehat, speak
                  with a Giani or trusted scholars.
                </p>
              </div>
              <div className="value">
                <h3>Sangat reviews the hard ones</h3>
                <p>
                  When the tool is unsure, it says so, and the case goes to a human review queue
                  instead of being treated as settled.
                </p>
              </div>
              <div className="value">
                <h3>Corrections, not accusations</h3>
                <p>
                  The aim is to correct a claim kindly, not to shame the person who shared it. Every
                  report suggests gentle wording you can use.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Closing ──────────────────────────────────────────── */}
      <section className="closing">
        <div className="wrap narrow">
          <p className="rule">॥</p>
          <p className="pothi-tuk" style={{ marginTop: "1.5rem" }}>
            ਸਚਹੁ ਓਰੈ ਸਭੁ ਕੋ ਉਪਰਿ ਸਚੁ ਆਚਾਰੁ ॥
          </p>
          <p className="pothi-translit">Sachahu orai sabh ko, upar sach aachaar.</p>
          <p className="pothi-meaning">
            Truth is high, but higher still is truthful living.
          </p>
          <p className="pothi-ang">Sri Guru Granth Sahib Ji · Ang 62</p>
          <div className="cta-row">
            <Link className="btn btn-primary btn-lg" href="/submit">
              Check something you saw today
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
