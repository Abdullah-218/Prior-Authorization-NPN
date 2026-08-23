import { Activity, Check, FileCheck2, FileSearch, Search, ShieldCheck, Sparkles } from 'lucide-react';
import '../../policyIntelligenceHub.css';

// Static, explanatory only — see module docstring at the bottom of this
// file for the full "why" (2026-08-21, explicit request). Nothing here
// reads from an API, a live evaluation, or real request/policy data —
// every label is illustrative, not a live count/ID/confidence value.
//
// Deliberately just 5 named agents + the policy core (2026-08-21,
// simplified per feedback — an earlier version also showed Reasoning
// Engine and Companion Agent as their own cards, which made the whole
// diagram too tall/busy for a 5-10s read). Reasoning/explanation still
// happen in the real pipeline; they're just not each a separate stop on
// this diagram anymore — the story ends at "ML Triage takes the decision."
const NODES = {
  rag: {
    key: 'rag', icon: Search, title: 'RAG', subtitle: 'Evidence Search',
    body: 'Retrieves relevant coverage and medical necessity evidence.',
    state: 'Evidence Retrieved',
  },
  policyAgent: {
    key: 'policyAgent', icon: FileSearch, title: 'Policy Agent', subtitle: 'Interpretation',
    body: 'Identifies the applicable policy and extracts its coverage criteria.',
  },
  clinical: {
    key: 'clinical', icon: Activity, title: 'Clinical Agent', subtitle: 'Clinical Evaluation',
    body: 'Evaluates diagnosis, indication and clinical criteria.',
  },
  document: {
    key: 'document', icon: FileCheck2, title: 'Document Agent', subtitle: 'Evidence Check',
    body: 'Checks whether submitted documents support the request.',
  },
  triage: {
    key: 'triage', icon: Sparkles, title: 'ML Triage', subtitle: 'Decision Intelligence',
    body: 'Uses the combined evidence to recommend the next step.',
  },
};

function Node({ node, big }) {
  const Icon = node.icon;
  return (
    <div className={`pih-node pih-node--${node.key}${big ? ' pih-node--big' : ''}`} tabIndex={0}>
      <span className="pih-node-icon"><Icon size={big ? 18 : 15} /></span>
      <div className="pih-node-text">
        <strong>{node.title}</strong>
        <small>{node.subtitle}</small>
      </div>
      {node.state && <span className="pih-node-state"><Check size={9} />{node.state}</span>}
      <div className="pih-tooltip" role="tooltip">{node.body}</div>
    </div>
  );
}

// A single, reusable vertical connector — a gently curved SVG path with a
// small particle animated along it (native SMIL animateMotion, no JS/
// library needed) to suggest evidence flowing downstream. preserveAspectRatio
// "none" deliberately stretches the path to exactly fill whatever box CSS
// gives this connector at any breakpoint, rather than needing to know the
// real pixel layout in advance.
function Connector({ id, className }) {
  return (
    <div className={`pih-connector ${className}`}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path id={id} className="pih-connector-path" d="M50,0 C46,35 54,65 50,100" />
        <circle r="2.2" className="pih-particle">
          <animateMotion dur="2.4s" repeatCount="indefinite">
            <mpath href={`#${id}`} xlinkHref={`#${id}`} />
          </animateMotion>
        </circle>
      </svg>
    </div>
  );
}

// The two branch curves (Clinical -> Policy, Document -> Policy) — drawn
// as one small SVG layered behind the triad row so they visually meet at
// the policy core regardless of exact card widths at any breakpoint.
function TriadConnectors() {
  return (
    <svg className="pih-triad-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <path id="pih-curve-clinical" className="pih-curve pih-curve--clinical" d="M27,50 C35,72 41,72 47,52" />
      <path id="pih-curve-document" className="pih-curve pih-curve--document" d="M73,50 C65,72 59,72 53,52" />
      <circle r="1.7" className="pih-particle">
        <animateMotion dur="2.7s" repeatCount="indefinite"><mpath href="#pih-curve-clinical" xlinkHref="#pih-curve-clinical" /></animateMotion>
      </circle>
      <circle r="1.7" className="pih-particle">
        <animateMotion dur="3s" repeatCount="indefinite" begin="0.4s"><mpath href="#pih-curve-document" xlinkHref="#pih-curve-document" /></animateMotion>
      </circle>
    </svg>
  );
}

// Compact by design (2026-08-21, feedback: "same structure it had before"
// — the earlier full-hub version made this the single largest, most
// dominant element on the page; scaled back down here closer to how
// PolicyDocument3D.jsx originally read: small, still clearly the center
// of gravity via its glow/badge/layered-page treatment, but not towering
// over its own neighbors).
function PolicyCore() {
  return (
    <div className="pih-core-wrap">
      <div className="pih-core" tabIndex={0}>
        <span className="pih-core-glow" aria-hidden="true" />
        <span className="pih-core-layer pih-core-layer--2" aria-hidden="true" />
        <span className="pih-core-layer pih-core-layer--1" aria-hidden="true" />
        <div className="pih-core-face">
          <span className="pih-core-badge"><ShieldCheck size={10} />ACTIVE POLICY</span>
          <strong className="pih-core-title">POLICY</strong>
          <span className="pih-core-sub">Coverage &amp; Medical Necessity</span>
          <span className="pih-core-truth">SOURCE OF TRUTH</span>
        </div>
        <div className="pih-tooltip pih-tooltip--core" role="tooltip">
          Every authorization is evaluated against this policy — the single source of truth for coverage and medical necessity.
        </div>
      </div>
    </div>
  );
}

export default function PolicyIntelligenceHub() {
  return (
    <div className="pih">
      <div className="pih-graph">
        <div className="pih-slot pih-slot--rag"><Node node={NODES.rag} /></div>
        <Connector id="pih-path-rag-policy" className="pih-slot pih-slot--connA" />

        <div className="pih-slot pih-slot--triad">
          <TriadConnectors />
          <Node node={NODES.clinical} />
          <PolicyCore />
          <Node node={NODES.document} />
        </div>

        <Connector id="pih-path-policy-pa" className="pih-slot pih-slot--connB" />
        <div className="pih-slot pih-slot--pa"><Node node={NODES.policyAgent} /></div>

        <Connector id="pih-path-pa-triage" className="pih-slot pih-slot--connC" />
        <div className="pih-slot pih-slot--triage">
          <Node node={NODES.triage} big />
          <div className="pih-outcomes">
            <span className="pih-outcome pih-outcome--approve">APPROVE</span>
            <span className="pih-outcome pih-outcome--pend">PEND</span>
            <span className="pih-outcome pih-outcome--info">MORE INFORMATION</span>
          </div>
        </div>
      </div>

      <aside className="pih-explainer">
        <p className="pih-explainer-eyebrow">HOW IT WORKS</p>
        <p className="pih-explainer-copy">
          Every authorization is evaluated against an applicable coverage policy. RAG retrieves the relevant policy
          evidence, specialized agents evaluate clinical and documentation evidence, and the ML triage layer takes
          the resulting decision.
        </p>
        <p className="pih-explainer-copy">
          Along the way, deterministic checks — missing documentation, a specialty mismatch, a safety concern — route
          the request straight to a human reviewer instead of letting the model guess. The model only ever
          recommends a next step; a nurse or admin reviewer makes the final call.
        </p>
        <ul className="pih-explainer-points">
          <li><Check size={13} /><span>Evidence-grounded — every recommendation cites real, retrieved policy text</span></li>
          <li><Check size={13} /><span>Safety gates first — known risks route to review before the model ever runs</span></li>
          <li><Check size={13} /><span>Reviewer decides — the model recommends, a person approves every outcome</span></li>
        </ul>
      </aside>
    </div>
  );
}

// Deliberately static (2026-08-21, explicit request): this replaces the
// old react-three-fiber PolicyDocument3D — a real WebGL scene rendering a
// floating document plus a side panel of HARDCODED numbers styled to look
// live ("Evidence Retrieved: 12", "Coverage Match: 94%") next to a REAL
// "Active"/badge row that WAS wired to nothing. That mix of real-looking
// and fake-looking elements on the same panel is exactly what this
// component avoids: every string here is a conceptual label, never a
// count, percentage, confidence score, or policy ID, so nothing here can
// be mistaken for live evaluation output. Built in plain CSS/SVG rather
// than pulling react-three-fiber (already a dependency, used elsewhere in
// this app for HeroModel) into a dashboard card — this
// component's job is hover/tooltip interactivity across 6 elements, which
// real DOM + CSS :hover/:has() handles natively and far more reliably
// than bridging HTML into a WebGL raycasting scene would.
