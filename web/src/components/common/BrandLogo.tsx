interface BrandLogoProps {
  compact?: boolean
  className?: string
}

/** AlgoBots identity — paper theme, ink on cream, single red accent. */
export function BrandLogo({ compact = false, className = '' }: BrandLogoProps) {
  return (
    <span className={`nofx-brand ${className}`} aria-label="AlgoBots">
      <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="6" fill="#F1ECE2" />
        <circle cx="16" cy="16" r="9" fill="#E0483B" />
      </svg>
      {!compact && (
        <span className="nofx-wordmark" aria-hidden="true">
          AlgoBots
        </span>
      )}
    </span>
  )
}
