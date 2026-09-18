type Props = { className?: string };

/** Ik Onkar (ੴ) rendered with the Gurmukhi font. Decorative unless a label is given. */
export function IkOnkar({ className }: Props) {
  return (
    <span className={`ik-onkar ${className ?? ""}`} aria-hidden="true">
      ੴ
    </span>
  );
}
