import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { ChatTurn, Plan } from '../types'
import AgentFigure from './AgentFigure'

const SUGGESTIONS = ["I don't like our 8th hitter in this matchup.", 'Why is our cleanup hitter batting 4th?',
  'Who should close if our closer is unavailable?', 'Add a note: hold the runner at first in the late innings.']

/** Chat with the Manager's Assistant: explain the plan, or change it in words instead of dropdowns. */
export function ChatPanel({ plan, onPlan, blocked }: { plan: Plan; onPlan: (p: Plan) => void; blocked: boolean }) {
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const body = useRef<HTMLDivElement>(null)

  useEffect(() => { api.chatHistory(plan.run_id).then(setTurns).catch(() => setTurns([])) }, [plan.run_id])
  useEffect(() => { body.current?.scrollTo({ top: body.current.scrollHeight, behavior: 'smooth' }) }, [turns.length, busy, open])

  async function send(message: string) {
    if (!message.trim() || busy) return
    setBusy(true); setErr(null); setText('')
    setTurns((t) => [...t, { role: 'manager', text: message }])
    try {
      const r = await api.chat(plan.run_id, message)
      setTurns(r.history)
      onPlan(r.plan)
    } catch (e) {
      setErr(String((e as Error).message)); setTurns((t) => t.slice(0, -1)); setText(message)
    } finally { setBusy(false) }
  }

  if (!open) {
    return (
      <button className="chat-fab" onClick={() => setOpen(true)} title="Explain or change the plan in plain words">
        <span className="mini"><AgentFigure agent="assistant" mood="waiting" /></span>
        Ask your assistant coach
      </button>
    )
  }
  return (
    <div className="chat">
      <div className="chat-head">
        <div className="who"><AgentFigure agent="assistant" mood={busy ? 'working' : 'done'} /></div>
        <div><b>Manager's Assistant</b><small>Tell me what to change, or ask why. Every change is re-checked by code before it's saved.</small></div>
        <button onClick={() => setOpen(false)} aria-label="Close chat">×</button>
      </div>
      <div className="chat-body" ref={body}>
        {turns.length === 0 && <div className="msg assistant">Hi skip. Want a different look at second base, a new closer, or just the reasoning behind a call? Ask me in plain words.</div>}
        {turns.map((t, i) => (
          <div key={i} className={`msg ${t.role}`}>
            {t.text}
            {t.changes && t.changes.length > 0 && <ul className="changes">{t.changes.map((c, j) => <li key={j}>{c}</li>)}</ul>}
            {t.role === 'assistant' && t.status === 'changed' && <div className="verdict ok">✓ Saved: the plan passed every rule check</div>}
            {t.role === 'assistant' && t.status === 'rejected' && <div className="verdict no">✗ Not saved: {t.issues?.map((x) => x.message).join(' ')}</div>}
            {t.role === 'assistant' && t.status === 'answered' && <div className="verdict info">No changes to the plan</div>}
          </div>
        ))}
        {busy && <div className="typing">The assistant is checking the numbers…</div>}
      </div>
      {turns.length === 0 && !busy && (
        <div className="chat-suggest">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} disabled={blocked}>{s}</button>)}</div>
      )}
      {err && <div className="error" style={{ margin: '0 10px' }}>{err}</div>}
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(text) }}>
        <input value={text} maxLength={500} disabled={busy || blocked} onChange={(e) => setText(e.target.value)}
          placeholder={blocked ? 'Save or discard your dropdown edits first' : 'e.g. I don\'t like Clement in this matchup'} />
        <button className="btn" disabled={busy || blocked || !text.trim()}>Send</button>
      </form>
    </div>
  )
}
