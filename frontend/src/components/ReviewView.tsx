import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { EditOptions, Plan } from '../types'
import { AGENTS } from './BuildView'
import { ChatPanel } from './ChatPanel'
import { VenueBanner } from './Photos'

const TABS = ['Lineup card', 'Pitching plan', 'Their pitchers', 'Their hitters', 'Medical', 'Game plan & briefings', 'Run details'] as const
type Tab = (typeof TABS)[number]
const x3 = (v: number | null | undefined) => (v === null || v === undefined ? '-' : v < 1 ? v.toFixed(3).replace(/^0/, '') : String(v))
const nice = (s: string) => s.replaceAll('_', ' ')

interface Draft { lineup: { slot: number; player_id: number; position: string }[]; starter: number; roles: Record<number, string>; notes: string }

function draftFrom(p: Plan): Draft {
  const lc = p.sections.lineup_card, pp = p.sections.pitching_plan
  return {
    lineup: (lc?.lineup ?? []).map((s) => ({ slot: s.slot, player_id: s.player_id, position: s.position })).sort((a, b) => a.slot - b.slot),
    starter: pp?.starter.player_id ?? 0,
    roles: Object.fromEntries((pp?.bullpen ?? []).map((b) => [b.player_id, b.role])),
    notes: p.staff_notes ?? '',
  }
}

export function ReviewView({ plan, onPlan }: { plan: Plan; onPlan: (p: Plan) => void }) {
  const [tab, setTab] = useState<Tab>('Lineup card')
  const [opts, setOpts] = useState<EditOptions | null>(null)
  const [draft, setDraft] = useState<Draft>(() => draftFrom(plan))
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api.options(plan.run_id).then(setOpts).catch((e) => setErr(String(e.message ?? e))) }, [plan.run_id])
  useEffect(() => { setDraft(draftFrom(plan)) }, [plan])

  const original = useMemo(() => draftFrom(plan), [plan])
  const dirty = JSON.stringify(draft) !== JSON.stringify(original)
  const s = plan.sections
  const issues = plan.checker.open_issues

  async function save() {
    setSaving(true); setErr(null)
    try {
      const edits: Record<string, unknown> = {}
      if (JSON.stringify(draft.lineup) !== JSON.stringify(original.lineup)) edits.lineup = draft.lineup
      if (draft.starter !== original.starter) edits.starter_id = draft.starter
      const roles = Object.fromEntries(Object.entries(draft.roles).filter(([k, v]) => original.roles[Number(k)] !== v))
      if (Object.keys(roles).length) edits.bullpen_roles = roles
      if (draft.notes !== original.notes) edits.staff_notes = draft.notes
      onPlan(await api.edit(plan.run_id, edits))
    } catch (e) { setErr(String((e as Error).message)) } finally { setSaving(false) }
  }

  const banner = issues.length ? 'review' : plan.edited ? 'edited' : plan.status === 'approved' ? 'approved' : 'review'
  const headline = issues.length ? `${issues.length} issue(s) to resolve before sending`
    : plan.edited ? 'Edited by you · re-checked by code: all rules pass'
    : plan.status === 'approved' ? `Approved by the manager · checker passed${plan.checker.fix_rounds ? ` after ${plan.checker.fix_rounds} fix round(s)` : ' first time'}`
    : `Status: ${nice(plan.status)}`
  const where = plan.game.home_away === 'home' ? 'vs' : 'at'

  return (
    <main>
      <ChatPanel plan={plan} onPlan={onPlan} blocked={dirty} />
      <VenueBanner homeTeamId={plan.game.home_away === 'home' ? plan.game.team_id : plan.game.opponent_id}
        title={`${plan.game.team} ${where} ${plan.game.opponent}`}
        subtitle={`${new Date(`${plan.game.game_date}T12:00:00`).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })} · ${plan.game.venue} · ${plan.game.day_night === 'night' ? 'night game' : 'day game'}`} />
      <div className={`status ${banner}`}>
        <div className="grow">
          <b>{headline}</b>
          {issues.length > 0 && <ul className="issues">{issues.map((i, k) => <li key={k}>[{AGENTS[i.owner]?.title ?? i.owner}] {i.message}</li>)}</ul>}
        </div>
        <div className="actions">
          <button className="btn ghost" style={{ background: '#fff' }} disabled={!dirty || saving} onClick={() => setDraft(original)}>Discard edits</button>
          <button className="btn" disabled={!dirty || saving} onClick={save}>{saving ? 'Checking…' : 'Save edits & re-check'}</button>
          <a className="btn" style={{ background: '#111', textDecoration: 'none' }} href={api.exportUrl(plan.run_id)} download>⬇ Download packets (ZIP)</a>
        </div>
      </div>
      <p className="muted">Stats: {plan.game.stats_basis} {plan.game.roster_basis ?? ''}</p>
      {err && <div className="error">{err}</div>}

      <div className="tabs">{TABS.map((t) => <button key={t} className={`tab ${tab === t ? 'on' : ''}`} onClick={() => setTab(t)}>{t}</button>)}</div>

      {tab === 'Lineup card' && s.lineup_card && (
        <div className="row">
          <div className="grow lineup-card">
            <div className="head"><span>LINEUP CARD · {plan.game.team.toUpperCase()}</span><span>vs {s.lineup_card.opposing_starter_assumed.name}</span></div>
            <table className="grid"><thead><tr><th>#</th><th>Player</th><th>Pos</th><th>Why</th></tr></thead><tbody>
              {draft.lineup.map((d, i) => {
                const spot = s.lineup_card!.lineup.find((x) => x.slot === d.slot)
                const changed = spot?.player_id !== d.player_id || spot?.position !== d.position
                return (
                  <tr key={d.slot} className={changed ? 'changed' : ''}>
                    <td><span className="slot">{d.slot}</span></td>
                    <td><select value={d.player_id} onChange={(e) => setDraft({ ...draft, lineup: draft.lineup.map((x, j) => j === i ? { ...x, player_id: Number(e.target.value) } : x) })}>
                      {(opts?.hitters ?? []).map((h) => <option key={h.player_id} value={h.player_id}>{h.name} ({h.bats}) · xwOBA {x3(h.xwoba)}</option>)}
                      {!opts?.hitters.some((h) => h.player_id === d.player_id) && <option value={d.player_id}>{spot?.name}</option>}
                    </select></td>
                    <td><select value={d.position} onChange={(e) => setDraft({ ...draft, lineup: draft.lineup.map((x, j) => j === i ? { ...x, position: e.target.value } : x) })}>
                      {(opts?.positions ?? [d.position]).map((p) => <option key={p}>{p}</option>)}
                    </select></td>
                    <td className="note">{changed ? <i>Your change. Save to re-check.</i> : spot?.reason}</td>
                  </tr>
                )
              })}
            </tbody></table>
          </div>
          <div style={{ width: 380 }}>
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Bench</h3>
              <table className="grid"><tbody>{s.lineup_card.bench.map((b) => <tr key={b.player_id}><td><b>{b.name}</b><br /><span className="muted">{nice(b.role)}: {b.note}</span></td></tr>)}</tbody></table>
              <h3>Planned moves</h3>
              <ul className="tight">{s.lineup_card.substitutions.map((m, i) => {
                const names = Object.fromEntries([...s.lineup_card!.lineup, ...s.lineup_card!.bench].map((p) => [p.player_id, p.name]))
                return <li key={i}><b>{nice(m.kind)}:</b> {names[m.bench_player_id]} for {names[m.replaces_player_id]}: {m.situation}</li>
              })}</ul>
              <p className="note">{s.lineup_card.summary}</p>
            </div>
          </div>
        </div>
      )}

      {tab === 'Pitching plan' && s.pitching_plan && (() => {
        const pp = s.pitching_plan!
        const names = Object.fromEntries(pp.bullpen.map((b) => [b.player_id, b.name]))
        return (
          <div className="row">
            <div className="grow card">
              <h3 style={{ marginTop: 0 }}>Starting pitcher</h3>
              <select value={draft.starter} onChange={(e) => setDraft({ ...draft, starter: Number(e.target.value) })} style={{ fontSize: 16, padding: 6 }}>
                {(opts?.starters ?? []).map((o) => <option key={o.player_id} value={o.player_id}>
                  {o.name} ({o.throws}HP) · {o.days_rest === null ? 'fully rested' : `${o.days_rest} days rest`}{o.ready_to_start ? '' : ' (NOT rested)'} · ERA {o.era ?? '-'}</option>)}
                {!opts?.starters.some((o) => o.player_id === draft.starter) && <option value={draft.starter}>{pp.starter.name}</option>}
              </select>
              <p className="note">{draft.starter !== original.starter ? <i>Your change. Save to re-check.</i> : pp.starter.reason}</p>
              {pp.starter.plan_written_for && <p className="muted">Pitch mix and keys below were written for {pp.starter.plan_written_for}.</p>}
              <p className="note">Target: about <b>{pp.starter.expected_innings}</b> innings, pitch-count limit <b>{pp.starter.pitch_count_limit}</b>.</p>
              <table className="grid"><thead><tr><th>Pitch</th><th>% vs LHB</th><th>% vs RHB</th><th>Purpose</th></tr></thead><tbody>
                {pp.starter.pitch_mix.map((m) => <tr key={m.pitch}><td>{m.pitch}</td><td>{m.vs_lhb_pct}</td><td>{m.vs_rhb_pct}</td><td>{m.purpose}</td></tr>)}
              </tbody></table>
              <ul className="tight">{pp.starter.keys.map((k, i) => <li key={i}>{k}</li>)}</ul>
              <h3>Game scenarios</h3>
              <table className="grid"><tbody>{pp.scenarios.map((sc) => (
                <tr key={sc.scenario}><td style={{ width: 150 }}><b>{nice(sc.scenario)}</b></td><td>{sc.plan}<br /><span className="muted">{sc.pitcher_ids.map((id) => names[id] ?? id).join(' → ')}</span></td></tr>
              ))}</tbody></table>
            </div>
            <div className="card" style={{ width: 430 }}>
              <h3 style={{ marginTop: 0 }}>Bullpen roles</h3>
              <table className="grid"><tbody>{pp.bullpen.map((b) => (
                <tr key={b.player_id} className={draft.roles[b.player_id] !== b.role ? 'changed' : ''}>
                  <td><b>{b.name}</b> ({b.throws})<br /><span className="muted">{b.note}</span></td>
                  <td><select value={draft.roles[b.player_id]} onChange={(e) => setDraft({ ...draft, roles: { ...draft.roles, [b.player_id]: e.target.value } })}>
                    {(opts?.roles ?? [b.role]).map((r) => <option key={r} value={r}>{nice(r)}</option>)}
                  </select></td>
                </tr>
              ))}</tbody></table>
            </div>
          </div>
        )
      })()}

      {tab === 'Their pitchers' && s.opposing_pitchers_report && (() => {
        const r = s.opposing_pitchers_report!
        return (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Expected starter: {r.opposing_starter.name} ({r.opposing_starter.throws}HP) <span className="chip">{r.opposing_starter.confidence}</span></h3>
            {r.opposing_starter.alternatives.length > 0 && <p className="muted">Alternatives: {r.opposing_starter.alternatives.join(', ')}</p>}
            <table className="grid"><thead><tr><th>Pitch</th><th>Usage %</th><th>Velo</th><th>Whiff %</th><th>Note</th></tr></thead><tbody>
              {r.arsenal.map((a) => <tr key={a.pitch}><td>{a.pitch}</td><td>{a.usage_pct}</td><td>{a.velo ?? '-'}</td><td>{a.whiff_pct ?? '-'}</td><td>{a.note}</td></tr>)}
            </tbody></table>
            <h3>How to attack him</h3><ul className="tight">{r.how_to_attack.map((x, i) => <li key={i}>{x}</li>)}</ul>
            <div className="row">
              {(['best_matchups', 'toughest_matchups'] as const).map((k) => (
                <div className="grow" key={k}><h3>{k === 'best_matchups' ? 'Best matchups' : 'Toughest matchups'}</h3>
                  <table className="grid"><tbody>{r[k].map((m) => <tr key={m.player_id}><td><b>{m.name}</b><br /><span className="muted">{m.note}</span></td><td>{x3(m.expected_xwoba)}</td><td><span className={`chip ${m.edge}`}>{m.edge}</span></td></tr>)}</tbody></table>
                </div>
              ))}
            </div>
            <h3>Their bullpen to watch</h3><ul className="tight">{r.bullpen_to_watch.map((b) => <li key={b.player_id}><b>{b.name}</b> ({b.throws}): {b.note}</li>)}</ul>
            <p className="note">{r.summary}</p>
          </div>
        )
      })()}

      {tab === 'Their hitters' && s.opposing_hitters_report && (() => {
        const r = s.opposing_hitters_report!
        return (
          <div className="card">
            <div className="row">
              {(['lineup_vs_rhp', 'lineup_vs_lhp'] as const).map((k) => (
                <div className="grow" key={k}><h3 style={{ marginTop: 0 }}>Their lineup vs a {k === 'lineup_vs_rhp' ? 'right' : 'left'}-hander</h3>
                  <table className="grid"><tbody>{[...r[k]].sort((a, b) => a.slot - b.slot).map((e) => <tr key={e.player_id}><td><span className="slot">{e.slot}</span></td><td>{e.name}</td><td>{e.position}</td><td>{e.bats}</td></tr>)}</tbody></table>
                </div>
              ))}
            </div>
            <h3>How to pitch them</h3>
            <table className="grid"><thead><tr><th>Hitter</th><th>Threat</th><th>xwOBA</th><th>Weakness</th><th>How to pitch him</th></tr></thead><tbody>
              {[...r.hitters].sort((a, b) => ['high', 'medium', 'low'].indexOf(a.threat) - ['high', 'medium', 'low'].indexOf(b.threat)).map((h) => (
                <tr key={h.player_id}><td><b>{h.name}</b> ({h.bats})</td><td><span className={`chip ${h.threat}`}>{h.threat}</span></td><td>{x3(h.xwoba)}</td><td>{h.weakness}</td><td>{h.how_to_pitch}</td></tr>))}
            </tbody></table>
            <p className="note">{r.summary}</p>
          </div>
        )
      })()}

      {tab === 'Medical' && s.medical_report && (
        <div className="card">
          <p className="note">{s.medical_report.summary}</p>
          <table className="grid"><thead><tr><th>Player</th><th>Status</th><th>Reason</th></tr></thead><tbody>
            {s.medical_report.statuses.map((m) => <tr key={m.player_id}><td><b>{m.name}</b></td><td><span className={`chip ${m.status}`}>{nice(m.status)}</span></td><td>{m.reason}</td></tr>)}
          </tbody></table>
        </div>
      )}

      {tab === 'Game plan & briefings' && (
        <div className="row">
          <div className="grow card">
            {s.manager_review && <>
              <h3 style={{ marginTop: 0 }}>The manager's game plan</h3><p className="note">{s.manager_review.summary}</p>
              <h3>Keys to the game</h3><ul className="tight">{s.manager_review.keys_to_the_game.map((k, i) => <li key={i}>{k}</li>)}</ul>
              <h3>Key decisions</h3><ul className="tight">{s.manager_review.key_decisions.map((k, i) => <li key={i}>{k}</li>)}</ul>
            </>}
            <h3>Your notes for the staff packet</h3>
            <textarea maxLength={2000} value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} placeholder="Anything you want the coaches to see in their packet." />
            {plan.edit_log && plan.edit_log.length > 0 && <>
              <h3>Your changes</h3><ul className="tight">{plan.edit_log.flatMap((e) => e.changes.map((c, i) => <li key={e.at + i}>{c}{e.source === 'chat' ? ' (via chat)' : ''}</li>))}</ul></>}
          </div>
          <div className="grow card">
            <h3 style={{ marginTop: 0 }}>Briefings (what each group receives)</h3>
            {(['hitters', 'pitchers', 'coaches'] as const).map((aud) => {
              const b = s[`${aud}_briefing`]
              return b && <div className="brief" key={aud}><span className="chip">{aud}</span><h4>{b.headline}</h4>
                <p className="note">{b.message}</p><ul className="tight">{b.reminders.map((r, i) => <li key={i}>{r}</li>)}</ul>
                <p className="muted">Packet: {plan.packets[aud].map(nice).join(', ')}</p></div>
            })}
          </div>
        </div>
      )}

      {tab === 'Run details' && (() => {
        const u = plan.usage, t = u.total
        return (
          <div className="card">
            <div className="kpis">
              <div className="kpi"><label>Cost (list price)</label><div>${t.cost_usd.toFixed(4)}</div></div>
              <div className="kpi"><label>Input tokens (cached)</label><div>{t.input_tokens.toLocaleString()} ({t.input_tokens ? Math.round(100 * t.cached_tokens / t.input_tokens) : 0}%)</div></div>
              <div className="kpi"><label>Output tokens</label><div>{t.output_tokens.toLocaleString()}</div></div>
              <div className="kpi"><label>Time · fix rounds</label><div>{u.seconds}s · {plan.checker.fix_rounds}</div></div>
            </div>
            <table className="grid"><thead><tr><th>Agent</th><th>Runs</th><th>Model calls</th><th>Input tokens</th><th>Cached</th><th>Output tokens</th><th>Seconds</th><th>Cost</th></tr></thead><tbody>
              {Object.entries(u.by_agent).map(([k, a]) => <tr key={k}><td>{AGENTS[k]?.title ?? k}</td><td>{a.calls}</td><td>{a.model_steps}</td><td>{a.input_tokens.toLocaleString()}</td><td>{a.cached_tokens.toLocaleString()}</td><td>{a.output_tokens.toLocaleString()}</td><td>{a.seconds}</td><td>${a.cost_usd.toFixed(5)}</td></tr>)}
              {u.chat && <tr><td>Manager's Assistant (chat edits, after the build)</td><td></td><td>{u.chat.model_steps}</td><td>{u.chat.input_tokens.toLocaleString()}</td><td>{u.chat.cached_tokens.toLocaleString()}</td><td>{u.chat.output_tokens.toLocaleString()}</td><td></td><td>${u.chat.cost_usd.toFixed(5)}</td></tr>}
            </tbody></table>
            <p className="muted">Pricing: {u.pricing_source}. Full audit trail: runs/{plan.run_id}/audit.jsonl</p>
          </div>
        )
      })()}
    </main>
  )
}
