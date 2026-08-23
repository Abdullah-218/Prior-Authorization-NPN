import { useEffect, useState } from 'react';
import { AlertTriangle, Clock3, FileText, ShieldCheck } from 'lucide-react';
import { Badge, Card, DataState } from '../components/ui';
import { StatCard } from '../components/dashboard/DashboardWidgets';
import PriorityIntelligenceHub from '../components/nurse/PriorityIntelligenceHub';
import { dashboardService } from '../services/dashboardService';
import { useLiveRequests } from '../hooks/useLiveRequests';
import { usePriorityQueue } from '../hooks/usePriorityQueue';
import SimplePage from './SimplePage';
import './analytics.css';

const TIER_BARS = [
  { key: 'HIGH', label: 'High', color: 'var(--red)' },
  { key: 'MEDIUM', label: 'Moderate', color: 'var(--amber)' },
  { key: 'LOW', label: 'Low', color: 'var(--blue)' },
];

function TierComparisonBar({ tierCounts }) {
  const [hoverKey, setHoverKey] = useState(null);
  const [mounted, setMounted] = useState(false);
  const max = Math.max(1, tierCounts.HIGH, tierCounts.MEDIUM, tierCounts.LOW);
  useEffect(() => { const timer = setTimeout(() => setMounted(true), 60); return () => clearTimeout(timer); }, []);

  return <div className="bars enhanced-bars">{TIER_BARS.map((tier, i) => <div key={tier.key} onMouseEnter={() => setHoverKey(tier.key)} onMouseLeave={() => setHoverKey(null)}>
    {hoverKey === tier.key && <div className="chart-tooltip">{tierCounts[tier.key]} case{tierCounts[tier.key] === 1 ? '' : 's'}</div>}
    <i className={hoverKey === tier.key ? 'active' : ''} style={{ height: mounted ? `${(tierCounts[tier.key] / max) * 100}%` : '0%', background: tier.color, transitionDelay: `${i * 60}ms` }}/>
    <span>{tier.label}</span>
  </div>)}</div>;
}

// Nurse-scoped analytics — priority tiers (HIGH/MEDIUM/LOW) already power
// the review queue's filters and the dashboard's stat tiles
// (usePriorityQueue()/RoleDashboard.jsx); this page just presents the same
// tier breakdown as a dedicated, visual comparison instead of plain
// numbers on the dashboard. All computed client-side from the already-
// loaded "Needs Review" queue — no new endpoint.
export default function NurseAnalytics() {
  const { status: listStatus, error: listError } = useLiveRequests();
  const { priorityByAuthorization, status: priorityStatus } = usePriorityQueue();

  if (listStatus !== 'done' || priorityStatus !== 'done') {
    return <SimplePage title="Queue analytics" subtitle="Priority breakdown across the clinical review queue.">
      <DataState status={listStatus !== 'done' ? listStatus : priorityStatus} error={listError}/>
    </SimplePage>;
  }

  const reviewRequests = dashboardService.getNurseDashboard().requests;
  const evidenceNeededCount = reviewRequests.filter(request => request.status === 'Additional Information Required').length;
  const tierCounts = { HIGH: 0, MEDIUM: 0, LOW: 0, UNRANKED: 0 };
  reviewRequests.forEach(request => {
    const tier = priorityByAuthorization[request.id]?.priorityTier;
    if (tier && tier in tierCounts) tierCounts[tier] += 1;
    else tierCounts.UNRANKED += 1;
  });
  const ranked = tierCounts.HIGH + tierCounts.MEDIUM + tierCounts.LOW;
  const pct = count => ranked ? Math.round((count / ranked) * 100) : 0;

  return <SimplePage title="Queue analytics" subtitle="Priority breakdown across the clinical review queue.">
    <Card className="attention" style={{ marginBottom: 15 }}>
      <div className="section-title"><div><p className="eyebrow">PRIORITY INTELLIGENCE</p><h3>Pending case prioritization</h3><p className="piq-heading-sub">How PEND cases are ranked into your review queue</p></div><Badge type="blue">View only</Badge></div>
      <PriorityIntelligenceHub/>
    </Card>
    <div className="analytics-grid">
      <StatCard label="High risk" value={tierCounts.HIGH} note={`${pct(tierCounts.HIGH)}% of ranked cases`} tone="red" icon={<AlertTriangle/>}/>
      <StatCard label="Moderate risk" value={tierCounts.MEDIUM} note={`${pct(tierCounts.MEDIUM)}% of ranked cases`} tone="amber" icon={<Clock3/>}/>
      <StatCard label="Low risk" value={tierCounts.LOW} note={`${pct(tierCounts.LOW)}% of ranked cases`} tone="blue" icon={<ShieldCheck/>}/>
      <Card className="chart">
        <div className="section-title"><h3>Priority queue comparison</h3><Badge>{reviewRequests.length} in queue</Badge></div>
        <TierComparisonBar tierCounts={tierCounts}/>
      </Card>
    </div>
    <Card className="chart" style={{ marginTop: 15 }}>
      <div className="section-title"><div><p className="eyebrow">EVIDENCE</p><h3>Additional information requested</h3></div><FileText size={18}/></div>
      <p className="body-copy">{evidenceNeededCount} of the {reviewRequests.length} case{reviewRequests.length === 1 ? '' : 's'} in your queue {evidenceNeededCount === 1 ? 'is' : 'are'} waiting on additional evidence from the provider.{tierCounts.UNRANKED > 0 && ` ${tierCounts.UNRANKED} case${tierCounts.UNRANKED === 1 ? '' : 's'} ${tierCounts.UNRANKED === 1 ? 'has' : 'have'} not been ranked yet.`}</p>
      <p className="hint">Priority reflects SLA pressure, urgency, and clinical risk — hover a priority badge in the review queue for the specific reasons behind a case's tier.</p>
    </Card>
  </SimplePage>;
}
