import type { EditOptions, Game, Plan, RunEvent, RunSummary, Team, Colors } from './types'

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try { detail = (await res.json()).detail ?? detail } catch { /* not JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => call<{ api_key_found: boolean; model: string }>('/api/health'),
  teams: () => call<{ league: Colors; teams: Team[] }>('/api/teams'),
  games: (teamId: number, oppId: number) => call<Game[]>(`/api/games?team_id=${teamId}&opponent_id=${oppId}`),
  runs: () => call<RunSummary[]>('/api/runs'),
  start: (game_pk: number, team_id: number, notes: string) =>
    call<{ run_id: string }>('/api/runs', { method: 'POST', body: JSON.stringify({ game_pk, team_id, notes: notes || null }) }),
  events: (runId: string, since: number) =>
    call<{ events: RunEvent[]; next: number; done: boolean; error: string | null }>(`/api/runs/${runId}/events?since=${since}`),
  plan: (runId: string) => call<Plan>(`/api/runs/${runId}/plan`),
  options: (runId: string) => call<EditOptions>(`/api/runs/${runId}/options`),
  edit: (runId: string, edits: object) => call<Plan>(`/api/runs/${runId}/edits`, { method: 'POST', body: JSON.stringify(edits) }),
  exportUrl: (runId: string) => `/api/runs/${runId}/export`,
}
