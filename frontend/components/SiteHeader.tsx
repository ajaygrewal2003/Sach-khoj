import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="wrap inner">
        <Link href="/" className="brand">
          <div className="brand-mark">
            Sach <span>Khoj</span>
          </div>
          <div className="brand-sub">ਸੱਚ ਖੋਜ · evidence-grounded claim checks</div>
        </Link>
        <nav className="nav">
          <Link href="/submit">Check a claim</Link>
          <Link href="/review">Review</Link>
          <Link href="/about">About</Link>
        </nav>
      </div>
    </header>
  );
}
