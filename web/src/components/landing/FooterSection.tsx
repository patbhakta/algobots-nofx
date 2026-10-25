import { Link } from 'react-router-dom'
import { t, Language } from '../../i18n/translations'
import { ROUTES } from '../../router/paths'

interface FooterSectionProps {
  language: Language
}

// ALG-3344: gutted to brand + in-app nav + copyright. The upstream footer
// carried GitHub stars/forks, docs/issues/PR links and exchange referral
// badges — none of which belong in a private build.
export default function FooterSection({ language }: FooterSectionProps) {
  const navLinks = [
    { to: ROUTES.data, label: 'Data' },
    { to: ROUTES.traders, label: t('configNav', language) },
    { to: ROUTES.dashboard, label: t('dashboardNav', language) },
    { to: ROUTES.strategy, label: t('strategyNav', language) },
    { to: ROUTES.competition, label: t('realtimeNav', language) },
    { to: ROUTES.faq, label: t('faqNav', language) },
  ]

  return (
    <footer style={{ background: '#F1ECE2', borderTop: '1px solid rgba(26, 24, 19, 0.14)' }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex flex-col items-center gap-6 md:flex-row md:justify-between">
          {/* Brand */}
          <Link to={ROUTES.home} className="flex items-center gap-3 transition-opacity hover:opacity-80">
            <img src="/icons/algobots.svg" alt="AlgoBots Logo" className="w-8 h-8" />
            <span className="text-xl font-bold" style={{ color: '#1A1813' }}>
              AlgoBots
            </span>
          </Link>

          {/* Nav links */}
          <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-3">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className="text-sm transition-colors hover:text-[#E0483B]"
                style={{ color: '#8A8478' }}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>

        {/* Copyright */}
        <div
          className="mt-8 pt-6 text-center text-xs"
          style={{ color: '#8A8478', borderTop: '1px solid rgba(26, 24, 19, 0.14)' }}
        >
          <p className="mb-2">{t('footerTitle', language)}</p>
          <p style={{ color: '#B4B2A9' }}>{t('footerWarning', language)}</p>
        </div>
      </div>
    </footer>
  )
}
