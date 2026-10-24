import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { Game, RunSummary, Team } from '../types'

interface Props {
  teams: Team[]
  team: Team | null
  opponent: Team | null
  onTeam: (t: Team | null) => void
  onOpponent: (t: Team | null) => void
  onBuild: (game: Game, notes: string) => void
  onOpenRun: (runId: string) => void
  busy: boolean
  error: string | null
  keyMissing: boolean
}

function Badge({ t }: { t: Team }) {
  return <span className="badge" style={{ background: t.colors.primary, borderColor: t.colors.secondary }}>{t.abbrev}</span>
}

function TeamGrid({ teams, selected, disabled, onPick }: { teams: Team[]; selected: Team | null; disabled?: Team | null; onPick: (t: Team) => void }) {
  return (
    <div className="team-grid">
      {teams.map((t) => (
        <button key={t.team_id} className={`team-tile ${selected?.team_id === t.team_id ? 'selected' : ''}`}
          disabled={disabled?.team_id === t.team_id} onClick={() => onPick(t)}>
          <Badge t={t} /><span>{t.name}</span>
        </button>
      ))}
    </div>
  )
}

const dateLabel = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })

export function SetupView({ teams, team, opponent, onTeam, onOpponent, onBuild, onOpenRun, busy, error, keyMissing }: Props) {
  const [games, setGames] = useState<Game[]>([])
  const [season, setSeason] = useState(2027)
  const [game, setGame] = useState<Game | null>(null)
  const [notes, setNotes] = useState('')
  const [runs, setRuns] = useState<RunSummary[]>([])

  useEffect(() => { api.runs().then(setRuns).catch(() => setRuns([])) }, [])
  useEffect(() => {
    setGame(null)
    if (team && opponent) api.games(team.team_id, opponent.team_id).then(setGames).catch(() => setGames([]))
    else setGames([])
  }, [team, opponent])

  // Bring the next step into view after each pick.
  const scrollTo = (id: string) => setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80)
  useEffect(() => { if (team) scrollTo(opponent ? 'step-game' : 'step-opponent') }, [team, opponent])
  useEffect(() => { if (game) scrollTo('step-notes') }, [game])

  const shown = useMemo(() => games.filter((g) => g.season === season), [games, season])
  const sorted = useMemo(() => [...teams].sort((a, b) => a.name.localeCompare(b.name)), [teams])

  return (
    <main>
      <section className="hero theme-fade">
        <h1>{team ? `${team.name}: game-day prep` : 'Your pre-game coaching staff'}</h1>
        <p>Pick your club, your opponent, and a game. Seven AI staff members (a team doctor, two advance scouts, a pitching coach,
          a bench coach, the manager and clubhouse comms) build the lineup, the pitching plan and both scouting reports from
          Statcast data. Code checks every plan, and you review and edit it before anything goes to the players.</p>
        <blockquote>"Yale, economics and baseball. You're funny, Pete." (Moneyball, 2011)</blockquote>
      </section>

      {keyMissing && <div className="error">No PORTKEY_API_KEY found. Saved plans below can still be opened, but building a new plan needs the key in a .env file (see the README).</div>}

      <section className="card">
        <h2><span className="step">1</span>Your team</h2>
        <TeamGrid teams={sorted} selected={team} onPick={(t) => { onTeam(t); if (opponent?.team_id === t.team_id) onOpponent(null) }} />
      </section>

      {team && (
        <section className="card" id="step-opponent">
          <h2><span className="step">2</span>Opponent</h2>
          <TeamGrid teams={sorted} selected={opponent} disabled={team} onPick={onOpponent} />
        </section>
      )}

      {team && opponent && (
        <section className="card" id="step-game">
          <h2><span className="step">3</span>Game</h2>
          <div className="seasons">
            <button className={`pill ${season === 2027 ? 'on' : ''}`} onClick={() => setSeason(2027)}>2027 schedule (upcoming)</button>
            <button className={`pill ${season === 2026 ? 'on' : ''}`} onClick={() => setSeason(2026)}>2026 season (played)</button>
          </div>
          <p className="muted">{season === 2027
            ? 'Built on full-2026 stats and end-of-2026 rosters; the opposing starter is a projection.'
            : 'Built only on stats from before the game date, as if planning that morning.'}</p>
          {shown.length === 0 ? <p className="muted">These teams do not meet in {season}.</p> : (
            <div className="game-list">
              {shown.map((g) => (
                <button key={g.game_pk} className={`game ${game?.game_pk === g.game_pk ? 'selected' : ''}`} onClick={() => setGame(g)}>
                  <b>{dateLabel(g.game_date)}{g.game_number > 1 ? ` (game ${g.game_number})` : ''}</b>
                  <span>{g.home_away === 'home' ? 'vs' : 'at'} {opponent.abbrev} | {g.venue}</span>
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      {game && team && opponent && (
        <section className="card" id="step-notes">
          <h2><span className="step">4</span>Your notes for the staff (optional)</h2>
          <textarea maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. Give the regular catcher the day off. Prefer to save the closer if we're up by 4 or more." />
          <p className="muted">Notes are treated as information for the staff. They can't override the rules (only available players, stats only from the data).</p>
          {error && <div className="error">{error}</div>}
          <div className="actions">
            <button className="btn big" disabled={busy || keyMissing} onClick={() => onBuild(game, notes)}>
              {busy ? 'Starting…' : `Build game plan: ${team.abbrev} ${game.home_away === 'home' ? 'vs' : 'at'} ${opponent.abbrev}, ${dateLabel(game.game_date)}`}
            </button>
            <span className="muted">About 1 minute and 2 cents.</span>
          </div>
        </section>
      )}

      {runs.length > 0 && (
        <section className="card">
          <h2>Recent game plans</h2>
          <table className="recent"><tbody>
            {runs.map((r) => (
              <tr key={r.run_id} onClick={() => onOpenRun(r.run_id)}>
                <td><b>{r.game_date}</b></td><td>{r.team} vs {r.opponent}</td>
                <td>{r.status.replaceAll('_', ' ')}{r.edited ? ' (edited)' : ''}</td><td>${r.cost_usd.toFixed(4)}</td><td>Open</td>
              </tr>
            ))}
          </tbody></table>
        </section>
      )}
    </main>
  )
}
