import { useState } from 'react'
import { useApiFetch } from '../context/AuthContext'

interface Props {
  onComplete: () => void
}

export default function OnboardingWizard({ onComplete }: Props) {
  const apiFetch = useApiFetch()
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  // Step 1: IG credentials
  const [igApiKey, setIgApiKey] = useState('')
  const [igUsername, setIgUsername] = useState('')
  const [igPassword, setIgPassword] = useState('')
  const [igAccType, setIgAccType] = useState('LIVE')

  // Step 2: Telegram
  const [telegramToken, setTelegramToken] = useState('')
  const [telegramChatId, setTelegramChatId] = useState('')

  // Step 3: Autopilot
  const [autopilotEnabled, setAutopilotEnabled] = useState(true)
  const [shadowMode, setShadowMode] = useState(true)
  const [searchTerms, setSearchTerms] = useState('EUR/USD,GBP/USD,US 500,Gold')

  const steps = [
    { title: 'IG Markets', desc: 'Connecter votre compte IG' },
    { title: 'Telegram', desc: 'Recevoir les alertes (optionnel)' },
    { title: 'Auto-Pilot', desc: 'Configurer le trading automatique' },
  ]

  const saveStep1 = async () => {
    if (!igApiKey || !igUsername || !igPassword) {
      setMessage('Tous les champs IG sont obligatoires')
      return false
    }
    setSaving(true)
    try {
      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({
          settings: {
            ig_api_key: igApiKey,
            ig_username: igUsername,
            ig_password: igPassword,
            ig_acc_type: igAccType,
          },
        }),
      })
      if (!res.ok) throw new Error('Save failed')
      return true
    } catch {
      setMessage('Erreur de sauvegarde')
      return false
    } finally {
      setSaving(false)
    }
  }

  const saveStep2 = async () => {
    if (!telegramToken && !telegramChatId) return true // skip if empty
    setSaving(true)
    try {
      const settings: Record<string, string> = {}
      if (telegramToken) settings.telegram_bot_token = telegramToken
      if (telegramChatId) settings.telegram_chat_id = telegramChatId
      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ settings }),
      })
      if (!res.ok) throw new Error('Save failed')
      return true
    } catch {
      setMessage('Erreur de sauvegarde')
      return false
    } finally {
      setSaving(false)
    }
  }

  const saveStep3 = async () => {
    setSaving(true)
    try {
      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({
          settings: {
            autopilot_enabled: autopilotEnabled ? 'true' : 'false',
            autopilot_shadow_mode: shadowMode ? 'true' : 'false',
            autopilot_search_terms: searchTerms,
          },
        }),
      })
      if (!res.ok) throw new Error('Save failed')
      // Mark onboarding complete
      await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ settings: { onboarding_complete: 'true' } }),
      })
      return true
    } catch {
      setMessage('Erreur de sauvegarde')
      return false
    } finally {
      setSaving(false)
    }
  }

  const handleNext = async () => {
    setMessage('')
    let success = false
    if (step === 0) success = await saveStep1()
    else if (step === 1) success = await saveStep2()
    else if (step === 2) {
      success = await saveStep3()
      if (success) { onComplete(); return }
    }
    if (success) setStep(step + 1)
  }

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        {/* Progress */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {steps.map((_, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                i < step ? 'bg-profit text-white' : i === step ? 'bg-accent text-white' : 'bg-bg-card text-gray-500 border border-border'
              }`}>
                {i < step ? '\u2713' : i + 1}
              </div>
              {i < steps.length - 1 && <div className={`w-12 h-0.5 ${i < step ? 'bg-profit' : 'bg-border'}`} />}
            </div>
          ))}
        </div>

        {/* Header */}
        <div className="text-center mb-6">
          <h2 className="text-xl font-semibold text-white">{steps[step].title}</h2>
          <p className="text-sm text-gray-500 mt-1">{steps[step].desc}</p>
        </div>

        {message && (
          <div className="bg-loss/20 text-loss text-sm rounded-lg px-4 py-2 mb-4">{message}</div>
        )}

        <div className="card p-6 space-y-4">
          {/* Step 1: IG */}
          {step === 0 && (
            <>
              <div>
                <label className="block text-sm text-gray-500 mb-1">API Key</label>
                <input type="password" value={igApiKey} onChange={(e) => setIgApiKey(e.target.value)} className="input" placeholder="Votre cle API IG" />
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Username</label>
                <input value={igUsername} onChange={(e) => setIgUsername(e.target.value)} className="input" />
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Password</label>
                <input type="password" value={igPassword} onChange={(e) => setIgPassword(e.target.value)} className="input" />
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Type de compte</label>
                <select value={igAccType} onChange={(e) => setIgAccType(e.target.value)} className="input">
                  <option value="LIVE">LIVE</option>
                  <option value="DEMO">DEMO</option>
                </select>
              </div>
            </>
          )}

          {/* Step 2: Telegram */}
          {step === 1 && (
            <>
              <p className="text-xs text-gray-500">Creez un bot Telegram via @BotFather et entrez les informations ci-dessous.</p>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Bot Token</label>
                <input value={telegramToken} onChange={(e) => setTelegramToken(e.target.value)} className="input" placeholder="123456:ABC-DEF..." />
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Chat ID</label>
                <input value={telegramChatId} onChange={(e) => setTelegramChatId(e.target.value)} className="input" placeholder="Votre Chat ID numerique" />
              </div>
            </>
          )}

          {/* Step 3: Autopilot */}
          {step === 2 && (
            <>
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm text-white">Activer l'Auto-Pilot</span>
                  <p className="text-[10px] text-gray-500">Scanne et trade automatiquement les meilleurs marches</p>
                </div>
                <button onClick={() => setAutopilotEnabled(!autopilotEnabled)} className={`relative w-11 h-6 rounded-full transition-colors ${autopilotEnabled ? 'bg-profit' : 'bg-gray-600'}`}>
                  <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${autopilotEnabled ? 'translate-x-5' : ''}`} />
                </button>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm text-white">Mode Shadow (paper trading)</span>
                  <p className="text-[10px] text-gray-500">Simule les trades sans execution reelle — recommande pour commencer</p>
                </div>
                <button onClick={() => setShadowMode(!shadowMode)} className={`relative w-11 h-6 rounded-full transition-colors ${shadowMode ? 'bg-accent' : 'bg-gray-600'}`}>
                  <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${shadowMode ? 'translate-x-5' : ''}`} />
                </button>
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Marches a suivre</label>
                <input value={searchTerms} onChange={(e) => setSearchTerms(e.target.value)} className="input" />
                <p className="text-[10px] text-gray-600 mt-1">Separes par des virgules</p>
              </div>
            </>
          )}

          {/* Navigation */}
          <div className="flex justify-between pt-2">
            {step > 0 ? (
              <button onClick={() => { setStep(step - 1); setMessage('') }} className="text-sm text-gray-500 hover:text-white">Retour</button>
            ) : <div />}
            <div className="flex gap-2">
              {step === 1 && (
                <button onClick={() => { setStep(2); setMessage('') }} className="text-sm text-gray-500 hover:text-white">Passer</button>
              )}
              <button onClick={handleNext} disabled={saving} className="btn-primary">
                {saving ? 'Sauvegarde...' : step === 2 ? 'Terminer' : 'Suivant'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
