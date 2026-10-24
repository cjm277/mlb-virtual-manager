import { useEffect, useMemo, useRef } from 'react'
import type { RunEvent } from '../types'

export const AGENTS: Record<string, { title: string; icon: string; job: string }> = {
  team_doctor: { title: 'Team Doctor', icon: '🩺', job: 'Who is out or limited' },
  scout_pitchers: { title: 'Scout: their pitchers', icon: '🔭', job: 'Report for our hitters' },
  scout_hitters: { title: 'Scout: their hitters', icon: '📋', job: 'Report for our pitchers' },
  pitching_coach: { title: 'Pitching Coach', icon: '⚾', job: 'Starter, mix, bullpen' },
  bench_coach: { title: 'Bench Coach', icon: '🧢', job: 'Lineup, bench, moves' },
  manager: { title: 'Manager', icon: '🎯', job: 'Approves or sends fixes' },
  clubhouse_comms: { title: 'Clubhouse Comms', icon: '📣', job: 'Briefings by role' },
}
const STAGES: { label: string; agents: string[] }[] = [
  { label: '1 Medical', agents: ['team_doctor'] },
  { label: '2 Advance scouting', agents: ['scout_pitchers', 'scout_hitters'] },
  { label: '3 Coaches', agents: ['pitching_coach', 'bench_coach'] },
  { label: '4 Checker (code)', agents: ['checker'] },
  { label: '5 Manager', agents: ['manager'] },
  { label: '6 Comms', agents: ['clubhouse_comms'] },
]

interface AgentState { state: 'waiting' | 'working' | 'done'; steps: number; tools: number; lastTool?: string; runs: number; seconds: number }

export function agentStates(events: RunEvent[]) {
  const s: Record<string, AgentState> = {}
  for (const k of [...Object.keys(AGENTS), 'checker']) s[k] = { state: 'waiting', steps: 0, tools: 0, runs: 0, seconds: 0 }
  let checker = ''
  for (const e of events) {
    const a = e.agent ? s[e.agent] : undefined
    if (e.event === 'agent_start' && a) { a.state = 'working'; a.runs += 1 }
    if (e.event === 'model_step' && a) a.steps += 1
    if (e.event === 'tool_result' && a) { a.tools += 1; a.lastTool = e.tool }
    if (e.event === 'agent_end' && a) { a.state = 'done'; a.seconds += e.seconds ?? 0 }
    if (e.event === 'checker' && e.round !== 'comms') {
      s.checker.state = 'done'; s.checker.runs += 1
      checker = e.passed ? 'passed' : `${e.issues?.length ?? 0} issue(s) found`
    }
  }
  return { s, checker }
}

function line(e: RunEvent): { cls: string; text: string } | null {
  const who = e.agent ? AGENTS[e.agent]?.title ?? e.agent : ''
  switch (e.event) {
    case 'run_start': return { cls: 'ok', text: 'Staff meeting started. All stats are from before first pitch.' }
    case 'agent_start': return { cls: '', text: `▶ ${who} is on it` }
    case 'tool_result': {
      const args = Object.entries(e.args ?? {}).map(([k, v]) => `${k}=${Array.isArray(v) ? `[${v.length} players]` : v}`).join(', ')
      return { cls: '', text: `   ${who} → ${e.tool}(${args})` }
    }
    case 'tool_error': return { cls: 'warn', text: `   ${who} → ${e.tool} refused: ${e.error}` }
    case 'model_step': return e.gateway_cache === 'HIT' ? { cls: 't', text: `   ${who}: answer replayed from Portkey cache` } : null
    case 'agent_end': return { cls: 'ok', text: `✔ ${who} done (${e.seconds}s, ${e.steps} model calls)` }
    case 'checker':
      if (e.round === 'comms') return { cls: 'warn', text: '✱ Checker: briefing fixed' }
      return e.passed ? { cls: 'ok', text: `✱ Consistency checker round ${e.round}: PASS` }
        : { cls: 'bad', text: `✱ Consistency checker round ${e.round}: ${(e.issues ?? []).map((i) => i.message).join(' | ')}` }
    case 'manager_review': return e.approved ? { cls: 'ok', text: '★ Manager approved the plan' }
      : { cls: 'warn', text: `★ Manager sent fixes: ${(e.fixes ?? []).map((f) => `${f.to}: ${f.instruction}`).join(' | ')}` }
    case 'fix_round': return { cls: 'warn', text: `↻ Fix round ${e.round}: ${Object.keys(e.targets ?? {}).join(', ')}` }
    case 'budget_stop': return { cls: 'bad', text: `■ Stopped by the budget cap: ${e.reason}` }
    case 'run_end': return { cls: 'ok', text: `Game plan ${String(e.status).replaceAll('_', ' ')}.` }
    default: return null
  }
}

export function BuildView({ events, error }: { events: RunEvent[]; error: string | null }) {
  const { s, checker } = useMemo(() => agentStates(events), [events])
  const feedRef = useRef<HTMLDivElement>(null)
  useEffect(() => { feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight }) }, [events.length])

  return (
    <main>
      <section className="card">
        <h2>The staff is building your game plan</h2>
        <p className="muted">Scouts and coaches work in parallel. Code checks the plan before the manager signs off; problems go back to whoever owns them (at most two rounds).</p>
        <div className="pipeline">
          {STAGES.map((st) => (
            <div className="stage" key={st.label}>
              <div className="stage-label">{st.label}</div>
              {st.agents.map((k) => {
                const a = s[k]
                const meta = AGENTS[k] ?? { title: 'Consistency checker', icon: '✅', job: 'Rules + every number checked' }
                return (
                  <div key={k} className={`agent ${a.state}`}>
                    <div className="icon">{meta.icon}</div>
                    <b>{meta.title}</b>
                    <div className="state">{a.state === 'done' && a.runs > 1 ? `done ×${a.runs}` : a.state}</div>
                    <div className="meta">
                      {k === 'checker' ? (checker || meta.job)
                        : a.state === 'waiting' ? meta.job
                        : `${a.steps} model calls · ${a.tools} tool calls${a.lastTool ? ` · ${a.lastTool}` : ''}`}
                    </div>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </section>
      {error && <div className="error">The run failed: {error}</div>}
      <section className="card">
        <h2>Live activity</h2>
        <div className="feed" ref={feedRef}>
          {events.map((e, i) => {
            const l = line(e)
            return l ? <div key={i} className={l.cls}><span className="t">[{e.t_plus_s.toFixed(1).padStart(5, ' ')}s]</span> {l.text}</div> : null
          })}
        </div>
      </section>
    </main>
  )
}
