/** The SKUTruth mark: an isometric crate, matching the approved header lockup. */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true" focusable="false">
      <path
        d="M16 3.2 28 9.4v13.2L16 28.8 4 22.6V9.4L16 3.2Z"
        fill="#2F6B4A"
        stroke="#173F2A"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M4 9.4 16 15.6l12-6.2M16 15.6v13.2" stroke="#173F2A" strokeWidth="1.6" fill="none" />
      <path d="M10.4 12.5 22 6.6" stroke="#A5B995" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
