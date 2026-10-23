import { type ReactNode, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import useSWR from 'swr'
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import HeaderBar from '../components/common/HeaderBar'
import { SiteFooter } from '../components/common/SiteFooter'
import { LoginRequiredOverlay } from '../components/auth/LoginRequiredOverlay'
import { LoginPage } from '../components/auth/LoginPage'
import { RegisterPage } from '../components/auth/RegisterPage'
import { ResetPasswordPage } from '../components/auth/ResetPasswordPage'
import { SetupPage } from '../components/modals/SetupPage'
import { AITradersPage } from '../components/trader/AITradersPage'
import { TraderLaunchGuestPage } from '../components/trader/TraderLaunchGuestPage'
import { FAQPage } from '../pages/FAQPage'
import { LandingPage } from '../pages/LandingPage'
import { BeginnerOnboardingPage } from '../pages/BeginnerOnboardingPage'
import { LeaderboardPage } from '../pages/LeaderboardPage'
import { DataPage } from '../pages/DataPage'
import { DemoSettingsPage as SettingsPage } from '../pages/DemoSettingsPage'
import { StrategyStudioPage } from '../pages/StrategyStudioPage'
import { PaperLoopPanel } from '../components/strategy/PaperLoopPanel'
import { useAuth } from '../contexts/AuthContext'
import { useLanguage } from '../contexts/LanguageContext'
import { useSystemConfig } from '../hooks/useSystemConfig'
import { t } from '../i18n/translations'
import { api } from '../lib/api'
import type {
  TraderInfo,
} from '../types'
import {
  buildDashboardPath,
  LEGACY_HASH_ROUTES,
  ROUTES,
  type Page,
} from './paths'

function getTraderSlug(trader: TraderInfo) {
  const idPrefix = trader.trader_id.slice(0, 4)
  return `${trader.trader_name}-${idPrefix}`
}

function LoadingScreen() {
  const { language } = useLanguage()

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: '#F1ECE2' }}
    >
      <div className="text-center">
        <img
          src="/icons/algobots.svg"
          alt="AlgoBots Logo"
          className="w-16 h-16 mx-auto mb-4 animate-pulse"
        />
        <p style={{ color: '#1A1813' }}>{t('loading', language)}</p>
      </div>
    </div>
  )
}

function LegacyHashRedirect() {
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    const hashRoute = LEGACY_HASH_ROUTES[location.hash.slice(1)]
    if (!hashRoute) {
      return
    }

    if (hashRoute === location.pathname && location.hash === '') {
      return
    }

    navigate(
      {
        pathname: hashRoute,
        search: location.search,
      },
      { replace: true }
    )
  }, [location.hash, location.pathname, location.search, navigate])

  return null
}

interface AppChromeProps {
  children: ReactNode
  currentPage?: Page
  showFooter?: boolean
  wrapInMain?: boolean
  animateContent?: boolean
  extraContent?: ReactNode
}

function AppChrome({
  children,
  currentPage,
  showFooter = true,
  wrapInMain = true,
  animateContent = false,
  extraContent,
}: AppChromeProps) {
  const location = useLocation()
  const { language, setLanguage } = useLanguage()
  const { user, logout } = useAuth()
  const [loginOverlayOpen, setLoginOverlayOpen] = useState(false)
  const [loginOverlayFeature, setLoginOverlayFeature] = useState('')

  const handleLoginRequired = (featureName: string) => {
    setLoginOverlayFeature(featureName)
    setLoginOverlayOpen(true)
  }

  const content = animateContent ? (
    <AnimatePresence mode="wait">
      <motion.div
        key={`${location.pathname}${location.search}`}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.15, ease: 'easeOut' }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  ) : (
    children
  )

  return (
    <div
      className="min-h-screen"
      style={{ background: '#F1ECE2', color: '#1A1813' }}
    >
      <HeaderBar
        isLoggedIn={!!user}
        currentPage={currentPage}
        language={language}
        onLanguageChange={setLanguage}
        user={user}
        onLogout={logout}
        onLoginRequired={handleLoginRequired}
      />

      {wrapInMain ? (
        <main className="min-h-screen pt-16">{content}</main>
      ) : (
        content
      )}

      {showFooter ? <SiteFooter language={language} /> : null}

      <LoginRequiredOverlay
        isOpen={loginOverlayOpen}
        onClose={() => setLoginOverlayOpen(false)}
        featureName={loginOverlayFeature}
      />

      {extraContent}
    </div>
  )
}

function TradersRoute({
  showBeginnerOnboarding = false,
}: {
  showBeginnerOnboarding?: boolean
}) {
  const navigate = useNavigate()
  const { user, token } = useAuth()
  const { data: traders } = useSWR<TraderInfo[]>(
    user && token ? 'traders-route' : null,
    api.getTraders,
    {
      refreshInterval: 5000,
      shouldRetryOnError: false,
    }
  )

  return (
    <AppChrome
      currentPage="traders"
      animateContent
      extraContent={showBeginnerOnboarding ? <BeginnerOnboardingPage /> : null}
    >
      <AITradersPage
        onTraderSelect={(traderId) => {
          const trader = traders?.find((item) => item.trader_id === traderId)
          navigate(
            buildDashboardPath(trader ? getTraderSlug(trader) : undefined)
          )
        }}
      />
    </AppChrome>
  )
}

export function AppRoutes() {
  const { user, token, isLoading } = useAuth()
  const { config: systemConfig, loading: configLoading } = useSystemConfig()
  const isAuthenticated = !!user && !!token

  if (isLoading || configLoading) {
    return <LoadingScreen />
  }

  if (systemConfig && !systemConfig.initialized && !user) {
    return <SetupPage />
  }

  return (
    <>
      <LegacyHashRedirect />
      <Routes>
        <Route path={ROUTES.home} element={isAuthenticated ? <Navigate to={ROUTES.dashboard} replace /> : <LandingPage />} />
        <Route path={ROUTES.login} element={<LoginPage />} />
        <Route path={ROUTES.register} element={<RegisterPage />} />
        <Route path={ROUTES.resetPassword} element={<ResetPasswordPage />} />
        <Route
          path={ROUTES.setup}
          element={
            user ? (
              <Navigate to={ROUTES.dashboard} replace />
            ) : systemConfig?.initialized ? (
              <Navigate to={ROUTES.login} replace />
            ) : (
              <SetupPage />
            )
          }
        />
        <Route
          path={ROUTES.faq}
          element={
            <AppChrome currentPage="faq" showFooter={false} wrapInMain={false}>
              <FAQPage />
            </AppChrome>
          }
        />
        <Route
          path={ROUTES.data}
          element={
            <AppChrome currentPage="data" showFooter={false}>
              <DataPage />
            </AppChrome>
          }
        />
        <Route path="/config" element={<Navigate to={ROUTES.settings} replace />} />
        <Route path="/leaderboard" element={isAuthenticated ? <AppChrome currentPage="competition"><LeaderboardPage /></AppChrome> : <Navigate to={ROUTES.login} replace />} />
        <Route
          path={ROUTES.settings}
          element={
            isAuthenticated ? (
              <AppChrome showFooter={false}>
                <SettingsPage />
              </AppChrome>
            ) : (
              <Navigate to={ROUTES.login} replace />
            )
          }
        />
        <Route
          path={ROUTES.welcome}
          element={
            // The welcome overlay is the AI-wallet deposit page (QR +
            // auto-refreshing balance) — useful to every signed-in user, so
            // no legacy "beginner mode" gate here.
            isAuthenticated ? (
              <Navigate to={ROUTES.dashboard} replace />
            ) : (
              <Navigate to={ROUTES.login} replace />
            )
          }
        />
        <Route
          path={ROUTES.competition}
          element={
            isAuthenticated ? (
              <AppChrome currentPage="competition" animateContent>
                <LeaderboardPage />
              </AppChrome>
            ) : (
              <LandingPage />
            )
          }
        />
        <Route
          path={ROUTES.strategyMarket}
          element={
            isAuthenticated ? (
              <Navigate to={ROUTES.strategy} replace />
            ) : (
              <LandingPage />
            )
          }
        />
        <Route
          path={ROUTES.traders}
          element={
            isAuthenticated ? (
              <TradersRoute />
            ) : (
              <AppChrome
                currentPage="traders"
                showFooter={false}
                animateContent
              >
                <TraderLaunchGuestPage />
              </AppChrome>
            )
          }
        />
        <Route
          path={ROUTES.dashboard}
          element={isAuthenticated ? <AppChrome currentPage="trader"><section className="max-w-7xl mx-auto p-6"><h1 className="text-2xl font-semibold mb-4">Dashboard</h1><PaperLoopPanel /></section></AppChrome> : <LandingPage />}
        />
        <Route
          path={ROUTES.strategy}
          element={
            isAuthenticated ? (
              <AppChrome currentPage="strategy" animateContent>
                <StrategyStudioPage />
              </AppChrome>
            ) : (
              <LandingPage />
            )
          }
        />
        <Route path="*" element={<Navigate to={ROUTES.home} replace />} />
      </Routes>
    </>
  )
}
