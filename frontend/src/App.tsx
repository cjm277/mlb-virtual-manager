import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { BuildView, type Matchup } from './components/BuildView'
import { ReviewView } from './components/ReviewView'
import { SetupView } from './components/SetupView'
import { TopBar } from './components/TopBar'
import type { Colors, Game, Plan, RunEvent, Team, Totals } from './types'

type Screen = 'setup' | 'build' | 'review'

// Dark text on light team colors (e.g. Brewers gold, Padres yellow), white text on dark ones.
function textOn(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4 ? '#14181d' : '#ffffff'
}

function applyTheme(c: Colors) {
  const root = document.documentElement.style
  root.setProperty('--primary', c.primary)
  root.setProperty('--secondary', c.secondary)
  root.setProperty('--on-primary', textOn(c.primary))
  root.setProperty('--on-secondary', textOn(c.secondary))
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

function addTotals(a: Totals, b?: Totals): Totals {
  if (!b) return a
  return { model_steps: a.model_steps + b.model_steps, gateway_cache_hits: a.gateway_cache_hits + b.gateway_cache_hits,
    input_tokens: a.input_tokens + b.input_tokens, cached_tokens: a.cached_tokens + b.cached_tokens,
    output_tokens: a.output_tokens + b.output_tokens, cost_usd: a.cost_usd + b.cost_usd }
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
  const [matchup, setMatchup] = useState<Matchup | null>(null)
  const [lastRequest, setLastRequest] = useState<{ game: Game; notes: string } | null>(null)
  const [reusedNotice, setReusedNotice] = useState(false)
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

  async function build(game: Game, notes: string, force = false) {
    if (!team) return
    setBusy(true); setError(null); setLastRequest({ game, notes }); setReusedNotice(false)
    try {
      const { run_id, reused } = await api.start(game.game_pk, team.team_id, notes, force)
      if (reused) {   // the same plan was built recently: reopen it instead of paying for it again
        setPlan(await api.plan(run_id)); setRunId(run_id); setReusedNotice(true); setScreen('review')
        return
      }
      const home = game.home_away === 'home'
      setMatchup({ homeTeamId: home ? team.team_id : (opponent?.team_id ?? team.team_id),
        title: `${team.name} ${home ? 'vs' : 'at'} ${opponent?.name ?? ''}`,
        subtitle: `${new Date(`${game.game_date}T12:00:00`).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })} · ${game.venue}` })
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

  const totals = screen === 'build' ? liveTotals : screen === 'review' && plan ? addTotals(plan.usage.total, plan.usage.chat) : null
  const seconds = screen === 'build' ? clock : screen === 'review' && plan ? plan.usage.seconds : null

  return (
    <>
      <TopBar team={team} opponent={opponent} totals={totals} seconds={seconds} live={screen === 'build'} onHome={home} />
      {screen === 'setup' && <SetupView teams={teams} team={team} opponent={opponent} onTeam={setTeam} onOpponent={setOpponent}
        onBuild={build} onOpenRun={openRun} busy={busy} error={error} keyMissing={keyMissing} />}
      {screen === 'build' && <BuildView events={events} error={error} matchup={matchup} />}
      {screen === 'review' && plan && <ReviewView plan={plan} onPlan={setPlan}
        notice={reusedNotice ? 'You built this exact plan within the last 24 hours, so it was reopened at no cost.' : null}
        onRebuild={reusedNotice && lastRequest ? () => build(lastRequest.game, lastRequest.notes, true) : null} />}
      <footer>MLB Virtual Manager · data: MLB Stats API and Baseball Savant (Statcast) · model: gpt-6-luna · every number comes from the data, never from the model</footer>
    </>
  )
}
