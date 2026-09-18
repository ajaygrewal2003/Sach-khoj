import Link from "next/link";
import { Khanda } from "./Khanda";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-grid">
        <div className="footer-brand">
          <Khanda size={36} className="footer-khanda" />
          <div>
            <div className="brand-mark">
              Sach <span>Khoj</span>
            </div>
            <p className="muted">
              A seva project: helping Sangat check what they read about Sikhi before sharing it
              onward.
            </p>
          </div>
        </div>
        <nav className="footer-links" aria-label="Footer">
          <Link href="/submit">Check a post</Link>
          <Link href="/#how">How it works</Link>
          <Link href="/about">About the tool</Link>
          <Link href="/review">Sangat review</Link>
        </nav>
        <p className="footer-disclaimer">
          Sach Khoj is an AI-assisted research tool, not Panthic authority. It shows you the sources
          so you can read them yourself. For religious guidance, speak to a Giani or trusted
          scholars. Results with low confidence are sent for human review.
        </p>
        <p className="footer-line gurmukhi">ਵਾਹਿਗੁਰੂ ਜੀ ਕਾ ਖ਼ਾਲਸਾ, ਵਾਹਿਗੁਰੂ ਜੀ ਕੀ ਫ਼ਤਹਿ ॥</p>
      </div>
    </footer>
  );
}
