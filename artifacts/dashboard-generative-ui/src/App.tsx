import {
  Activity,
  BarChart3,
  Bot,
  BrainCircuit,
  Clock3,
  Command,
  Compass,
  Flame,
  Layers3,
  Orbit,
  Radar,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from 'lucide-react'
import {
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from 'react'
import './App.css'

type Capability = 'mission' | 'fleet' | 'risk' | 'research'
type ExperimentAction = 'start' | 'pause' | 'resume' | 'restart' | 'stop'
type ManagerAction = 'start' | 'pause' | 'resume' | 'restart' | 'stop'
type PaperAction = 'start' | 'restart' | 'stop'
type ControlTarget = 'paper' | 'trainer' | 'experiment'

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
    engine?: {
      equity?: number
      running?: boolean
      positions?: Record<string, number>
    }
  }
  trading?: {
    summary?: {
      total_experiments?: number
      best_score?: number | null
      best_commit?: string | null
    }
  }
  research?: {
    summary?: {
      total_runs?: number
      best_val_bpb?: number | null
      best_commit?: string | null
    }
  }
  equity?: {
    summary?: {
      return_pct?: number
    }
  }
  baseline_equity?: {
    summary?: {
      return_pct?: number
    }
  }
  experiment_events?: ExperimentEvent[]
  experiments?: Experiment[]
  workbench?: WorkbenchSnapshot
}

type WorkbenchSnapshot = {
  dashboard?: {
    url?: string
  }
  paper?: {
    running?: boolean
    pid?: number
    returncode?: number | null
  }
  experiment_manager?: {
    state?: string
    summary?: {
      active_count?: number
      paused_count?: number
      failed_count?: number
      degraded_count?: number
      drift_count?: number
      manager_state?: string
      leader_id?: string | null
      leader_score?: number | null
      phase_counts?: Record<string, number>
      decision_counts?: Record<string, number>
    }
  }
  experiments?: Experiment[]
}

type Experiment = {
  id?: string
  hypothesis?: string
  objective?: string
  state?: string
  phase?: string
  phase_detail?: string
  search_space?: string
  split?: string
  symbols?: string[]
  health?: string
  degraded?: boolean
  degraded_reasons?: string[]
  health_reasons?: string[]
  best_score?: number | null
  iteration?: number
  cycle_runtime_seconds?: number | null
  last_started_at?: string | null
  last_completed_at?: string | null
  last_phase_transition_at?: string | null
  last_error?: string | null
  last_exit_code?: number | null
  last_metrics?: {
    score?: number | null
  }
  last_decision?: {
    status?: string
    reason?: string
  }
  last_verification?: {
    failed_gates?: string[]
  }
  command?: string[]
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
    desired_state?: string
    decision?: {
      status?: string
    }
  }
}

type CapabilityMeta = {
  label: string
  icon: typeof Compass
  summary: string
  detail: string
}

type TimelineSnapshot = {
  eyebrow: string
  title: string
  detail: string
  metricA: string
  metricB: string
  metricC: string
}

type PostmortemDriver =
  | 'model'
  | 'execution'
  | 'liquidity-exit'
  | 'sizing'
  | 'operational'

const REFRESH_MS = 10000
const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

const capabilityMeta: Record<Capability, CapabilityMeta> = {
  mission: {
    label: 'Mission',
    icon: Command,
    summary: 'Follow the room-wide command cadence and keep the leader moving.',
    detail:
      'Mission view centers the operational snapshot, live controls, and the latest event stream.',
  },
  fleet: {
    label: 'Fleet',
    icon: Layers3,
    summary: 'Rank every thread by urgency, health, and reward.',
    detail:
      'Fleet view emphasizes the active experiment board and the controls attached to each thread.',
  },
  risk: {
    label: 'Risk',
    icon: ShieldAlert,
    summary: 'Intervene early when verification, drift, or health degrade.',
    detail:
      'Risk view prioritizes unhealthy threads, failed gates, and state drift before they become noise.',
  },
  research: {
    label: 'Research',
    icon: BrainCircuit,
    summary: 'Compare search spaces, score leaders, and benchmark the edge.',
    detail:
      'Research view foregrounds the strongest experiments, return curves, and best validation runs.',
  },
}

const capabilityOrder: Capability[] = ['mission', 'fleet', 'risk', 'research']
const EMPTY_EXPERIMENTS: Experiment[] = []
const EMPTY_EVENTS: ExperimentEvent[] = []
const EMPTY_ACTIONS: NonNullable<DashboardPayload['actions']> = []
const postmortemDrivers: Array<{ value: PostmortemDriver; label: string }> = [
  { value: 'model', label: 'Model' },
  { value: 'execution', label: 'Execution' },
  { value: 'liquidity-exit', label: 'Liquidity / exit' },
  { value: 'sizing', label: 'Sizing' },
  { value: 'operational', label: 'Operational' },
]

function scoreOf(experiment: Experiment): number | null {
  if (typeof experiment.best_score === 'number') return experiment.best_score
  if (typeof experiment.last_metrics?.score === 'number') return experiment.last_metrics.score
  return null
}

function money(value: number | undefined | null): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? currency.format(value)
    : '--'
}

function decimal(value: number | null | undefined, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toFixed(digits)
    : '--'
}

function percent(value: number | null | undefined, digits = 1): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${value.toFixed(digits)}%`
    : '--'
}

function stamp(value: string | null | undefined): string {
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

function shortClock(value: string | null | undefined): string {
  if (!value) return '--'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function compactList(values: string[] | undefined, limit = 3): string {
  const filtered = (values || []).filter(Boolean)
  if (!filtered.length) return '--'
  return filtered.slice(0, limit).join(', ') + (filtered.length > limit ? ' …' : '')
}

function compactCommand(command: string[] | undefined): string {
  if (!command || command.length === 0) return '--'
  const preview = command.slice(0, 6).join(' ')
  return command.length > 6 ? `${preview} …` : preview
}

function stateTone(experiment: Experiment): 'accent' | 'warn' | 'danger' {
  if (experiment.degraded || experiment.health === 'failed' || experiment.last_error) {
    return 'danger'
  }
  if (experiment.state === 'paused' || experiment.health === 'degraded') {
    return 'warn'
  }
  return 'accent'
}

function actionTone(event: ExperimentEvent): 'accent' | 'warn' | 'danger' {
  if (event.payload?.health === 'failed') return 'danger'
  if (event.payload?.decision?.status === 'rejected') return 'warn'
  if (event.payload?.health === 'degraded') return 'warn'
  return 'accent'
}

function actionKey(target: ControlTarget, action: string, experimentId?: string): string {
  return `${target}:${action}:${experimentId || 'all'}`
}

function eventSummary(event: ExperimentEvent): string {
  const parts = [event.payload?.phase, event.payload?.phase_detail, event.payload?.health]
    .filter(Boolean)
    .join(' · ')
  if (parts) return parts
  if (event.payload?.decision?.status) return `decision · ${event.payload.decision.status}`
  return event.experiment_id || 'manager'
}

function actionLabel(action: ExperimentAction | ManagerAction | PaperAction): string {
  return action.charAt(0).toUpperCase() + action.slice(1)
}

async function readJsonResponse<T>(response: Response, route: string): Promise<T> {
  const text = await response.text()
  if (!text) return {} as T
  try {
    return JSON.parse(text) as T
  } catch {
    const snippet = text.slice(0, 120).replace(/\s+/g, ' ').trim()
    throw new Error(
      `Unexpected non-JSON response from ${route}${
        snippet ? `: ${snippet}` : ''
      }`,
    )
  }
}

function sortExperiments(experiments: Experiment[], capability: Capability): Experiment[] {
  return [...experiments].sort((left, right) => {
    const leftScore = scoreOf(left) ?? Number.NEGATIVE_INFINITY
    const rightScore = scoreOf(right) ?? Number.NEGATIVE_INFINITY
    const leftRisk =
      Number(Boolean(left.degraded)) +
      Number(left.health === 'degraded') +
      Number(Boolean(left.last_error))
    const rightRisk =
      Number(Boolean(right.degraded)) +
      Number(right.health === 'degraded') +
      Number(Boolean(right.last_error))
    const leftUrgency =
      Number(left.state === 'paused' || left.state === 'stopped') +
      Number(Boolean(left.degraded)) +
      Number(Boolean(left.last_error))
    const rightUrgency =
      Number(right.state === 'paused' || right.state === 'stopped') +
      Number(Boolean(right.degraded)) +
      Number(Boolean(right.last_error))
    const leftFreshness = new Date(
      left.last_phase_transition_at || left.last_completed_at || left.last_started_at || 0,
    ).getTime()
    const rightFreshness = new Date(
      right.last_phase_transition_at || right.last_completed_at || right.last_started_at || 0,
    ).getTime()

    if (capability === 'risk') {
      if (rightRisk !== leftRisk) return rightRisk - leftRisk
      if (rightScore !== leftScore) return leftScore - rightScore
      return rightFreshness - leftFreshness
    }

    if (capability === 'fleet') {
      if (rightUrgency !== leftUrgency) return rightUrgency - leftUrgency
      if (rightScore !== leftScore) return rightScore - leftScore
      return rightFreshness - leftFreshness
    }

    if (capability === 'research') {
      if (rightScore !== leftScore) return rightScore - leftScore
      const leftIteration = left.iteration ?? 0
      const rightIteration = right.iteration ?? 0
      if (rightIteration !== leftIteration) return rightIteration - leftIteration
      return rightFreshness - leftFreshness
    }

    if (rightUrgency !== leftUrgency) return rightUrgency - leftUrgency
    if (rightScore !== leftScore) return rightScore - leftScore
    return rightFreshness - leftFreshness
  })
}

function buildTimelineSnapshot(
  payload: DashboardPayload,
  capability: Capability,
  selectedThread: Experiment | null,
): TimelineSnapshot {
  const summary = payload.workbench?.experiment_manager?.summary || {}
  const research = payload.research?.summary || {}
  const trading = payload.trading?.summary || {}
  const leaderId = summary.leader_id || selectedThread?.id || 'no leader'
  const activeCount = summary.active_count ?? 0
  const degradedCount = summary.degraded_count ?? 0
  const failedCount = summary.failed_count ?? 0
  const managerState =
    summary.manager_state || payload.workbench?.experiment_manager?.state || 'running'
  const capabilityLabel = capabilityMeta[capability].label

  return {
    eyebrow: `${capabilityLabel} focus`,
    title: `${leaderId} is steering ${activeCount} active threads.`,
    detail:
      capability === 'risk'
        ? `Risk focus is now on ${degradedCount} degraded and ${failedCount} failed threads, plus any drift on the selected leader.`
        : capability === 'research'
          ? `Research focus is comparing ${research.total_runs ?? 0} validation runs against the strongest thread and the latest trading score.`
          : `Manager state is ${managerState}; the command surface should keep the leader, paper engine, and fleet moving in lockstep.`,
    metricA: `leader ${leaderId}`,
    metricB: `active ${activeCount} / degraded ${degradedCount}`,
    metricC:
      capability === 'research'
        ? `best score ${decimal(trading.best_score)}`
        : capability === 'risk'
          ? `failed ${failedCount}`
          : `paper ${money(payload.paper?.portfolio?.equity)}`,
  }
}

function App() {
  const [payload, setPayload] = useState<DashboardPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [statusNote, setStatusNote] = useState('Loading mission control surface...')
  const [selectedCapability, setSelectedCapability] = useState<Capability>('mission')
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null)
  const [pendingControl, setPendingControl] = useState<string | null>(null)
  const [postmortemOpen, setPostmortemOpen] = useState(false)
  const [postmortemDriver, setPostmortemDriver] = useState<PostmortemDriver>('model')
  const [postmortemWorked, setPostmortemWorked] = useState('')
  const [postmortemFailed, setPostmortemFailed] = useState('')
  const [postmortemGuardrail, setPostmortemGuardrail] = useState('')
  const [postmortemStatus, setPostmortemStatus] = useState('Capture the outcome while the room is still fresh.')
  const [postmortemSaved, setPostmortemSaved] = useState(false)

  const deferredCapability = useDeferredValue(selectedCapability)
  const embedded = window.self !== window.top

  const refreshDashboard = useCallback(async () => {
    try {
      const response = await fetch('/api/dashboard', { cache: 'no-store' })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const nextPayload = await readJsonResponse<DashboardPayload>(response, '/api/dashboard')
      startTransition(() => {
        setPayload(nextPayload)
        setError(null)
        setStatusNote(`Live payload synced from /api/dashboard at ${stamp(nextPayload.meta?.generated_at)}`)
      })
    } catch (refreshError) {
      const message = refreshError instanceof Error ? refreshError.message : 'Unknown error'
      startTransition(() => {
        setError(message)
        setStatusNote(`Refresh failed: ${message}`)
      })
    }
  }, [])

  useEffect(() => {
    void refreshDashboard()
    const timer = window.setInterval(() => {
      void refreshDashboard()
    }, REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [refreshDashboard])

  const runControl = useCallback(
    async (
      target: ControlTarget,
      action: ExperimentAction | ManagerAction | PaperAction,
      experimentId?: string,
    ) => {
      const key = actionKey(target, action, experimentId)
      setPendingControl(key)
      setStatusNote(`Sending ${action} to ${target}${experimentId ? ` / ${experimentId}` : ''}...`)

      try {
        const response = await fetch('/api/workbench/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target,
            action,
            experiment_id: experimentId,
          }),
        })
        const result = await readJsonResponse<{ ok?: boolean; error?: string }>(
          response,
          '/api/workbench/control',
        )
        if (!response.ok || !result.ok) {
          throw new Error(result.error || `HTTP ${response.status}`)
        }
        await refreshDashboard()
        setStatusNote(`${actionLabel(action)} on ${target}${experimentId ? ` / ${experimentId}` : ''} completed.`)
      } catch (actionError) {
        const message = actionError instanceof Error ? actionError.message : 'Unknown error'
        setStatusNote(`${actionLabel(action)} on ${target} failed: ${message}`)
      } finally {
        setPendingControl(null)
      }
    },
    [refreshDashboard],
  )

  const workbench = payload?.workbench || {}
  const manager = workbench.experiment_manager || {}
  const summary = manager.summary || {}
  const experiments = workbench.experiments ?? payload?.experiments ?? EMPTY_EXPERIMENTS
  const events = payload?.experiment_events ?? EMPTY_EVENTS
  const actions = payload?.actions ?? EMPTY_ACTIONS
  const selectedThread =
    experiments.find((experiment) => experiment.id === selectedThreadId) ||
    (summary.leader_id
      ? experiments.find((experiment) => experiment.id === summary.leader_id) || null
      : null) ||
    experiments[0] ||
    null

  useEffect(() => {
    if (!experiments.length) {
      if (selectedThreadId !== null) {
        setSelectedThreadId(null)
      }
      return
    }
    const currentExists = selectedThreadId
      ? experiments.some((experiment) => experiment.id === selectedThreadId)
      : false
    if (!currentExists) {
      setSelectedThreadId(summary.leader_id || experiments[0]?.id || null)
    }
  }, [experiments, selectedThreadId, summary.leader_id])

  const capabilityCard = capabilityMeta[deferredCapability]
  const CapabilityIcon = capabilityCard.icon
  const timelineSnapshot = buildTimelineSnapshot(payload || {}, deferredCapability, selectedThread)
  const sortedFleet = sortExperiments(experiments, deferredCapability)
  const recentEvents = events.slice(0, 8)
  const recentActions = actions.slice(0, 3)
  const paperPositions = payload?.paper?.positions || []
  const paperRunning = Boolean(workbench.paper?.running)
  const managerState = summary.manager_state || manager.state || 'running'
  const managerActions: ManagerAction[] =
    managerState === 'stopped'
      ? ['start', 'restart']
      : managerState === 'paused'
        ? ['resume', 'restart', 'stop']
        : ['pause', 'restart', 'stop']
  const paperActions: PaperAction[] = paperRunning ? ['stop', 'restart'] : ['start']
  const selectedThreadActions: ExperimentAction[] =
    selectedThread?.state === 'paused'
      ? ['resume', 'restart', 'stop']
      : selectedThread?.state === 'stopped'
        ? ['start', 'restart']
        : ['pause', 'restart', 'stop']

  const fleetCounts = {
    total: experiments.length,
    active: summary.active_count ?? 0,
    degraded: summary.degraded_count ?? 0,
    failed: summary.failed_count ?? 0,
  }

  const equitySummary = payload?.equity?.summary
  const baselineSummary = payload?.baseline_equity?.summary
  const researchSummary = payload?.research?.summary
  const tradingSummary = payload?.trading?.summary
  const postmortemMarkdown = useMemo(() => {
    const snapshotStamp = new Date().toISOString()
    const selectedThreadSummary = selectedThread?.id
      ? `- Selected thread: ${selectedThread.id}\n- Thread state: ${selectedThread.state || '--'}\n- Thread score: ${decimal(scoreOf(selectedThread))}`
      : '- Selected thread: none'
    return [
      `## ${snapshotStamp} - Auto-Research postmortem`,
      '',
      '### Snapshot',
      `- UTC timestamp: ${snapshotStamp}`,
      `- Paper equity: ${money(payload?.paper?.portfolio?.equity)}`,
      `- Leader thread: ${summary.leader_id || '--'}`,
      `- Active / degraded / failed: ${fleetCounts.active} / ${fleetCounts.degraded} / ${fleetCounts.failed}`,
      selectedThreadSummary,
      '',
      '### Primary driver',
      `- ${postmortemDrivers.find((item) => item.value === postmortemDriver)?.label || 'Model'}`,
      '',
      '### What worked',
      postmortemWorked || '- ',
      '',
      '### What failed',
      postmortemFailed || '- ',
      '',
      '### New guardrail',
      postmortemGuardrail || '- ',
      '',
      '### Recommended follow-through',
      '- Append this entry to docs/trade_postmortems.md',
      '- Add the guardrail to AGENTS.md, a skill, or code if it should become enforceable',
      '- Re-run the relevant verification command before the next live-sensitive action',
    ].join('\n')
  }, [
    fleetCounts.active,
    fleetCounts.degraded,
    fleetCounts.failed,
    payload?.paper?.portfolio?.equity,
    postmortemDriver,
    postmortemFailed,
    postmortemGuardrail,
    postmortemWorked,
    selectedThread,
    summary.leader_id,
  ])

  useEffect(() => {
    setPostmortemSaved(false)
  }, [postmortemMarkdown])

  return (
    <main className={`workspace ${embedded ? 'workspace--embedded' : ''}`}>
      <section className="dashboard-surface">
        <header className="panel command-rail">
          <div className="command-rail__lead">
            <div className="brand-mark">
              <Sparkles size={20} />
            </div>
            <div>
              <p className="eyebrow">Chat-first mission control</p>
              <h1>Direct the room from the same surface that explains it.</h1>
              <p className="command-rail__lede">
                The dashboard speaks in live state, but the controls remain explicit:
                refresh the payload, steer the manager, and intervene at the thread level.
              </p>
            </div>
          </div>

          <div className="command-rail__transcript">
            <div className="chat-bubble chat-bubble--system">
              <span className="chat-bubble__label">System</span>
              <p>{statusNote}</p>
            </div>
            <div className="chat-bubble chat-bubble--operator">
              <span className="chat-bubble__label">Operator</span>
              <p>
                {capabilityCard.summary} Use the rail to move the manager, paper feed,
                or the selected thread without leaving this workspace.
              </p>
            </div>
          </div>

          <div className="command-rail__actions">
            <div className="command-group">
              <span className="command-group__label">Manager</span>
              <div className="command-group__buttons">
                {managerActions.map((action) => {
                  const key = actionKey('trainer', action)
                  return (
                    <button
                      key={key}
                      className="rail-button"
                      disabled={pendingControl === key}
                      type="button"
                      onClick={() => void runControl('trainer', action)}
                    >
                      {pendingControl === key ? 'Sending...' : actionLabel(action)}
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="command-group">
              <span className="command-group__label">Paper</span>
              <div className="command-group__buttons">
                {paperActions.map((action) => {
                  const key = actionKey('paper', action)
                  return (
                    <button
                      key={key}
                      className="rail-button"
                      disabled={pendingControl === key}
                      type="button"
                      onClick={() => void runControl('paper', action)}
                    >
                      {pendingControl === key ? 'Sending...' : actionLabel(action)}
                    </button>
                  )
                })}
              </div>
            </div>

            <a
              className="rail-link"
              href={workbench.dashboard?.url || '/'}
              target="_blank"
              rel="noreferrer"
            >
              <Command size={16} />
              Open native dashboard
            </a>
          </div>
        </header>

        <nav className="panel capability-nav" aria-label="Capability navigation">
          {capabilityOrder.map((capability) => {
            const meta = capabilityMeta[capability]
            const Icon = meta.icon
            const value =
              capability === 'mission'
                ? fleetCounts.active
                : capability === 'fleet'
                  ? fleetCounts.total
                  : capability === 'risk'
                    ? fleetCounts.degraded + fleetCounts.failed
                    : researchSummary?.total_runs ?? 0
            return (
              <button
                key={capability}
                className={`capability-chip ${capability === selectedCapability ? 'capability-chip--active' : ''}`}
                type="button"
                onClick={() => setSelectedCapability(capability)}
              >
                <Icon size={16} />
                <span>{meta.label}</span>
                <strong>{value}</strong>
              </button>
            )
          })}
        </nav>

        <div className="dashboard-grid">
          <aside className="panel rail rail--fleet">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Thread fleet board</p>
                <h2>Every experiment, sorted for the current lens.</h2>
              </div>
              <Layers3 size={18} />
            </div>

            <div className="metric-strip">
              <div className="metric-card">
                <span>Threads</span>
                <strong>{fleetCounts.total}</strong>
              </div>
              <div className="metric-card">
                <span>Active</span>
                <strong>{fleetCounts.active}</strong>
              </div>
              <div className="metric-card">
                <span>Risk</span>
                <strong>{fleetCounts.degraded + fleetCounts.failed}</strong>
              </div>
            </div>

            <div className="fleet-board">
              {sortedFleet.length > 0 ? (
                sortedFleet.map((experiment, index) => {
                  const score = scoreOf(experiment)
                  const selected = experiment.id && experiment.id === selectedThread?.id
                  const stateActionSet: ExperimentAction[] =
                    experiment.state === 'paused'
                      ? ['resume', 'restart', 'stop']
                      : experiment.state === 'stopped'
                        ? ['start', 'restart']
                        : ['pause', 'restart', 'stop']
                  return (
                    <article
                      key={experiment.id || `thread-${index}`}
                      className={`thread-card tone-${stateTone(experiment)} ${selected ? 'thread-card--selected' : ''}`}
                      onClick={() => setSelectedThreadId(experiment.id || null)}
                    >
                      <div className="thread-card__topline">
                        <div>
                          <strong>{experiment.id || 'unknown-thread'}</strong>
                          <span>{experiment.phase || experiment.state || '--'}</span>
                        </div>
                        <span className="thread-card__select">{selected ? 'Focused' : 'Inspect'}</span>
                      </div>

                      <p className="thread-card__lead">
                        {experiment.hypothesis || experiment.objective || experiment.search_space || 'No hypothesis text is available.'}
                      </p>

                      <div className="thread-card__meta">
                        <span>score {decimal(score)}</span>
                        <span>iter {experiment.iteration ?? 0}</span>
                        <span>{compactList(experiment.symbols)}</span>
                      </div>

                      <div className="thread-card__tags">
                        <span>{experiment.search_space || 'search space unset'}</span>
                        <span>{experiment.health || 'health unknown'}</span>
                      </div>

                      <div className="thread-card__actions">
                        {stateActionSet.map((action) => {
                          const key = actionKey('experiment', action, experiment.id)
                          return (
                            <button
                              key={key}
                              className="thread-action"
                              disabled={pendingControl === key || !experiment.id}
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation()
                                if (!experiment.id) return
                                void runControl('experiment', action, experiment.id)
                              }}
                            >
                              {pendingControl === key ? 'Sending...' : actionLabel(action)}
                            </button>
                          )
                        })}
                      </div>
                    </article>
                  )
                })
              ) : (
                <div className="empty-state">No experiment inventory is available yet.</div>
              )}
            </div>
          </aside>

          <section className="panel rail rail--timeline">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Mission timeline</p>
                <h2>Chronology first, explanation second.</h2>
              </div>
              <Clock3 size={18} />
            </div>

            <article className={`timeline-snapshot tone-${selectedCapability}`}>
              <div className="timeline-snapshot__icon">
                <CapabilityIcon size={18} />
              </div>
              <div className="timeline-snapshot__body">
                <p className="timeline-snapshot__eyebrow">{timelineSnapshot.eyebrow}</p>
                <strong>{timelineSnapshot.title}</strong>
                <p>{timelineSnapshot.detail}</p>
                <div className="timeline-snapshot__metrics">
                  <span>{timelineSnapshot.metricA}</span>
                  <span>{timelineSnapshot.metricB}</span>
                  <span>{timelineSnapshot.metricC}</span>
                </div>
              </div>
            </article>

            <div className="timeline-stack">
              {recentEvents.length > 0 ? (
                recentEvents.map((event, index) => {
                  const tone = actionTone(event)
                  return (
                    <article
                      key={`${event.timestamp || 'event'}-${index}`}
                      className={`timeline-item tone-${tone}`}
                    >
                      <div className="timeline-item__rail" />
                      <div className="timeline-item__body">
                        <div className="timeline-item__topline">
                          <div>
                            <strong>{event.type || 'event'}</strong>
                            <span>{event.experiment_id || 'manager'}</span>
                          </div>
                          <span>{stamp(event.timestamp)}</span>
                        </div>
                        <p className="timeline-item__detail">{eventSummary(event)}</p>
                        <div className="timeline-item__meta">
                          <span>{event.payload?.search_space || 'search space n/a'}</span>
                          <span>{event.payload?.desired_state || '--'}</span>
                          <span>{event.payload?.decision?.status || '--'}</span>
                        </div>
                      </div>
                    </article>
                  )
                })
              ) : (
                <div className="empty-state">No manager events are available yet.</div>
              )}
            </div>

            <div className="timeline-footer">
              <div className="timeline-footer__card">
                <span>Generated</span>
                <strong>{stamp(payload?.meta?.generated_at)}</strong>
              </div>
              <div className="timeline-footer__card">
                <span>Manager</span>
                <strong>{managerState}</strong>
              </div>
              <div className="timeline-footer__card">
                <span>Prompt spec</span>
                <strong>{payload?.meta?.strategy_spec ? 'loaded' : 'unavailable'}</strong>
              </div>
            </div>
          </section>

          <aside className="panel rail rail--context">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Right context rail</p>
                <h2>Live state, actions, and benchmarks.</h2>
              </div>
              <Orbit size={18} />
            </div>

            <div className="context-stack">
              <article className="context-card">
                <div className="context-card__header">
                  <div>
                    <p className="context-card__eyebrow">Command state</p>
                    <strong>{statusNote}</strong>
                  </div>
                  <Activity size={16} />
                </div>
                <div className="context-chip-row">
                  <span className="context-chip">Manager {managerState}</span>
                  <span className="context-chip">Paper {paperRunning ? 'running' : 'idle'}</span>
                  <span className="context-chip">Leader {summary.leader_id || '--'}</span>
                </div>
                <p className="context-card__detail">{capabilityCard.detail}</p>
                <div className="mini-actions">
                  <button
                    className="thread-action thread-action--compact"
                    type="button"
                    onClick={() => setPostmortemOpen(true)}
                  >
                    Open postmortem
                  </button>
                </div>
              </article>

              <article className="context-card">
                <div className="context-card__header">
                  <div>
                    <p className="context-card__eyebrow">Paper engine</p>
                    <strong>{money(payload?.paper?.portfolio?.equity)}</strong>
                  </div>
                  <Bot size={16} />
                </div>
                <div className="context-metric-grid">
                  <div className="context-metric">
                    <span>Running</span>
                    <strong>{paperRunning ? 'yes' : 'no'}</strong>
                  </div>
                  <div className="context-metric">
                    <span>Return</span>
                    <strong>{percent(equitySummary?.return_pct)}</strong>
                  </div>
                  <div className="context-metric">
                    <span>Baseline</span>
                    <strong>{percent(baselineSummary?.return_pct)}</strong>
                  </div>
                  <div className="context-metric">
                    <span>Positions</span>
                    <strong>{paperPositions.length}</strong>
                  </div>
                </div>
                <div className="position-stack">
                  {paperPositions.length > 0 ? (
                    paperPositions.map((position) => (
                      <div key={`${position.symbol}-${position.direction}`} className="position-pill">
                        <div>
                          <strong>{position.symbol}</strong>
                          <span>{position.direction || '--'}</span>
                        </div>
                        <span>{money(position.notional)}</span>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state">No paper exposure is open.</div>
                  )}
                </div>
                <div className="mini-actions">
                  {paperActions.map((action) => {
                    const key = actionKey('paper', action)
                    return (
                      <button
                        key={key}
                        className="thread-action thread-action--compact"
                        disabled={pendingControl === key}
                        type="button"
                        onClick={() => void runControl('paper', action)}
                      >
                        {pendingControl === key ? 'Sending...' : actionLabel(action)}
                      </button>
                    )
                  })}
                </div>
              </article>

              <article className="context-card">
                <div className="context-card__header">
                  <div>
                    <p className="context-card__eyebrow">Research scoreboard</p>
                    <strong>{researchSummary?.best_commit || '--'}</strong>
                  </div>
                  <BarChart3 size={16} />
                </div>
                <div className="context-metric-grid">
                  <div className="context-metric">
                    <span>Validation runs</span>
                    <strong>{researchSummary?.total_runs ?? 0}</strong>
                  </div>
                  <div className="context-metric">
                    <span>Best bpb</span>
                    <strong>{decimal(researchSummary?.best_val_bpb)}</strong>
                  </div>
                  <div className="context-metric">
                    <span>Trading score</span>
                    <strong>{decimal(tradingSummary?.best_score)}</strong>
                  </div>
                  <div className="context-metric">
                    <span>Trading set</span>
                    <strong>{tradingSummary?.total_experiments ?? 0}</strong>
                  </div>
                </div>
              </article>

              <article className="context-card">
                <div className="context-card__header">
                  <div>
                    <p className="context-card__eyebrow">Selected thread</p>
                    <strong>{selectedThread?.id || 'No thread selected'}</strong>
                  </div>
                  <Radar size={16} />
                </div>
                {selectedThread ? (
                  <>
                    <p className="context-card__detail">
                      {selectedThread.hypothesis || selectedThread.objective || selectedThread.search_space || 'No hypothesis text is available.'}
                    </p>
                    <div className="context-chip-row">
                      <span className="context-chip">state {selectedThread.state || '--'}</span>
                      <span className="context-chip">phase {selectedThread.phase || '--'}</span>
                      <span className="context-chip">score {decimal(scoreOf(selectedThread))}</span>
                    </div>
                    <div className="context-rows">
                      <div className="context-row">
                        <span>Search space</span>
                        <strong>{selectedThread.search_space || '--'}</strong>
                      </div>
                      <div className="context-row">
                        <span>Last decision</span>
                        <strong>
                          {selectedThread.last_decision?.status || '--'}
                          {selectedThread.last_decision?.reason ? ` · ${selectedThread.last_decision.reason}` : ''}
                        </strong>
                      </div>
                      <div className="context-row">
                        <span>Exit code</span>
                        <strong>{selectedThread.last_exit_code ?? '--'}</strong>
                      </div>
                      <div className="context-row">
                        <span>Runtime</span>
                        <strong>{decimal(selectedThread.cycle_runtime_seconds, 1)}s</strong>
                      </div>
                      <div className="context-row">
                        <span>Started</span>
                        <strong>{shortClock(selectedThread.last_started_at)}</strong>
                      </div>
                      <div className="context-row">
                        <span>Completed</span>
                        <strong>{shortClock(selectedThread.last_completed_at)}</strong>
                      </div>
                    </div>

                    <div className="verification-stack">
                      <div className="verification-card">
                        <span>Verification gates</span>
                        <strong>{compactList(selectedThread.last_verification?.failed_gates, 2)}</strong>
                      </div>
                      <div className="verification-card">
                        <span>Command</span>
                        <strong>{compactCommand(selectedThread.command)}</strong>
                      </div>
                    </div>

                    <div className="mini-actions">
                      {selectedThreadActions.map((action) => {
                        const key = actionKey('experiment', action, selectedThread.id)
                        return (
                          <button
                            key={key}
                            className="thread-action thread-action--compact"
                            disabled={pendingControl === key || !selectedThread.id}
                            type="button"
                            onClick={() => {
                              if (!selectedThread.id) return
                              void runControl('experiment', action, selectedThread.id)
                            }}
                          >
                            {pendingControl === key ? 'Sending...' : actionLabel(action)}
                          </button>
                        )
                      })}
                    </div>
                  </>
                ) : (
                  <div className="empty-state">
                    Select a thread to inspect its plan and verification state.
                  </div>
                )}
              </article>

              <article className="context-card">
                <div className="context-card__header">
                  <div>
                    <p className="context-card__eyebrow">Operator prompts</p>
                    <strong>Native dashboard actions worth preserving</strong>
                  </div>
                  <Flame size={16} />
                </div>
                <div className="prompt-stack">
                  {recentActions.length > 0 ? (
                    recentActions.map((item, index) => (
                      <div key={`${item.title || 'action'}-${index}`} className="prompt-card">
                        <strong>{item.title || 'Untitled action'}</strong>
                        <p>{item.detail || 'No detail provided.'}</p>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state">No action prompts have been emitted yet.</div>
                  )}
                </div>
              </article>
            </div>
          </aside>
        </div>

        <section className="timeline-tail">
          <div className="timeline-tail__card">
            <span>Generated</span>
            <strong>{stamp(payload?.meta?.generated_at)}</strong>
          </div>
          <div className="timeline-tail__card">
            <span>Manager</span>
            <strong>{managerState}</strong>
          </div>
          <div className="timeline-tail__card">
            <span>Prompt spec</span>
            <strong>{payload?.meta?.strategy_spec ? 'loaded' : 'unavailable'}</strong>
          </div>
        </section>

        {error ? (
          <section className="error-banner">
            <TriangleAlert size={18} />
            <span>{error}</span>
          </section>
        ) : null}

        {postmortemOpen ? (
          <section className="modal-shell" role="dialog" aria-modal="true" aria-labelledby="postmortem-title">
            <div className="modal-backdrop" onClick={() => setPostmortemOpen(false)} />
            <article className="modal-card">
              <div className="modal-card__header">
                <div>
                  <p className="eyebrow">Trade postmortem</p>
                  <h2 id="postmortem-title">Turn the latest outcome into a reusable rule.</h2>
                </div>
                <button
                  className="rail-button rail-button--ghost"
                  type="button"
                  onClick={() => setPostmortemOpen(false)}
                >
                  Close
                </button>
              </div>

              <p className="modal-card__lede">
                This is the calm review surface. Capture the driver, what worked, what failed,
                and the guardrail that prevents the same mistake from repeating.
              </p>

              <div className="modal-grid">
                <section className="modal-panel">
                  <div className="modal-panel__group">
                    <label className="modal-label" htmlFor="postmortem-driver">
                      Primary driver
                    </label>
                    <select
                      id="postmortem-driver"
                      className="modal-input"
                      value={postmortemDriver}
                      onChange={(event) => setPostmortemDriver(event.target.value as PostmortemDriver)}
                    >
                      {postmortemDrivers.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="modal-panel__group">
                    <label className="modal-label" htmlFor="postmortem-worked">
                      What worked
                    </label>
                    <textarea
                      id="postmortem-worked"
                      className="modal-input modal-input--area"
                      value={postmortemWorked}
                      onChange={(event) => setPostmortemWorked(event.target.value)}
                      placeholder="Example: The room surfaced the degraded thread quickly, and the restart path was clear."
                    />
                  </div>

                  <div className="modal-panel__group">
                    <label className="modal-label" htmlFor="postmortem-failed">
                      What failed
                    </label>
                    <textarea
                      id="postmortem-failed"
                      className="modal-input modal-input--area"
                      value={postmortemFailed}
                      onChange={(event) => setPostmortemFailed(event.target.value)}
                      placeholder="Example: We acted before verifying whether the latest score drift came from stale state or a real regression."
                    />
                  </div>

                  <div className="modal-panel__group">
                    <label className="modal-label" htmlFor="postmortem-guardrail">
                      New guardrail
                    </label>
                    <textarea
                      id="postmortem-guardrail"
                      className="modal-input modal-input--area"
                      value={postmortemGuardrail}
                      onChange={(event) => setPostmortemGuardrail(event.target.value)}
                      placeholder="Example: Require one explicit verification command after every thread restart before trusting the room state."
                    />
                  </div>
                </section>

                <section className="modal-panel">
                  <div className="modal-panel__header">
                    <strong>Generated postmortem draft</strong>
                    <span>Ready for docs/trade_postmortems.md</span>
                  </div>
                  <pre className="modal-pre">{postmortemMarkdown}</pre>
                  <div className="mini-actions">
                    <button
                      className="rail-button"
                      disabled={postmortemSaved}
                      type="button"
                      onClick={async () => {
                        setPostmortemStatus('Saving the postmortem draft to docs/trade_postmortems.md...')
                        try {
                          const response = await fetch('/api/postmortem', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ markdown: postmortemMarkdown }),
                          })
                          const result = await readJsonResponse<{ ok?: boolean; error?: string; path?: string; duplicate?: boolean }>(
                            response,
                            '/api/postmortem',
                          )
                          if (!response.ok || !result.ok) {
                            throw new Error(result.error || `HTTP ${response.status}`)
                          }
                          setPostmortemSaved(true)
                          setPostmortemStatus(result.duplicate
                            ? `This postmortem draft already matches the latest entry in ${result.path || 'docs/trade_postmortems.md'}.`
                            : `Saved the postmortem draft to ${result.path || 'docs/trade_postmortems.md'}.`)
                        } catch (saveError) {
                          const message =
                            saveError instanceof Error ? saveError.message : 'Unknown error'
                          setPostmortemStatus(
                            `Save failed: ${message}. Use Copy draft as a fallback.`,
                          )
                          setPostmortemSaved(false)
                        }
                      }}
                    >
                      {postmortemSaved ? 'Saved' : 'Save to repo'}
                    </button>
                    <button
                      className="rail-button rail-button--ghost"
                      type="button"
                      onClick={async () => {
                        await navigator.clipboard.writeText(postmortemMarkdown)
                        setPostmortemStatus('Copied the postmortem draft to the clipboard.')
                      }}
                    >
                      Copy draft
                    </button>
                    <button
                      className="rail-button rail-button--ghost"
                      type="button"
                      onClick={() =>
                        setPostmortemStatus(
                          'Next step: append the draft to docs/trade_postmortems.md and encode the guardrail in docs or code.',
                        )
                      }
                    >
                      Show next step
                    </button>
                  </div>
                  <div className="modal-status">{postmortemStatus}</div>
                </section>
              </div>
            </article>
          </section>
        ) : null}
      </section>
    </main>
  )
}

export default App
