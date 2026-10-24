import type { Team, Totals } from '../types'

interface Props {
  team: Team | null
  opponent: Team | null
  totals: Totals | null
  seconds: number | null
  live: boolean
  onHome: () => void
}

const fmt = (n: number) => n.toLocaleString('en-US')

export function Scoreboard({ totals, seconds, live }: { totals: Totals | null; seconds: number | null; live: boolean }) {
  const t = totals ?? { input_tokens: 0, cached_tokens: 0, output_tokens: 0, cost_usd: 0, model_steps: 0, gateway_cache_hits: 0 }
  const cachedPct = t.input_tokens ? Math.round((100 * t.cached_tokens) / t.input_tokens) : 0
  return (
    <div className={`scoreboard ${live ? 'live' : ''}`} title="Tokens and cost for this game plan (list price, gpt-6-luna)">
      <div><label>MODEL CALLS</label><span>{t.model_steps}</span></div>
      <div><label>TOKENS IN</label><span>{fmt(t.input_tokens)}</span></div>
      <div><label>CACHED</label><span>{cachedPct}%</span></div>
      <div><label>TOKENS OUT</label><span>{fmt(t.output_tokens)}</span></div>
      <div><label>COST</label><span>${t.cost_usd.toFixed(4)}</span></div>
      <div><label>TIME</label><span>{seconds === null ? '0s' : `${Math.round(seconds)}s`}</span></div>
    </div>
  )
}

export function TopBar({ team, opponent, totals, seconds, live, onHome }: Props) {
  return (
    <header className="topbar theme-fade">
      <div className="brand" onClick={onHome} title="Start a new game plan">
        <img src="/baseball.svg" alt="" />
        <div><b>MLB VIRTUAL MANAGER</b><small>{team ? `${team.name.toUpperCase()} DUGOUT` : 'PRE-GAME PLANNING STAFF'}</small></div>
      </div>
      {team && opponent && <div className="matchup-chip">{team.abbrev} vs {opponent.abbrev}</div>}
      <div className="spacer" />
      {(totals || live) && <Scoreboard totals={totals} seconds={seconds} live={live} />}
    </header>
  )
}
