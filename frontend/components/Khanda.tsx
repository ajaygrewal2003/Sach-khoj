type Props = { size?: number; className?: string; title?: string };

/**
 * Khanda mark: chakkar (ring), central double-edged khanda, and two kirpans
 * whose handles cross beneath it. Uses currentColor so it inherits text colour.
 */
export function Khanda({ size = 48, className, title = "Khanda" }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role="img"
      aria-label={title}
      fill="currentColor"
    >
      {/* left kirpan: blade + crossing handle */}
      <path d="M41 78 C20 70, 8 50, 12 16 C15 46, 26 64, 47 74 Z" />
      <path d="M40 78 L59 93 L56 97 L37 82 Z" />
      {/* right kirpan */}
      <path d="M59 78 C80 70, 92 50, 88 16 C85 46, 74 64, 53 74 Z" />
      <path d="M60 78 L41 93 L44 97 L63 82 Z" />
      {/* chakkar */}
      <path
        fillRule="evenodd"
        d="M50 22 a26 26 0 1 0 0.01 0 Z M50 27.5 a20.5 20.5 0 1 1 -0.01 0 Z"
      />
      {/* central khanda */}
      <path d="M50 2 L42.5 18 L44 64 L56 64 L57.5 18 Z" />
      <path d="M50 12 L50 60" stroke="#fff8ea" strokeOpacity="0.55" strokeWidth="1.2" fill="none" />
      <rect x="37" y="64" width="26" height="5" rx="2" />
      <rect x="46.5" y="69" width="7" height="14" rx="2" />
      <circle cx="50" cy="87" r="4" />
    </svg>
  );
}
