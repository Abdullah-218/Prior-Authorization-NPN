import { Check, Clock3, FileCheck2, Gauge, ShieldCheck, TrendingUp, Workflow } from 'lucide-react';
import '../../priorityIntelligenceHub.css';

// Static, explanatory only — same convention as PolicyIntelligenceHub.jsx
// (2026-08-21): nothing here reads from an API, the priority_intelligence
// service, or a live queue. No case IDs, scores, or queue metrics — those
// were in an earlier version and got explicit feedback (2026-08-22: "too
// large... just a simple illustration... remove the [fake] data, just a
// flow of how everything works"). This version carries zero numbers, same
// as PolicyIntelligenceHub — every label is a conceptual step, not a
// value that could be mistaken for a live prediction.
//
// Structure/CSS deliberately cloned from the proven PolicyIntelligenceHub
// pattern (rag -> triad -> policyAgent -> mlTriage) rather than invented
// fresh: Pend Cases -> triad(Triage Signals / Queue Intelligence core /
// Live Signals) -> LangGraph Agent -> XGBoost Ranker. Same reasoning
// applies here as there — a linear top-to-bottom story reads clearly in
// 5-10s; it doesn't need to be a literal call graph. Feature names,
// "no LLM call", and the safety-floor concept are real facts about
// ProAuth_AI_ML/priority_intelligence; case IDs/scores are gone entirely
// rather than being labeled illustrative, per feedback.
const NODES = {
  pend: {
    key: 'pend', icon: Workflow, title: 'PEND Cases', subtitle: 'Awaiting Review',
    body: 'Only requests still marked PEND after the original triage evaluation enter this pipeline.',
  },
  triageSignals: {
    key: 'triageSignals', icon: FileCheck2, title: 'Triage Signals', subtitle: 'Reused Scores',
    body: 'Reuses the policy, documentation and clinical evidence scores already produced during the original triage evaluation — not recalculated.',
  },
  liveSignals: {
    key: 'liveSignals', icon: Gauge, title: 'Live Signals', subtitle: 'Care & Risk',
    body: "Captures the case's current urgency, care setting and clinical risk at the moment of ranking.",
  },
  agent: {
    key: 'agent', icon: Workflow, title: 'LangGraph Agent', subtitle: 'Queue Orchestrator',
    body: 'Deterministic orchestration — validates the case and invokes the ranking pipeline.',
    state: 'No LLM Call',
  },
  ranker: {
    key: 'ranker', icon: TrendingUp, title: 'XGBoost Ranker', subtitle: 'Priority Prediction',
    body: "ML ranking model that scores each case's review priority — it ranks, it never approves or denies.",
  },
};

function Node({ node, big }) {
  const Icon = node.icon;
  return (
    <div className={`piq-node piq-node--${node.key}${big ? ' piq-node--big' : ''}`} tabIndex={0}>
      <span className="piq-node-icon"><Icon size={big ? 18 : 15} /></span>
      <div className="piq-node-text">
        <strong>{node.title}</strong>
        <small>{node.subtitle}</small>
      </div>
      {node.state && <span className="piq-node-state"><Check size={9} />{node.state}</span>}
      <div className="piq-tooltip" role="tooltip">{node.body}</div>
    </div>
  );
}

function Connector({ id, className }) {
  return (
    <div className={`piq-connector ${className}`}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path id={id} className="piq-connector-path" d="M50,0 C46,35 54,65 50,100" />
        <circle r="2.2" className="piq-particle">
          <animateMotion dur="2.4s" repeatCount="indefinite">
            <mpath href={`#${id}`} xlinkHref={`#${id}`} />
          </animateMotion>
        </circle>
      </svg>
    </div>
  );
}

function TriadConnectors() {
  return (
    <svg className="piq-triad-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <path id="piq-curve-triage" className="piq-curve piq-curve--triage" d="M27,50 C35,72 41,72 47,52" />
      <path id="piq-curve-live" className="piq-curve piq-curve--live" d="M73,50 C65,72 59,72 53,52" />
      <circle r="1.7" className="piq-particle">
        <animateMotion dur="2.7s" repeatCount="indefinite"><mpath href="#piq-curve-triage" xlinkHref="#piq-curve-triage" /></animateMotion>
      </circle>
      <circle r="1.7" className="piq-particle">
        <animateMotion dur="3s" repeatCount="indefinite" begin="0.4s"><mpath href="#piq-curve-live" xlinkHref="#piq-curve-live" /></animateMotion>
      </circle>
    </svg>
  );
}

// The one "3D model" centerpiece — layered, glass, perspective-tilted
// card, identical technique to PolicyIntelligenceHub's PolicyCore (see
// that file for why: plain CSS perspective/rotateX/rotateY + offset
// pseudo-layers reads as genuine depth without pulling react-three-fiber
// into a card that only needs hover interactivity).
function QueueCore() {
  return (
    <div className="piq-core-wrap">
      <div className="piq-core" tabIndex={0}>
        <span className="piq-core-glow" aria-hidden="true" />
        <span className="piq-core-layer piq-core-layer--2" aria-hidden="true" />
        <span className="piq-core-layer piq-core-layer--1" aria-hidden="true" />
        <div className="piq-core-face">
          <span className="piq-core-badge"><ShieldCheck size={10} />LIVE QUEUE STATE</span>
          <strong className="piq-core-title">QUEUE INTELLIGENCE</strong>
          <span className="piq-core-sub">Wait Time &amp; SLA Pressure</span>
          <span className="piq-core-truth">PRIORITIZATION INPUT</span>
        </div>
        <div className="piq-tooltip piq-tooltip--core" role="tooltip">
          How long a case has waited and how close it is to its SLA — recalculated live, not stored from the
          original triage.
        </div>
      </div>
    </div>
  );
}

export default function PriorityIntelligenceHub() {
  return (
    <div className="piq">
      <div className="piq-graph">
        <div className="piq-slot piq-slot--pend"><Node node={NODES.pend} /></div>
        <Connector id="piq-path-pend-triad" className="piq-slot piq-slot--connA" />

        <div className="piq-slot piq-slot--triad">
          <TriadConnectors />
          <Node node={NODES.triageSignals} />
          <QueueCore />
          <Node node={NODES.liveSignals} />
        </div>

        <Connector id="piq-path-triad-agent" className="piq-slot piq-slot--connB" />
        <div className="piq-slot piq-slot--agent"><Node node={NODES.agent} /></div>

        <Connector id="piq-path-agent-ranker" className="piq-slot piq-slot--connC" />
        <div className="piq-slot piq-slot--ranker">
          <Node node={NODES.ranker} big />
          <div className="piq-outcomes">
            <span className="piq-outcome piq-outcome--high">HIGH</span>
            <span className="piq-outcome piq-outcome--medium">MEDIUM</span>
            <span className="piq-outcome piq-outcome--low">LOW</span>
          </div>
          <p className="piq-safety-note"><ShieldCheck size={11} />Emergency &amp; SLA-critical cases carry a protected priority floor</p>
        </div>
      </div>

      <aside className="piq-explainer">
        <p className="piq-explainer-eyebrow">HOW IT WORKS</p>
        <p className="piq-explainer-copy">
          Only requests still marked PEND after the original triage evaluation enter this pipeline. A LangGraph
          orchestrator — deterministic, no LLM call — pulls together the evidence already produced during triage
          with live queue conditions like waiting time and SLA pressure.
        </p>
        <p className="piq-explainer-copy">
          Those combined signals feed an XGBoost ranking model that scores each case's review priority. A separate,
          deterministic safety layer guarantees emergency and SLA-critical cases can never be ranked below a
          protected priority floor.
        </p>
        <ul className="piq-explainer-points">
          <li><Clock3 size={13} /><span>Re-ranked, not retrained — a new PEND case or elapsed queue time re-invokes the same model with fresh inputs</span></li>
          <li><ShieldCheck size={13} /><span>Safety first — emergency and SLA-critical cases have a guaranteed priority floor the model can't override</span></li>
          <li><Check size={13} /><span>Ranks, doesn't decide — orders the review queue; a nurse still makes every call</span></li>
        </ul>
      </aside>
    </div>
  );
}
