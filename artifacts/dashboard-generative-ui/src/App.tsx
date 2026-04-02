import {
  Activity,
  ArrowRight,
  Bot,
  BrainCircuit,
  Flame,
  Orbit,
  Radar,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from 'lucide-react'
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useState,
} from 'react'
import './App.css'

type Lens = 'operator' | 'research' | 'risk'
type ExperimentAction = 'start' | 'pause' | 'resume' | 'restart' | 'stop'

type DashboardPayload = {
  meta?: {
    generated_at?: string
    strategy_spec?: string
  }
  actions?: Array<{
    title?: string
    detail?: string
  }>
  paper?: {
    positions?: Array<{
      symbol?: string
      direction?: string
      notional?: number
      entry_price?: number
    }>
    portfolio?: {
      equity?: number
      timestamp?: string
    }
  }
  experiment_events?: ExperimentEvent[]
  experiments?: Experiment[]
  workbench?: {
    experiment_manager?: {
      summary?: {
        active_count?: number
        decision_counts?: Record<string, number>
        degraded_count?: number
        drift_count?: number
        experiment_count?: number
        failed_count?: number
        leader_id?: string | null
        leader_score?: number | null
        manager_state?: string
        phase_counts?: Record<string, number>
      }
      state?: string
    }
  }
}

type Experiment = {
  id?: string
  hypothesis?: string
  state?: string
  desired_state?: string
  phase?: string
  phase_detail?: string
  search_space?: string
  symbols?: string[]
  health?: string
  degraded?: boolean
  degraded_reasons?: string[]
  health_reasons?: string[]
  best_score?: number | null
  iteration?: number
  cycle_runtime_seconds?: number
  last_completed_at?: string
  last_metrics?: {
    score?: number
  }
  last_decision?: {
    status?: string
    reason?: string
  }
  last_verification?: {
    failed_gates?: string[]
  }
}

type ExperimentEvent = {
  type?: string
  timestamp?: string
  experiment_id?: string
  payload?: {
    phase?: string
    phase_detail?: string
    health?: string
    search_space?: string
    decision?: {
      status?: string
    }
  }
}

type NarrativeBlock = {
  eyebrow: string
  headline: string
  summary: string
  bulletA: string
  bulletB: string
  bulletC: string
}

type OpportunityCard = {
  id: string
  tone: 'accent' | 'warn' | 'danger'
  title: string
  detail: string
  suggestion: string
  action?: ExperimentAction
  actionLabel?: string
}

const REFRESH_MS = 10000
const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

const lensMeta: Record<
  Lens,
  { label: string; note: string; icon: typeof Orbit }
> = {
  operator: {
    label: 'Operator',
    note: 'Favor interventions that stabilize and unblock the room.',
    icon: Radar,
  },
  research: {
    label: 'Research',
    note: 'Prioritize which hypotheses deserve more iteration budget.',
    icon: BrainCircuit,
  },
  risk: {
    label: 'Risk',
    note: 'Surface the stress points before they become false confidence.',
    icon: ShieldAlert,
  },
}

function scoreOf(experiment: Experiment): number | null {
  if (typeof experiment.best_score === 'number') {
    return experiment.best_score
  }
  if (typeof experiment.last_metrics?.score === 'number') {
    return experiment.last_metrics.score
  }
  return null
}

function money(value: number | undefined): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? currency.format(value)
    : '--'
}

function decimal(value: number | null | undefined, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toFixed(digits)
    : '--'
}

function stamp(value: string | undefined): string {
  if (!value) return '--'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      })
}

function stateTone(experiment: Experiment): 'accent' | 'warn' | 'danger' {
  if (experiment.degraded || experiment.health === 'failed') return 'danger'
  if (experiment.state === 'paused' || experiment.health === 'degraded') return 'warn'
  return 'accent'
}

function recommendationFor(experiment: Experiment): OpportunityCard {
  const id = experiment.id || 'unknown-thread'
  const score = scoreOf(experiment)
  const failedGates = experiment.last_verification?.failed_gates || []

  if (experiment.degraded || failedGates.length) {
    return {
      id,
      tone: 'danger',
      title: `${id} needs a reset path`,
      detail:
        failedGates.length > 0
          ? `Verifier blocked ${failedGates.join(', ')} and the thread should be restarted with a narrower acceptance envelope.`
          : 'Health flags are active, which makes the current state too noisy to trust.',
      suggestion: 'Restart the thread and inspect the most recent degraded reasons before letting it re-enter the pool.',
      action: 'restart',
      actionLabel: 'Restart thread',
    }
  }

  if (experiment.state === 'stopped') {
    return {
      id,
      tone: 'accent',
      title: `${id} is idle inventory`,
      detail: 'The hypothesis is offline even though it still occupies semantic space in the room.',
      suggestion: 'Start it if the search space is still relevant, otherwise leave it out of the active rotation.',
      action: 'start',
      actionLabel: 'Start thread',
    }
  }

  if (experiment.state === 'paused') {
    return {
      id,
      tone: 'warn',
      title: `${id} is paused with unfinished context`,
      detail: 'The thread has recent context but is not consuming more cycle budget right now.',
      suggestion: 'Resume it if the thesis still diversifies the leader rather than duplicating it.',
      action: 'resume',
      actionLabel: 'Resume thread',
    }
  }

  if (typeof score === 'number' && score < 0) {
    return {
      id,
      tone: 'warn',
      title: `${id} is burning cycle budget`,
      detail: `Current score is ${decimal(score)} and the thread is not earning live attention.`,
      suggestion: 'Pause it and fold the failure mode into the next prompt or verifier gate.',
      action: 'pause',
      actionLabel: 'Pause thread',
    }
  }

  return {
    id,
    tone: 'accent',
    title: `${id} is behaving like a keeper`,
    detail: 'No intervention is needed right now; the thread is compounding useful signal.',
    suggestion: 'Let it run and compare its phase cadence against the rest of the room.',
  }
}

function narrativeFor(payload: DashboardPayload, lens: Lens): NarrativeBlock {
  const summary = payload.workbench?.experiment_manager?.summary || {}
  const experiments = payload.experiments || []
  const paperEquity = payload.paper?.portfolio?.equity
  const activeCount = summary.active_count ?? 0
  const degradedCount = summary.degraded_count ?? 0
  const failedCount = summary.failed_count ?? 0
  const leaderId = summary.leader_id || 'no leader yet'
  const leaderScore = summary.leader_score
  const openPositions = payload.paper?.positions || []
  const scores = experiments
    .map((experiment) => scoreOf(experiment))
    .filter((value): value is number => typeof value === 'number')
    .sort((left, right) => right - left)
  const medianScore =
    scores.length > 0 ? scores[Math.floor(scores.length / 2)] : null

  if (lens === 'research') {
    return {
      eyebrow: 'Research Lens',
      headline: `${leaderId} is the benchmark, but the room still has headroom.`,
      summary: `The current leader is sitting at ${decimal(
        leaderScore,
      )} while the median tracked score is ${decimal(
        medianScore,
      )}. This lens biases toward experiments that widen the search surface rather than merely matching the incumbent.`,
      bulletA: `Highest leverage move: compare the leader against the strongest non-leader search space and decide whether you have real diversification or a disguised clone.`,
      bulletB: `Operator context: ${activeCount} threads are live, which is enough to explore but still small enough to keep prompt drift visible.`,
      bulletC: `Paper context: ${money(
        paperEquity,
      )} in equity means the room is not abstract; every false positive eventually reaches live operator attention.`,
    }
  }

  if (lens === 'risk') {
    return {
      eyebrow: 'Risk Lens',
      headline: `The room is only as trustworthy as its weakest thread.`,
      summary: `${degradedCount} degraded and ${failedCount} failed threads are the pressure points. This lens privileges intervention over discovery and looks for stale status, verifier misses, and score decay before they become narrative momentum.`,
      bulletA: `Immediate check: ${openPositions.length} paper positions are open, so execution state can diverge from research state if the dashboard gets noisy.`,
      bulletB: `Leader dependency: ${leaderId} should not be allowed to monopolize confidence without a healthy challenger behind it.`,
      bulletC: `The safest habit here is to restart unhealthy threads fast and only then re-read their hypotheses.`,
    }
  }

  return {
    eyebrow: 'Operator Lens',
    headline: `${leaderId} is steering the room while ${activeCount} threads stay in motion.`,
    summary: `The control plane is currently watching ${activeCount} active hypotheses with ${degradedCount} degraded and ${failedCount} failed. This lens optimizes for smooth, confident intervention rather than deep post-hoc analysis.`,
    bulletA: `Paper equity is ${money(
      paperEquity,
    )}, which keeps the room grounded in a live-ish outcome instead of a passive leaderboard.`,
    bulletB: `Leader score is ${decimal(
      leaderScore,
    )}; if that stays high while the rest of the room stalls, the operator should start pruning rather than just restarting.`,
    bulletC: `The best next move is usually a small number of decisive actions, not another full scan of every panel.`,
  }
}

function sortExperiments(experiments: Experiment[], lens: Lens): Experiment[] {
  return [...experiments].sort((left, right) => {
    const leftScore = scoreOf(left) ?? Number.NEGATIVE_INFINITY
    const rightScore = scoreOf(right) ?? Number.NEGATIVE_INFINITY

    if (lens === 'risk') {
      const leftRisk = Number(Boolean(left.degraded)) + Number(left.health === 'degraded')
      const rightRisk = Number(Boolean(right.degraded)) + Number(right.health === 'degraded')
      if (rightRisk !== leftRisk) return rightRisk - leftRisk
      return leftScore - rightScore
    }

    if (lens === 'operator') {
      const leftUrgency =
        Number(left.state === 'paused' || left.state === 'stopped') +
        Number(Boolean(left.degraded))
      const rightUrgency =
        Number(right.state === 'paused' || right.state === 'stopped') +
        Number(Boolean(right.degraded))
      if (rightUrgency !== leftUrgency) return rightUrgency - leftUrgency
    }

    return rightScore - leftScore
  })
}

function phaseEntries(experiments: Experiment[]) {
  const counts = new Map<string, number>()
  for (const experiment of experiments) {
    const phase = experiment.phase || experiment.state || 'unknown'
    counts.set(phase, (counts.get(phase) || 0) + 1)
  }
  return [...counts.entries()].sort((left, right) => right[1] - left[1])
}

function eventTone(event: ExperimentEvent): 'accent' | 'warn' | 'danger' {
  if (event.payload?.health === 'failed') return 'danger'
  if (event.payload?.decision?.status === 'rejected') return 'warn'
  if (event.payload?.health === 'degraded') return 'warn'
  return 'accent'
}

function App() {
  const [payload, setPayload] = useState<DashboardPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lens, setLens] = useState<Lens>('operator')
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const [statusNote, setStatusNote] = useState('Loading generative operator surface...')

  const deferredLens = useDeferredValue(lens)
  const embedded = window.self !== window.top

  const refreshDashboard = useEffectEvent(async () => {
    try {
      const response = await fetch('/api/dashboard', { cache: 'no-store' })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const nextPayload: DashboardPayload = await response.json()
      startTransition(() => {
        setPayload(nextPayload)
        setError(null)
        setStatusNote('Live payload synced from /api/dashboard.')
      })
    } catch (refreshError) {
      const message =
        refreshError instanceof Error ? refreshError.message : 'Unknown error'
      startTransition(() => {
        setError(message)
        setStatusNote(`Refresh failed: ${message}`)
      })
    }
  })

  useEffect(() => {
    void refreshDashboard()
    const timer = window.setInterval(() => {
      void refreshDashboard()
    }, REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [refreshDashboard])

  const runSuggestedAction = useEffectEvent(
    async (experimentId: string, action: ExperimentAction) => {
      setPendingAction(experimentId)
      setStatusNote(`Sending ${action} to ${experimentId}...`)
      try {
        const response = await fetch('/api/workbench/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target: 'experiment',
            action,
            experiment_id: experimentId,
          }),
        })
        const result = await response.json()
        if (!response.ok || !result.ok) {
          throw new Error(result.error || `HTTP ${response.status}`)
        }
        await refreshDashboard()
        setStatusNote(`${experimentId} ${action} completed.`)
      } catch (actionError) {
        const message =
          actionError instanceof Error ? actionError.message : 'Unknown error'
        setStatusNote(`${experimentId} ${action} failed: ${message}`)
      } finally {
        setPendingAction(null)
      }
    },
  )

  const managerSummary = payload?.workbench?.experiment_manager?.summary || {}
  const experiments = payload?.experiments || []
  const events = payload?.experiment_events || []
  const narrative = narrativeFor(payload || {}, deferredLens)
  const topOpportunities = sortExperiments(experiments, deferredLens)
    .slice(0, 4)
    .map((experiment) => recommendationFor(experiment))
  const phases = phaseEntries(experiments).slice(0, 6)
  const decisions = Object.entries(managerSummary.decision_counts || {})
  const livePositions = payload?.paper?.positions || []
  const leadActions = (payload?.actions || []).slice(0, 3)
  const lensCard = lensMeta[deferredLens]
  const LensIcon = lensCard.icon

  return (
    <main className={`workspace ${embedded ? 'workspace--embedded' : ''}`}>
      <section className="hero-shell">
        <div className="hero-shell__mesh" />
        <div className="hero-shell__topline">
          <div className="brand-lockup">
            <img className="brand-lockup__mark" src="/assets/logo.png" alt="" />
            <div>
              <p className="eyebrow">Codex generative dashboard artifact</p>
              <h1>Compose the room around what changed, not around fixed tiles.</h1>
            </div>
          </div>
          <div className="hero-shell__links">
            <a className="ghost-link" href="/" target="_blank" rel="noreferrer">
              Open native dashboard
            </a>
          </div>
        </div>

        <div className="hero-grid">
          <article className="hero-copy panel panel--hero">
            <div className="story-kicker">
              <Sparkles size={16} />
              <span>{narrative.eyebrow}</span>
            </div>
            <h2>{narrative.headline}</h2>
            <p className="hero-copy__summary">{narrative.summary}</p>
            <div className="bullet-stack">
              <div>{narrative.bulletA}</div>
              <div>{narrative.bulletB}</div>
              <div>{narrative.bulletC}</div>
            </div>
          </article>

          <article className="lens-panel panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Lenses</p>
                <h3>Shift the generated readout</h3>
              </div>
              <LensIcon size={18} />
            </div>
            <div className="lens-switcher">
              {(['operator', 'research', 'risk'] as Lens[]).map((value) => {
                const meta = lensMeta[value]
                const Icon = meta.icon
                return (
                  <button
                    key={value}
                    className={`lens-chip ${
                      value === lens ? 'lens-chip--active' : ''
                    }`}
                    onClick={() => setLens(value)}
                    type="button"
                  >
                    <Icon size={16} />
                    <span>{meta.label}</span>
                  </button>
                )
              })}
            </div>
            <p className="panel-note">{lensCard.note}</p>
            <div className="status-ribbon">
              <span>{statusNote}</span>
              <span>{stamp(payload?.meta?.generated_at)}</span>
            </div>
          </article>
        </div>

        <div className="signal-row">
          <article className="signal-tile">
            <span className="signal-tile__label">Paper equity</span>
            <strong>{money(payload?.paper?.portfolio?.equity)}</strong>
            <span className="signal-tile__detail">
              {livePositions.length > 0
                ? `${livePositions.length} live paper positions`
                : 'No paper exposure open'}
            </span>
          </article>
          <article className="signal-tile">
            <span className="signal-tile__label">Leader thread</span>
            <strong>{managerSummary.leader_id || '--'}</strong>
            <span className="signal-tile__detail">
              Score {decimal(managerSummary.leader_score)}
            </span>
          </article>
          <article className="signal-tile">
            <span className="signal-tile__label">Active / degraded</span>
            <strong>
              {managerSummary.active_count ?? 0} / {managerSummary.degraded_count ?? 0}
            </strong>
            <span className="signal-tile__detail">
              Failed {managerSummary.failed_count ?? 0}, drifted{' '}
              {managerSummary.drift_count ?? 0}
            </span>
          </article>
          <article className="signal-tile">
            <span className="signal-tile__label">Decision mix</span>
            <strong>
              {Object.entries(managerSummary.decision_counts || {})
                .map(([key, value]) => `${key}:${value}`)
                .join(' · ') || '--'}
            </strong>
            <span className="signal-tile__detail">
              Manager state {payload?.workbench?.experiment_manager?.state || '--'}
            </span>
          </article>
        </div>
      </section>

      <section className="content-grid">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Generated moves</p>
              <h3>What the room wants next</h3>
            </div>
            <Bot size={18} />
          </div>
          <div className="opportunity-grid">
            {topOpportunities.length > 0 ? (
              topOpportunities.map((card) => {
                const action = card.action
                return (
                  <div key={card.id} className={`opportunity-card tone-${card.tone}`}>
                    <div className="opportunity-card__topline">
                      <strong>{card.title}</strong>
                      <span>{card.id}</span>
                    </div>
                    <p>{card.detail}</p>
                    <div className="opportunity-card__suggestion">{card.suggestion}</div>
                    {action ? (
                      <button
                        className="action-button"
                        disabled={pendingAction === card.id}
                        onClick={() => void runSuggestedAction(card.id, action)}
                        type="button"
                      >
                        <span>
                          {pendingAction === card.id
                            ? 'Sending...'
                            : card.actionLabel || 'Run action'}
                        </span>
                        <ArrowRight size={16} />
                      </button>
                    ) : (
                      <div className="monitor-note">No automatic intervention suggested.</div>
                    )}
                  </div>
                )
              })
            ) : (
              <div className="empty-state">No experiment inventory is available yet.</div>
            )}
          </div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Room geometry</p>
              <h3>Where the threads are clustering</h3>
            </div>
            <Orbit size={18} />
          </div>
          <div className="phase-stack">
            {phases.length > 0 ? (
              phases.map(([phase, count]) => (
                <div key={phase} className="phase-row">
                  <div className="phase-row__meta">
                    <strong>{phase}</strong>
                    <span>{count} threads</span>
                  </div>
                  <div className="phase-row__bar">
                    <span style={{ width: `${Math.max(14, count * 11)}%` }} />
                  </div>
                </div>
              ))
            ) : (
              <div className="empty-state">No phase data has been written yet.</div>
            )}
          </div>

          <div className="decision-grid">
            {decisions.length > 0 ? (
              decisions.map(([decision, count]) => (
                <div key={decision} className="decision-tile">
                  <span>{decision}</span>
                  <strong>{count}</strong>
                </div>
              ))
            ) : (
              <div className="empty-state">Decision counts will populate after the first completed cycles.</div>
            )}
          </div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Operator prompts</p>
              <h3>Native dashboard actions worth preserving</h3>
            </div>
            <Activity size={18} />
          </div>
          <div className="prompt-stack">
            {leadActions.length > 0 ? (
              leadActions.map((item, index) => (
                <div key={`${item.title}-${index}`} className="prompt-card">
                  <strong>{item.title || 'Untitled action'}</strong>
                  <p>{item.detail || 'No detail provided.'}</p>
                </div>
              ))
            ) : (
              <div className="empty-state">The base dashboard has not emitted any action prompts yet.</div>
            )}
          </div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Recent signal</p>
              <h3>Event stream with semantic weight</h3>
            </div>
            <Flame size={18} />
          </div>
          <div className="event-stack">
            {events.length > 0 ? (
              events.slice(0, 6).map((event, index) => (
                <div key={`${event.timestamp}-${index}`} className={`event-card tone-${eventTone(event)}`}>
                  <div className="event-card__topline">
                    <strong>{event.type || 'event'}</strong>
                    <span>{stamp(event.timestamp)}</span>
                  </div>
                  <div className="event-card__body">
                    <span>{event.experiment_id || 'manager'}</span>
                    <span>{event.payload?.phase || event.payload?.phase_detail || '--'}</span>
                    <span>{event.payload?.decision?.status || event.payload?.health || '--'}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="empty-state">No manager events are available yet.</div>
            )}
          </div>
        </article>

        <article className="panel panel--wide">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Thread tape</p>
              <h3>All experiments, re-ranked by the current lens</h3>
            </div>
            <Radar size={18} />
          </div>
          <div className="thread-tape">
            {sortExperiments(experiments, deferredLens).map((experiment, index) => {
              const score = scoreOf(experiment)
              return (
                <div
                  key={experiment.id || `thread-${index}`}
                  className={`thread-pill tone-${stateTone(experiment)}`}
                >
                  <div className="thread-pill__title">
                    <strong>{experiment.id || 'unknown-thread'}</strong>
                    <span>{experiment.phase || experiment.state || '--'}</span>
                  </div>
                  <div className="thread-pill__meta">
                    <span>{experiment.search_space || 'search space unset'}</span>
                    <span>score {decimal(score)}</span>
                    <span>
                      {experiment.last_decision?.status ||
                        (experiment.degraded ? 'degraded' : experiment.health || '--')}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </article>
      </section>

      {error ? (
        <section className="error-banner">
          <TriangleAlert size={18} />
          <span>{error}</span>
        </section>
      ) : null}
    </main>
  )
}

export default App
