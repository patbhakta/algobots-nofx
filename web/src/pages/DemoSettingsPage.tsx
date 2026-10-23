import { useAuth } from '../contexts/AuthContext'
import { Link } from 'react-router-dom'

export function DemoSettingsPage() {
  const { user } = useAuth()
  return <section className="max-w-3xl mx-auto p-8 space-y-4">
    <h1 className="text-2xl font-semibold">Configuration</h1>
    <p>Signed in as {user?.email}. This workspace uses live Kalshi data and Nautilus paper execution.</p>
    <p>Exchange credentials, model providers and notifications are managed by the workspace operator. Personal configuration is unavailable in this demo.</p>
    <Link className="underline" to="/strategy">Edit strategy configuration in Strategy Studio</Link>
    <p>Saved strategy drafts do not change the running paper worker.</p>
  </section>
}
