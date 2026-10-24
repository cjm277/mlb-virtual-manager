import { useEffect, useState } from 'react'

/** Freely licensed ballpark photos (Wikimedia Commons), fetched once by scripts/fetch_team_photos.py.
 *  Every photo shown carries its credit line, as the Creative Commons licenses require. */

export interface Credit { kind: string; subject: string; author: string; license: string; license_url: string; source: string }
let cache: Promise<Record<string, Credit>> | null = null
const loadCredits = () => (cache ??= fetch('/teams/credits.json').then((r) => (r.ok ? r.json() : {})).catch(() => ({})))

export function useCredits() {
  const [credits, setCredits] = useState<Record<string, Credit>>({})
  useEffect(() => { loadCredits().then(setCredits) }, [])
  return credits
}

export const photoUrl = (teamId: number) => `/teams/${teamId}.jpg`
export const thumbUrl = (teamId: number) => `/teams/thumbs/${teamId}.jpg`

export function PhotoCredit({ teamId, credits }: { teamId: number; credits: Record<string, Credit> }) {
  const c = credits[String(teamId)]
  if (!c) return null
  return (
    <div className="photo-credit">
      {c.subject} · photo: <a href={c.source} target="_blank" rel="noreferrer">{c.author}</a>,{' '}
      {c.license_url ? <a href={c.license_url} target="_blank" rel="noreferrer">{c.license}</a> : c.license}, via Wikimedia Commons
    </div>
  )
}

/** A wide photo strip of the ballpark where the game is played, with the matchup over it. */
export function VenueBanner({ homeTeamId, title, subtitle }: { homeTeamId: number; title: string; subtitle: string }) {
  const credits = useCredits()
  return (
    <div className="venue-banner theme-fade" style={{ backgroundImage: `url(${photoUrl(homeTeamId)})` }}>
      <div className="venue-shade" />
      <div className="venue-text"><b>{title}</b><span>{subtitle}</span></div>
      <PhotoCredit teamId={homeTeamId} credits={credits} />
    </div>
  )
}

/** All 30 ballparks, faded behind the league-colored landing banner. */
export function Mosaic({ teamIds }: { teamIds: number[] }) {
  return (
    <div className="mosaic" aria-hidden="true">
      {teamIds.map((id) => <div key={id} style={{ backgroundImage: `url(${thumbUrl(id)})` }} />)}
    </div>
  )
}
