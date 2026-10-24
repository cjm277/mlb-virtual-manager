import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { BuildView } from './components/BuildView'
import { ReviewView } from './components/ReviewView'
import { SetupView } from './components/SetupView'
import { TopBar } from './components/TopBar'
import type { Colors, Game, Plan, RunEvent, Team, Totals } from './types'

type Screen = 'setup' | 'build' | 'review'

function applyTheme(c: Colors) {
  const root = document.documentElement.style
  root.setProperty('--primary', c.primary)
  root.setProperty('--secondary', c.secondary)
  root.setProperty('--on-primary', c.on_primary)
}

function totalsFrom(events: RunEvent[]): Totals {
  const t: Totals = { model_steps: 0, gateway_cache_hits: 0, input_tokens: 0, cached_tokens: 0, output_tokens: 0, cost_usd: 0 }
  for (const e of events) {
    if (e.event !== 'model_step') continue
    t.model_steps += 1
    t.gateway_cache_hits += e.gateway_cache === 'HIT' ? 1 : 0
    t.input_tokens += e.input_tokens ?? 0
    t.cached_tokens += e.cached_tokens ?? 0
    t.output_tokens += e.output_tokens ?? 0
    t.cost_usd += e.cost_usd ?? 0
  }
  return t
}

export default function App() {
  const [league, setLeague] = useState<Colors | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [team, setTeam] = useState<Team | null>(null)
  const [opponent, setOpponent] = useState<Team | null>(null)
  const [screen, setScreen] = useState<Screen>('setup')
  const [runId, setRunId] = useState<string | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [plan, setPlan] = useState<Plan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [keyMissing, setKeyMissing] = useState(false)
  const [clock, setClock] = useState(0)
  const startedAt = useRef<number>(0)

  useEffect(() => {
    api.teams().then((r) => { setTeams(r.teams); setLeague(r.league) }).catch((e) => setError(String(e.message ?? e)))
    api.health().then((h) => setKeyMissing(!h.api_key_found)).catch(() => undefined)
  }, [])

  // League colors until a team is picked, then that team's colors.
  useEffect(() => { if (team) applyTheme(team.colors); else if (league) applyTheme(league) }, [team, league])

  // Poll the run's live events every second until it finishes, then load the plan.
  useEffect(() => {
    if (screen !== 'build' || !runId) return
    let since = 0, stop = false
    const tick = async () => {
      if (stop) return
      try {
        const r = await api.events(runId, since)
        since = r.next
        if (r.events.length) setEvents((prev) => [...prev, ...r.events])
        if (r.error) { setError(r.error); return }
        if (r.done) { const p = await api.plan(runId); setPlan(p); setScreen('review'); return }
      } catch (e) { setError(String((e as Error).message)) }
      setTimeout(tick, 1000)
    }
    tick()
    const timer = setInterval(() => setClock((Date.now() - startedAt.current) / 1000), 250)
    return () => { stop = true; clearInterval(timer) }
  }, [screen, runId])

  useEffect(() => { window.scrollTo(0, 0) }, [screen])

  const liveTotals = useMemo(() => totalsFrom(events), [events])

  async function build(game: Game, notes: string) {
    if (!team) return
    setBusy(true); setError(null)
    try {
      const { run_id } = await api.start(game.game_pk, team.team_id, notes)
      setRunId(run_id); setEvents([]); setPlan(null); startedAt.current = Date.now(); setClock(0); setScreen('build')
    } catch (e) { setError(String((e as Error).message)) } finally { setBusy(false) }
  }

  async function openRun(id: string) {
    try {
      const p = await api.plan(id)
      setTeam(teams.find((t) => t.team_id === p.game.team_id) ?? null)
      setOpponent(teams.find((t) => t.team_id === p.game.opponent_id) ?? null)
      setRunId(id); setPlan(p); setScreen('review')
    } catch (e) { setError(String((e as Error).message)) }
  }

  function home() { setScreen('setup'); setPlan(null); setRunId(null); setEvents([]); setError(null) }

  const totals = screen === 'build' ? liveTotals : screen === 'review' && plan ? plan.usage.total : null
  const seconds = screen === 'build' ? clock : screen === 'review' && plan ? plan.usage.seconds : null

  return (
    <>
      <TopBar team={team} opponent={opponent} totals={totals} seconds={seconds} live={screen === 'build'} onHome={home} />
      {screen === 'setup' && <SetupView teams={teams} team={team} opponent={opponent} onTeam={setTeam} onOpponent={setOpponent}
        onBuild={build} onOpenRun={openRun} busy={busy} error={error} keyMissing={keyMissing} />}
      {screen === 'build' && <BuildView events={events} error={error} />}
      {screen === 'review' && plan && <ReviewView plan={plan} onPlan={setPlan} />}
      <footer>MLB Virtual Manager · data: MLB Stats API and Baseball Savant (Statcast) · model: gpt-6-luna · every number comes from the data, never from the model</footer>
    </>
  )
}
