import { ArrowRight, Database, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { markBeginnerOnboardingCompleted } from '../lib/onboarding'

export function BeginnerOnboardingPage() {
  const navigate = useNavigate()
  const handleContinue = () => {
    markBeginnerOnboardingCompleted()
    navigate('/traders')
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/58 px-4 py-10 backdrop-blur-[2px]">
      <div className="w-full max-w-3xl rounded-[32px] border border-[rgba(26,24,19,0.14)] bg-nofx-bg-lighter p-8 shadow-lg sm:p-12">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-nofx-gold/20 bg-nofx-gold/10 text-nofx-gold">
          <ShieldCheck className="h-6 w-6" />
        </div>
        <h1 className="mt-6 text-3xl font-bold tracking-tight text-nofx-text sm:text-4xl">Your AlgoBots subscription is ready</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-nofx-text-muted">
          AI access is included with your subscription. There is no per-call wallet to create, fund, or back up.
        </p>
        <div className="mt-8 rounded-2xl border border-nofx-gold/20 bg-nofx-bg-deeper p-6">
          <div className="flex items-center gap-3 text-sm font-semibold text-nofx-text">
            <Database className="h-5 w-5 text-nofx-gold" /> Connected market intelligence
          </div>
          <p className="mt-3 text-sm leading-6 text-nofx-text-muted">
            AlgoBots combines Binance market data, Polymarket probabilities, and IBKR brokerage data to support its signals and trading decisions.
          </p>
        </div>
        <button type="button" onClick={handleContinue} className="mt-8 inline-flex items-center gap-2 rounded-xl bg-nofx-gold px-5 py-3 text-sm font-bold text-white transition hover:bg-nofx-gold/90">
          Continue to traders <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
