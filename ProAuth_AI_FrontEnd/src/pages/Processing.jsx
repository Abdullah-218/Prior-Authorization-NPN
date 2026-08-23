import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, AlertTriangle, BrainCircuit, Check, CircleHelp, Clock3, FileText, ShieldCheck } from 'lucide-react';
import AppLayout from '../components/layout/AppLayout';
import './processing.css';

const TICK_MS = 50;

const evidenceAgents = [
  { key: 'policy', icon: ShieldCheck, name: 'Policy Agent', short: 'Policy', angle: 'top', activity: 'Retrieving applicable coverage policy…', done: 'Policy identified · coverage criteria retrieved', duration: 2200 },
  { key: 'clinical', icon: Activity, name: 'Clinical Agent', short: 'Clinical', angle: 'right', activity: 'Evaluating clinical evidence…', done: 'Clinical evidence evaluated', duration: 2700 },
  { key: 'document', icon: FileText, name: 'Document Agent', short: 'Document', angle: 'left', activity: 'Scanning submitted documents…', done: 'Documents analyzed', duration: 1900 }
];
const reasoningAgent = { key: 'reasoning', icon: BrainCircuit, name: 'Coverage Reasoning Agent', short: 'Reasoning', activity: 'Comparing evidence against policy criteria…', done: 'Recommendation synthesized', duration: 2400 };
const REASONING_START = Math.max(...evidenceAgents.map(a => a.duration));
const REVEAL_START = REASONING_START + reasoningAgent.duration;
const REVEAL_COUNT_MS = 900;

const decisionIcons = { clock: Clock3, check: Check, help: CircleHelp };

const NODE_COORDS = { top: [180, 62], right: [282, 239], left: [78, 239] };
const RING_R = 160;
const RING_C = 2 * Math.PI * RING_R;
const pct = v => `${(v / 3.6).toFixed(2)}%`;

function agentStatus(agent, elapsedMs, startAt = 0) {
  const localElapsed = elapsedMs - startAt;
  const status = localElapsed < 0 ? 'idle' : localElapsed >= agent.duration ? 'done' : 'running';
  const progress = Math.max(0, Math.min(100, (localElapsed / agent.duration) * 100));
  return { status, progress };
}

function OrbitNode({ agent, elapsedMs }) {
  const Icon = agent.icon;
  const { status } = agentStatus(agent, elapsedMs);
  const [x, y] = NODE_COORDS[agent.angle];
  return <div className="orbit-node" style={{ left: pct(x), top: pct(y) }}>
    <span className="orbit-node-label">{agent.short}</span>
    <div className={`orbit-node-icon ${status}`}>
      <Icon size={22} />
      {status === 'running' && <span className="orbit-ring" />}
      {status === 'done' && <span className="node-check"><Check size={9} /></span>}
    </div>
  </div>;
}

function StatusRow({ agent, elapsedMs, startAt = 0, holding }) {
  const Icon = agent.icon;
  const { status, progress } = agentStatus(agent, elapsedMs, startAt);
  const label = status === 'idle' ? 'Queued' : status === 'done' ? (holding ? 'Finalizing…' : agent.done) : agent.activity;
  return <div className={`pstatus-row ${status}`}>
    <div className="pstatus-icon"><Icon size={15} />{status === 'done' && !holding && <span className="pstatus-check"><Check size={8} /></span>}</div>
    <div className="pstatus-body"><strong>{agent.name}</strong><small>{label}</small></div>
    <div className="pstatus-bar"><em style={{ width: `${progress}%` }} /></div>
  </div>;
}

// Real pipeline (2026-08-20 integration): the visual orbit/agent animation
// below is ambient — each agent's own fixed "duration" is illustrative
// timing, not literally synced to the real backend (a single synchronous
// HTTP call, no per-agent progress streaming exists). What's REAL is the
// gate on navigation: this only reveals a result and moves on once `task`'s
// promise actually resolves, which can take 40-90+ real seconds — the
// animation holds at "finalizing" rather than fake-completing on its own
// fixed timer.
//
// `task` is a zero-arg async function resolving to { authorizationId,
// request } — shared by both submitAuthorizationForTriage (new request,
// NewAuthorization.jsx) and resubmitAuthorization (Additional Information
// Required resubmission, ResubmitApplication.jsx), so both flows show this
// exact same animation instead of the resubmit path only getting a static
// disabled-button label.
export default function Processing({
  task,
  eyebrow = 'NEW AUTHORIZATION REQUEST',
  heading = 'Analyzing your request',
  lead = 'Four specialized agents gather and reason over policy, clinical, and document evidence — then converge on a recommendation. Real evaluations can take up to two minutes.',
  errorEyebrow = 'SUBMISSION FAILED',
  errorHeading = "We couldn't complete this evaluation",
  errorBackHref = '/new-authorization',
  errorBackLabel = 'Back to new request',
  navigateTo = authorizationId => `/request/${authorizationId}`,
}) {
  const nav = useNavigate();
  const [elapsedMs, setElapsedMs] = useState(0);
  const [outcome, setOutcome] = useState(null); // { authorizationId, request } once resolved
  const [error, setError] = useState('');
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    task()
      .then(result => setOutcome(result))
      .catch(err => setError(err.message || 'The AI evaluation could not be completed.'));
  }, [task]);

  useEffect(() => {
    if (outcome || error) return undefined;
    const interval = setInterval(() => setElapsedMs(prev => prev + TICK_MS), TICK_MS);
    return () => clearInterval(interval);
  }, [outcome, error]);

  useEffect(() => {
    if (!outcome) return undefined;
    const timeout = setTimeout(() => nav(navigateTo(outcome.authorizationId)), REVEAL_COUNT_MS);
    return () => clearTimeout(timeout);
  }, [outcome, nav, navigateTo]);

  if (error) {
    return <AppLayout><div className="processing page orbit-page">
      <p className="eyebrow">{errorEyebrow}</p>
      <h1>{errorHeading}</h1>
      <p className="lead">{error}</p>
      <div className="pstatus-list">
        <button className="button primary" type="button" onClick={() => nav(errorBackHref)}>{errorBackLabel}</button>
        <button className="button" type="button" onClick={() => nav('/dashboard')} style={{ marginLeft: 12 }}>Back to dashboard</button>
      </div>
      <p className="safe-note"><AlertTriangle size={16} />This can happen if the AI service is briefly at capacity — trying again usually resolves it.</p>
    </div></AppLayout>;
  }

  const result = outcome?.request?.resultDetail;
  const revealed = Boolean(outcome);
  const revealProgress = revealed ? 1 : 0;
  const targetConfidence = parseInt(outcome?.request?.confidence) || 0;
  const displayConfidence = Math.round(revealProgress * targetConfidence);
  const RevealIcon = result ? (decisionIcons[result.icon] || Clock3) : Clock3;
  const holding = elapsedMs >= REVEAL_START && !revealed;
  const coreStatus = agentStatus(reasoningAgent, elapsedMs, REASONING_START).status;
  const showResult = revealed && Boolean(result);
  const CoreIcon = showResult ? RevealIcon : BrainCircuit;
  const overallProgress = Math.max(0, Math.min(1, elapsedMs / REVEAL_START || 0));

  return <AppLayout><div className="processing page orbit-page">
    <p className="eyebrow">{eyebrow}</p>
    <h1>{heading}</h1>
    <p className="lead">{lead}</p>

    <div className="orbit-stage">
      <svg className="orbit-svg" viewBox="0 0 360 360">
        <defs>
          <linearGradient id="orbitGradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#4b9b95" />
            <stop offset="100%" stopColor="#2e70ad" />
          </linearGradient>
        </defs>
        <circle className="orbit-track" cx="180" cy="180" r={RING_R} />
        <circle className="orbit-progress" cx="180" cy="180" r={RING_R}
          strokeDasharray={RING_C} strokeDashoffset={RING_C * (1 - (revealed ? 1 : Math.min(1, overallProgress)))} />
        {evidenceAgents.map(agent => {
          const { status } = agentStatus(agent, elapsedMs);
          const [x, y] = NODE_COORDS[agent.angle];
          return <line key={agent.key} className={`orbit-line ${status}`} x1="180" y1="180" x2={x} y2={y} />;
        })}
      </svg>

      {evidenceAgents.map(agent => <OrbitNode key={agent.key} agent={agent} elapsedMs={elapsedMs} />)}

      <div className={`orbit-core ${coreStatus} ${showResult ? `revealed ${result.reviewBadgeTone}` : ''}`}>
        <CoreIcon size={showResult ? 28 : 24} />
        {(coreStatus === 'running' || holding) && !showResult && <span className="orbit-ring core-ring" />}
        {showResult && result.modelInvoked && <strong className="orbit-confidence">{displayConfidence}%</strong>}
      </div>
    </div>

    {showResult && <div className="orbit-result">
      <p className="eyebrow">RECOMMENDATION READY</p>
      <h2>{result.headline}</h2>
    </div>}
    {holding && <div className="orbit-result"><p className="eyebrow">STILL WORKING</p><h2>Finalizing your recommendation…</h2></div>}

    <div className="pstatus-list">
      {evidenceAgents.map(agent => <StatusRow key={agent.key} agent={agent} elapsedMs={elapsedMs} holding={holding} />)}
      <StatusRow agent={reasoningAgent} elapsedMs={elapsedMs} startAt={REASONING_START} holding={holding} />
    </div>

    <p className="safe-note"><ShieldCheck size={16} />This is a decision-support workflow. A qualified reviewer retains final authority.</p>
  </div></AppLayout>;
}
