import type { CSSProperties, ReactNode } from 'react'

/**
 * Each staff member as a little person at a desk, dressed for the job in the managed team's colors
 * (uniform pieces use the --primary / --secondary theme variables, so they change with the club).
 * Pure SVG; motion is CSS in styles.css ("Agent figures"): breathing and blinking at rest, and a
 * job-specific action while working. The consistency checker is code, so it is drawn as a laptop, not a person.
 */

export type Mood = 'waiting' | 'working' | 'done'
const INK = '#1b2434'
const P: CSSProperties = { fill: 'var(--primary)' }
const S: CSSProperties = { fill: 'var(--secondary)' }
const TORSO = 'M44 136 L44 98 Q44 80 62 76 L98 76 Q116 80 116 98 L116 136 Z'

const cap = (
  <g>
    <path d="M59 39 Q59 17 80 17 Q101 17 101 39 Z" style={P} />
    <circle cx="80" cy="18" r="2.2" style={S} />
    <circle cx="80" cy="29" r="4.2" style={S} />
    <path d="M56 39 Q80 33 104 39 Q104 44 80 42 Q56 44 56 39 Z" style={P} opacity={0.85} />
  </g>
)

interface Look { skin: string; sleeve: string | CSSProperties; torso: ReactNode; hair?: ReactNode; hairBack?: ReactNode; hat?: ReactNode; face?: ReactNode; prop: ReactNode; propFront?: boolean }

const LOOKS: Record<string, Look> = {
  team_doctor: {
    skin: '#8d5524', sleeve: '#f7f7f4',
    hairBack: <ellipse cx="80" cy="36" rx="25" ry="20" fill="#2a1a12" />,
    hair: <><path d="M60 46 Q57 22 80 21 Q103 22 100 46 Q96 32 80 30 Q64 32 60 46 Z" fill="#2a1a12" /><circle cx="80" cy="16" r="8" fill="#2a1a12" /></>,
    torso: (<>
      <path d={TORSO} fill="#f7f7f4" />
      <path d="M68 76 L80 96 L92 76 Z" style={P} />
      <path d="M62 78 L74 112 L66 118 Z M98 78 L86 112 L94 118 Z" fill="#e4e4de" />
      <path d="M66 80 Q60 104 74 106 M94 80 Q100 104 86 106" fill="none" stroke="#5d6779" strokeWidth="2.2" />
      <circle cx="80" cy="108" r="4" fill="#9aa5b1" stroke="#5d6779" strokeWidth="1.5" />
      <rect x="97" y="96" width="12" height="9" rx="1.5" fill="#ffffff" stroke="#c9d3e0" />
    </>),
    prop: (
      <g className="prop">
        <rect x="14" y="98" width="28" height="26" rx="2" fill="#a8754f" />
        <rect x="17" y="102" width="22" height="20" fill="#ffffff" />
        <path d="M26 104 h4 v4 h4 v4 h-4 v4 h-4 v-4 h-4 v-4 h4 Z" fill="#d32f2f" />
        <rect x="23" y="96" width="10" height="5" rx="1.5" fill="#9aa5b1" />
        <path className="pen" d="M112 122 L126 104" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
      </g>
    ),
  },
  scout_pitchers: {
    skin: '#f1c27d', sleeve: P,
    hair: <path d="M61 46 Q60 38 64 36 L96 36 Q100 38 99 46 Q96 40 80 40 Q64 40 61 46 Z" fill="#6b4423" />,
    hat: cap,
    face: <g><rect x="66" y="43" width="12" height="8" rx="3" fill="#1b2434" /><rect x="82" y="43" width="12" height="8" rx="3" fill="#1b2434" /><path d="M78 46 h4" stroke="#1b2434" strokeWidth="1.6" /></g>,
    torso: (<>
      <path d={TORSO} style={P} />
      <path d="M70 76 L80 90 L90 76 Z" fill="#ffffff" />
      <rect x="92" y="94" width="12" height="9" rx="1" style={S} />
    </>),
    propFront: true,
    prop: (
      <g className="prop prop-radar">
        <path d="M100 100 h28 a4 4 0 0 1 4 4 v8 a4 4 0 0 1 -4 4 h-16 l-4 10 h-8 l2 -10 h-2 a4 4 0 0 1 -4 -4 v-8 a4 4 0 0 1 4 -4 Z" fill="#37474f" />
        <circle cx="132" cy="108" r="5" fill="#263238" stroke="#90a4ae" strokeWidth="1.2" />
        <rect x="104" y="103" width="16" height="9" rx="1" fill="#0d1b0d" />
        <text className="radar-digits" x="118.5" y="110.5" textAnchor="end" fontSize="7.5" fontFamily="monospace" fontWeight="700" fill="#7CFC00">97</text>
      </g>
    ),
  },
  scout_hitters: {
    skin: '#c68642', sleeve: S,
    hair: <path d="M61 44 Q58 18 80 18 Q102 18 99 44 Q97 30 80 28 Q63 30 61 44 Z" fill="#1a1110" />,
    hat: <g><path d="M58 33 Q80 27 102 33 L102 37 Q80 31 58 37 Z" style={P} /><path d="M58 36 Q80 30 102 36 Q108 42 80 41 Q52 42 58 36 Z" style={P} opacity={0.85} /></g>,
    torso: (<>
      <path d={TORSO} style={S} />
      <path d="M72 76 L80 86 L88 76 Z" fill="#ffffff" />
      <path d="M80 86 V100" stroke="#ffffff" strokeWidth="1.4" />
    </>),
    propFront: true,
    prop: (
      <g className="prop">
        <g className="stopwatch">
          <circle cx="28" cy="112" r="11" fill="#eceff1" stroke="#90a4ae" strokeWidth="2" />
          <rect x="26" y="98" width="4" height="4" fill="#90a4ae" />
          <path className="hand" d="M28 112 L28 104" stroke="#d32f2f" strokeWidth="1.6" strokeLinecap="round" />
        </g>
        <rect x="64" y="104" width="34" height="20" rx="1.5" fill="#fffdf2" stroke="#c9b98a" />
        <path d="M68 110 h26 M68 114 h22 M68 118 h24" stroke="#9aa5b1" strokeWidth="1.1" />
        <path className="pen" d="M100 122 L112 106" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
      </g>
    ),
  },
  pitching_coach: {
    skin: '#ffdbac', sleeve: '#ffffff',
    hair: <path d="M61 46 Q60 38 64 36 L96 36 Q100 38 99 46 Q96 40 80 40 Q64 40 61 46 Z" fill="#9e9e9e" />,
    hat: cap,
    face: <path d="M68 58 Q80 68 92 58 Q90 66 80 67 Q70 66 68 58 Z" fill="#9e9e9e" opacity={0.85} />,
    torso: (<>
      <path d={TORSO} fill="#ffffff" />
      <path d="M62 76 L80 96 L98 76" fill="none" style={{ stroke: 'var(--primary)' }} strokeWidth="3" />
      <path d="M80 96 V136" style={{ stroke: 'var(--primary)' }} strokeWidth="2" />
      <text x="96" y="118" textAnchor="middle" fontSize="14" fontWeight="900" style={P}>34</text>
    </>),
    prop: (
      <g className="prop prop-ball">
        <circle cx="128" cy="104" r="7" fill="#ffffff" stroke="#c9d3e0" />
        <path d="M123 99 q3 5 0 10 M133 99 q-3 5 0 10" fill="none" stroke="#d32f2f" strokeWidth="1.1" />
      </g>
    ),
  },
  bench_coach: {
    skin: '#e0ac69', sleeve: '#b9bec6',
    hair: <path d="M61 46 Q60 38 64 36 L96 36 Q100 38 99 46 Q96 40 80 40 Q64 40 61 46 Z" fill="#2b1d14" />,
    hat: cap,
    torso: (<>
      <path d={TORSO} fill="#b9bec6" />
      <path d="M68 76 L80 92 L92 76" fill="none" style={{ stroke: 'var(--primary)' }} strokeWidth="3" />
      <text x="80" y="112" textAnchor="middle" fontSize="11" fontWeight="900" style={P}>COACH</text>
    </>),
    propFront: true,
    prop: (
      <g className="prop">
        <rect x="60" y="100" width="40" height="24" rx="1.5" fill="#fffdf2" stroke="var(--primary)" />
        <rect x="60" y="100" width="40" height="5" style={P} />
        {[0, 1, 2, 3].map((i) => <path key={i} d={`M64 ${109 + i * 3.6} h30`} stroke="#9aa5b1" strokeWidth="1" />)}
        <path className="pen" d="M102 122 L116 104" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
      </g>
    ),
  },
  manager: {
    skin: '#5c3a21', sleeve: P,
    hair: <path d="M61 46 Q60 38 64 36 L96 36 Q100 38 99 46 Q96 40 80 40 Q64 40 61 46 Z" fill="#cfcfcf" />,
    hat: cap,
    face: <path d="M66 54 Q80 72 94 54 Q92 68 80 69 Q68 68 66 54 Z" fill="#cfcfcf" />,
    torso: (<>
      <path d={TORSO} style={P} />
      <path d="M48 112 h64" style={{ stroke: 'var(--secondary)' }} strokeWidth="4" />
      <path d="M72 76 L80 84 L88 76 Z" fill="#ffffff" />
      <path d="M80 84 V104" stroke="#ffffff" strokeWidth="2" />
    </>),
    prop: (
      <g className="prop prop-mug">
        <g className="mug">
          <path d="M120 104 h16 v16 q0 4 -4 4 h-8 q-4 0 -4 -4 Z" fill="#ffffff" stroke="#c9d3e0" strokeWidth="1.5" />
          <path d="M136 108 q7 0 7 6 q0 6 -7 6" fill="none" stroke="#c9d3e0" strokeWidth="2.5" />
          <rect x="122" y="110" width="12" height="5" style={S} />
          <path className="steam" d="M125 100 q-3 -4 0 -8 q3 -4 0 -8 M131 100 q-3 -4 0 -8 q3 -4 0 -8" fill="none" stroke="#c9d3e0" strokeWidth="1.6" strokeLinecap="round" />
        </g>
        <path d="M16 124 L20 104 L36 104 L40 124 Z" fill="#ffca28" />
        <rect x="18" y="108" width="20" height="7" fill="#ffffff" />
        <text x="28" y="113.5" textAnchor="middle" fontSize="4.5" fontWeight="900" fill="#2e7d32">SEEDS</text>
      </g>
    ),
  },
  clubhouse_comms: {
    skin: '#f1c27d', sleeve: '#6d4c41',
    hairBack: <path d="M58 40 Q56 74 66 80 L94 80 Q104 74 102 40 Z" fill="#b5651d" />,
    hair: <path d="M60 46 Q57 20 80 19 Q103 20 100 46 Q96 30 80 28 Q64 30 60 46 Z" fill="#b5651d" />,
    face: (<g>
      <path d="M60 46 Q60 18 80 18 Q100 18 100 46" fill="none" stroke="#263238" strokeWidth="3" />
      <rect x="55" y="41" width="8" height="13" rx="3" fill="#263238" />
      <rect x="97" y="41" width="8" height="13" rx="3" fill="#263238" />
      <path d="M59 53 Q60 62 72 61" fill="none" stroke="#263238" strokeWidth="2" />
      <circle cx="73" cy="61" r="2.4" style={S} />
      <g className="soundwaves" fill="none" style={{ stroke: 'var(--secondary)' }} strokeWidth="1.6" strokeLinecap="round">
        <path d="M50 58 q-4 4 0 8" /><path d="M45 55 q-6 7 0 14" />
      </g>
    </g>),
    torso: (<>
      <path d={TORSO} fill="#6d4c41" />
      <path d="M68 76 L80 100 L92 76 Z" fill="#f7f5ef" />
      <path d="M72 78 L80 112 L88 78" fill="none" style={{ stroke: 'var(--primary)' }} strokeWidth="2.2" />
      <rect x="75" y="110" width="10" height="13" rx="1.5" fill="#ffffff" stroke="var(--primary)" />
    </>),
    prop: (
      <g className="prop">
        <rect x="112" y="98" width="30" height="24" rx="3" fill="#263238" />
        <rect x="115" y="101" width="24" height="18" rx="1" fill="#e3f2fd" />
        <path d="M120 108 l6 -3 v10 l-6 -3 Z M126 106 l6 -3 v14 l-6 -3" style={P} />
      </g>
    ),
  },
  assistant: {
    skin: '#c68642', sleeve: P,
    hair: <path d="M61 45 Q57 24 72 22 Q80 18 88 22 Q103 24 99 45 Q97 34 92 31 Q86 35 80 31 Q74 35 68 31 Q63 36 61 45 Z" fill="#1a1110" />,
    face: <g fill="none" stroke={INK} strokeWidth="1.4"><rect x="67" y="43" width="11" height="9" rx="3" /><rect x="82" y="43" width="11" height="9" rx="3" /><path d="M78 47 h4" /></g>,
    torso: (<>
      <path d={TORSO} style={P} />
      <path d="M74 76 L80 70 L86 76 L80 92 Z" fill="#ffffff" />
      <path d="M80 76 V104" stroke="#d0d6de" strokeWidth="2" />
      <circle cx="80" cy="100" r="2" fill="#d0d6de" />
    </>),
    propFront: true,
    prop: (
      <g className="prop">
        <rect x="62" y="98" width="36" height="26" rx="3" fill="#263238" />
        <rect x="65" y="101" width="30" height="20" rx="1" fill="#f5f7fa" />
        <rect className="bubble b1" x="67" y="103" width="16" height="5" rx="2.5" style={S} />
        <rect className="bubble b2" x="76" y="110" width="17" height="5" rx="2.5" style={P} />
      </g>
    ),
  },
}

export function CheckerFigure({ mood }: { mood: Mood }) {
  return (
    <svg className={`figure figure-checker is-${mood}`} viewBox="0 0 160 136" role="img" aria-label={`consistency checker (code), ${mood}`}>
      <path d="M38 40 h84 a4 4 0 0 1 4 4 v56 h-92 v-56 a4 4 0 0 1 4 -4 Z" fill="#263238" />
      <rect x="40" y="44" width="80" height="52" fill="#101418" />
      {[0, 1, 2, 3, 4].map((i) => <rect key={i} className={`code-line l${i}`} x={46} y={50 + i * 8} width={[40, 56, 30, 48, 36][i]} height="3.2" rx="1.6" fill={['#7bd88f', '#ffd23f', '#9ecbff', '#7bd88f', '#ff9f80'][i]} />)}
      <g className="check-mark"><circle cx="104" cy="80" r="10" fill="#1f8a4c" /><path d="M99 80 l4 4 l7 -8" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></g>
      <path d="M26 100 h108 l-8 12 h-92 Z" fill="#90a4ae" />
      <rect x="0" y="124" width="160" height="12" fill="#a8754f" /><rect x="0" y="124" width="160" height="2.5" fill="#c4916a" />
    </svg>
  )
}

export default function AgentFigure({ agent, mood }: { agent: string; mood: Mood }) {
  if (agent === 'checker') return <CheckerFigure mood={mood} />
  const look = LOOKS[agent]
  if (!look) return null
  const sleeve = typeof look.sleeve === 'string' ? { stroke: look.sleeve } : { stroke: 'var(--primary)' }
  return (
    <svg className={`figure figure-${agent} is-${mood}`} viewBox="0 0 160 136" role="img" aria-label={`${agent.replace('_', ' ')}, ${mood}`}>
      <rect x="40" y="56" width="80" height="78" rx="16" fill="#1b2f4f" />
      <rect x="46" y="62" width="68" height="70" rx="12" fill="#22395e" />
      <g className="body">
        <g className="torso">{look.torso}</g>
        <rect x="72" y="62" width="16" height="17" rx="5" fill={look.skin} />
        <g className="head">
          {look.hairBack}
          <circle cx="60.5" cy="49" r="5" fill={look.skin} />
          <circle cx="99.5" cy="49" r="5" fill={look.skin} />
          <ellipse cx="80" cy="47" rx="19.5" ry="21.5" fill={look.skin} />
          {look.hair}
          <g className="eyes" fill={INK}><ellipse cx="73" cy="48" rx="2.2" ry="2.5" /><ellipse cx="87" cy="48" rx="2.2" ry="2.5" /></g>
          <path d="M69.5 42 q3.5 -2 7 0 M83.5 42 q3.5 -2 7 0" fill="none" stroke={INK} strokeWidth="1.3" strokeLinecap="round" opacity="0.7" />
          <ellipse cx="68" cy="55" rx="3" ry="1.8" fill="#e57373" opacity="0.25" />
          <ellipse cx="92" cy="55" rx="3" ry="1.8" fill="#e57373" opacity="0.25" />
          <path className="smile" d="M74 57.5 Q80 62.5 86 57.5" fill="none" stroke="#7a3b2e" strokeWidth="1.8" strokeLinecap="round" />
          <ellipse className="talk" cx="80" cy="59" rx="3.4" ry="2.6" fill="#7a3b2e" />
          {look.face}
          {look.hat}
        </g>
      </g>
      {!look.propFront && look.prop}
      <g className="arm arm-l">
        <path d="M52 86 Q44 104 48 116 L62 121" fill="none" style={sleeve} strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="63" cy="121" r="5.8" fill={look.skin} />
      </g>
      <g className="arm arm-r">
        <path d="M108 86 Q116 104 112 116 L98 121" fill="none" style={sleeve} strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="97" cy="121" r="5.8" fill={look.skin} />
      </g>
      {look.propFront && look.prop}
      <rect x="0" y="124" width="160" height="12" fill="#a8754f" />
      <rect x="0" y="124" width="160" height="2.5" fill="#c4916a" />
    </svg>
  )
}
