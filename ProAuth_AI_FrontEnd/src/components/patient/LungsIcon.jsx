// Custom pulmonary icon — lucide-react has no literal "lungs" glyph, so
// this fills that gap with a hand-drawn one matching lucide's own visual
// conventions exactly (24x24 viewBox, stroke-only, round caps/joins,
// currentColor, 2px default stroke) so it drops into ICON_COMPONENTS in
// DiagnosisSpotlight.jsx and reads as part of the same icon family, not a
// mismatched one-off. Trachea splits into two bronchi, each leading into a
// lobe with a slightly scalloped outer edge (the little inward notch on
// each side) to read as lung tissue rather than a plain balloon shape.
export default function LungsIcon({ size = 24, strokeWidth = 2, ...props }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M12 3v6" />
      <path d="M12 9l-2.5 2" />
      <path d="M12 9l2.5 2" />
      <path d="M9.5 11c-2.3 0-4.3 1.7-4.9 4.2-.5 2.1-.2 4.7 1.3 6.1.9.9 2.2 1.1 3.3.5 1-.6 1.6-1.7 1.6-2.9V12.3c0-.7-.6-1.3-1.3-1.3z" />
      <path d="M14.5 11c2.3 0 4.3 1.7 4.9 4.2.5 2.1.2 4.7-1.3 6.1-.9.9-2.2 1.1-3.3.5-1-.6-1.6-1.7-1.6-2.9V12.3c0-.7.6-1.3 1.3-1.3z" />
    </svg>
  );
}
