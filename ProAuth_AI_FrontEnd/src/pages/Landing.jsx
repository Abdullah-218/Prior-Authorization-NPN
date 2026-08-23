import { ArrowRight, CheckCircle2, ClipboardCheck, FileSearch, HeartPulse, ListOrdered, ShieldCheck, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import '../landing.css';

const trustPoints = [
  { icon: ShieldCheck, title: 'Human-led decisions', detail: 'AI recommendations never override reviewer action.' },
  { icon: ClipboardCheck, title: 'Traceable evidence', detail: 'Policy, document, and decision activity is auditable.' },
  { icon: HeartPulse, title: 'Designed for care teams', detail: 'Clear workflows for providers and reviewers.' }
];

export default function Landing() {
  return <div className="landing">
    <header className="landing-nav"><div className="brand"><span className="brand-mark"><HeartPulse size={20}/></span><span>PROAUTH <b>IQ</b></span></div><Link to="/login" className="landing-login">Sign in <ArrowRight size={15}/></Link></header>
    <main className="landing-main"><section className="landing-hero"><div className="landing-copy"><p className="eyebrow">AGENTIC AI · RAG · ML TRIAGE PLATFORM</p><h1>Prior authorization,<br/><em>made transparent.</em></h1><p className="landing-lead">Specialized AI agents, policy retrieval grounded in real payer text, and a trained ML model triage every request — while every final decision stays with a clinical reviewer.</p><p className="landing-detail">ProAuth IQ runs a pipeline of dedicated Policy, Clinical, and Document agents that retrieve and ground evidence directly from real payer policy text, then hand a structured evidence set to a trained ML triage model for a confidence-scored recommendation. Requests flagged for review are automatically prioritized by urgency and clinical risk, so nurses see the most critical pending cases first — with every recommendation, evidence citation, and decision logged to a complete audit trail.</p><div className="landing-actions"><Link to="/login" className="landing-primary">Access your workspace <ArrowRight size={17}/></Link><span>Decision support, not autonomous decision-making.</span></div></div><div className="landing-visual"><div className="landing-orbit orbit-a"></div><div className="landing-orbit orbit-b"></div><div className="landing-dot-grid"></div><div className="landing-card card-a"><span className="landing-card-icon"><Sparkles size={18}/></span><div><small>AI triage</small><strong>Evidence prepared</strong></div><CheckCircle2 size={16} className="landing-card-check"/></div><div className="landing-card card-b"><span className="landing-card-icon alt"><FileSearch size={18}/></span><div><small>Policy intelligence</small><strong>Relevant criteria retrieved</strong></div></div><div className="landing-card card-c"><span className="landing-card-icon amber"><ListOrdered size={18}/></span><div><small>Priority triage</small><strong>High-risk pending cases ranked first</strong></div></div></div></section><section className="landing-trust">{trustPoints.map(({ icon: Icon, title, detail }) => <div key={title}><Icon size={20}/><span><strong>{title}</strong><small>{detail}</small></span></div>)}</section></main>
  </div>;
}
