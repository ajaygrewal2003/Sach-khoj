import Link from "next/link";
import { IkOnkar } from "./IkOnkar";

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="wrap inner">
        <Link href="/" className="brand" aria-label="Sach Khoj home">
          <span className="brand-emblem">
            <IkOnkar />
          </span>
          <span className="brand-text">
            <span className="brand-mark">
              Sach <span>Khoj</span>
            </span>
            <span className="brand-sub gurmukhi">ਸੱਚ ਖੋਜ · ਕੂੜੁ ਨਿਖੁਟੇ, ਸਚਿ ਰਹੀ</span>
          </span>
        </Link>
        <nav className="nav" aria-label="Main">
          <Link href="/#how">How it works</Link>
          <Link href="/about">About</Link>
          <Link href="/review" className="nav-quiet">
            Sangat review
          </Link>
          <Link href="/submit" className="btn btn-primary btn-sm">
            Check a post
          </Link>
        </nav>
      </div>
    </header>
  );
}
