export interface Colors { primary: string; secondary: string; on_primary: string }
export interface Team { team_id: number; name: string; abbrev: string; team_name: string; league: string; division: string; colors: Colors }
export interface Game { game_pk: number; season: number; game_date: string; game_number: number; home_away: 'home' | 'away'; venue: string }

export interface RunEvent {
  event: string; t_plus_s: number; agent?: string; tool?: string; args?: Record<string, unknown>; error?: string
  step?: number; seconds?: number; steps?: number; input_tokens?: number; cached_tokens?: number; output_tokens?: number
  cost_usd?: number; gateway_cache?: string; round?: number | string; passed?: boolean; approved?: boolean
  issues?: Issue[]; fixes?: { to: string; instruction: string }[]; targets?: Record<string, string[]>; status?: string; reason?: string
  totals?: Totals; title?: string
}
export interface Issue { owner: string; code: string; message: string }
export interface Totals { model_steps: number; gateway_cache_hits: number; input_tokens: number; cached_tokens: number; output_tokens: number; cost_usd: number }
export interface AgentUsage extends Totals { calls: number; seconds: number }

export interface LineupSpot { slot: number; player_id: number; name: string; position: string; bats: string; reason: string }
export interface BenchRole { player_id: number; name: string; role: string; note: string }
export interface Substitution { kind: string; situation: string; bench_player_id: number; replaces_player_id: number; reason: string }
export interface LineupPlan { opposing_starter_assumed: { player_id: number; name: string }; lineup: LineupSpot[]; bench: BenchRole[]; substitutions: Substitution[]; summary: string }
export interface PitchMix { pitch: string; vs_lhb_pct: number; vs_rhb_pct: number; purpose: string }
export interface StarterPlan { player_id: number; name: string; throws: string; reason: string; expected_innings: number; pitch_count_limit: number; pitch_mix: PitchMix[]; keys: string[]; plan_written_for?: string }
export interface BullpenRole { player_id: number; name: string; throws: string; role: string; note: string }
export interface Scenario { scenario: string; plan: string; pitcher_ids: number[] }
export interface PitchingPlan { starter: StarterPlan; bullpen: BullpenRole[]; scenarios: Scenario[]; summary: string }
export interface MatchupNote { player_id: number; name: string; expected_xwoba: number; edge: string; note: string }
export interface PitchersReport {
  opposing_starter: { player_id: number; name: string; throws: string; confidence: string; alternatives: string[] }
  arsenal: { pitch: string; usage_pct: number; velo: number | null; whiff_pct: number | null; note: string }[]
  how_to_attack: string[]; best_matchups: MatchupNote[]; toughest_matchups: MatchupNote[]
  bullpen_to_watch: { player_id: number; name: string; throws: string; note: string }[]; summary: string
}
export interface LineupEntry { slot: number; player_id: number; name: string; position: string; bats: string }
export interface HittersReport {
  lineup_vs_rhp: LineupEntry[]; lineup_vs_lhp: LineupEntry[]
  hitters: { player_id: number; name: string; bats: string; threat: string; xwoba: number | null; weakness: string; how_to_pitch: string }[]
  summary: string
}
export interface MedicalReport { statuses: { player_id: number; name: string; status: string; reason: string }[]; summary: string }
export interface ManagerReview { approved: boolean; key_decisions: string[]; keys_to_the_game: string[]; summary: string }
export interface Briefing { audience: string; headline: string; message: string; reminders: string[] }

export interface Plan {
  run_id: string; status: string; edited?: boolean; staff_notes?: string; manager_notes?: string | null
  edit_log?: { at: string; changes: string[] }[]
  game: { game_pk: number; season: number; game_date: string; venue: string; team: string; team_id: number; opponent: string; opponent_id: number; home_away: string; stats_basis: string; roster_basis?: string; day_night: string }
  sections: {
    lineup_card: LineupPlan | null; pitching_plan: PitchingPlan | null; opposing_pitchers_report: PitchersReport | null
    opposing_hitters_report: HittersReport | null; medical_report: MedicalReport | null; manager_review: ManagerReview | null
    hitters_briefing: Briefing | null; pitchers_briefing: Briefing | null; coaches_briefing: Briefing | null
  }
  packets: Record<string, string[]>
  checker: { fix_rounds: number; open_issues: Issue[]; rechecked_after_edit?: boolean }
  usage: { seconds: number; total: Totals; by_agent: Record<string, AgentUsage>; pricing_source: string }
}

export interface EditOptions {
  hitters: { player_id: number; name: string; bats: string; position: string; starts_by_position: Record<string, number>; xwoba: number | null }[]
  starters: { player_id: number; name: string; throws: string; days_rest: number | null; ready_to_start: boolean; era: number | null; starts: number }[]
  roles: string[]; positions: string[]
}
export interface RunSummary { run_id: string; status: string; game_date: string; team: string; opponent: string; cost_usd: number; edited: boolean }
