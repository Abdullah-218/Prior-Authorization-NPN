import { useEffect, useState } from 'react';
import { Activity, Clock3, TrendingUp, UserCheck, Zap } from 'lucide-react';
import { Badge, Card, DataState } from '../components/ui';
import { StatCard } from '../components/dashboard/DashboardWidgets';
import { dashboardService } from '../services/dashboardService';
import { useAuth } from '../hooks/useAuth';
import { useLiveRequests } from '../hooks/useLiveRequests';
import SimplePage from './SimplePage';
import './analytics.css';

function buildVolumeData(ownRequests) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    return d;
  });
  return days.map(d => ({
    day: d.toLocaleDateString('en-US', { weekday: 'short' }),
    count: ownRequests.filter(r => r.submittedAtRaw && new Date(r.submittedAtRaw).toDateString() === d.toDateString()).length,
  }));
}

function VolumeBar({ data }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const [mounted, setMounted] = useState(false);
  const max = Math.max(1, ...data.map(d => d.count));
  useEffect(() => { const timer = setTimeout(() => setMounted(true), 60); return () => clearTimeout(timer); }, []);

  return <div className="bars enhanced-bars">{data.map((d, i) => <div key={`${d.day}-${i}`} onMouseEnter={() => setHoverIndex(i)} onMouseLeave={() => setHoverIndex(null)}>
    {hoverIndex === i && <div className="chart-tooltip">{d.count} request{d.count === 1 ? '' : 's'}</div>}
    <i className={hoverIndex === i ? 'active' : ''} style={{ height: mounted ? `${(d.count / max) * 100}%` : '0%', transitionDelay: `${i * 40}ms` }}/>
    <span>{d.day}</span>
  </div>)}</div>;
}

function AutomatedGauge({ automated, total }) {
  const pct = total ? Math.round((automated / total) * 100) : 0;
  const [animatedPct, setAnimatedPct] = useState(0);
  const [hover, setHover] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setAnimatedPct(pct), 80); return () => clearTimeout(timer); }, [pct]);
  const radius = 54;
  const circumference = 2 * Math.PI * radius;

  return <div className="gauge-wrap" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
    <svg className="gauge-svg" viewBox="0 0 130 130">
      <circle className="gauge-track" cx="65" cy="65" r={radius}/>
      <circle className="gauge-progress" cx="65" cy="65" r={radius} strokeDasharray={circumference} strokeDashoffset={circumference * (1 - animatedPct / 100)}/>
    </svg>
    <div className="gauge-center"><strong>{automated}</strong><span>Automated</span></div>
    {hover && <div className="chart-tooltip gauge-tooltip">{automated} of {total} decided requests · {pct}%</div>}
  </div>;
}

function ManualWaffle({ manual, total }) {
  const pct = total ? Math.round((manual / total) * 100) : 0;
  const filled = Math.round(pct / 10);
  const [hoverIndex, setHoverIndex] = useState(null);

  return <div className="waffle-wrap">
    <div className="waffle-grid">{Array.from({ length: 10 }, (_, i) => <div key={i} className={`waffle-cell ${i < filled ? 'filled' : ''}`} style={{ animationDelay: `${i * 35}ms` }} onMouseEnter={() => setHoverIndex(i)} onMouseLeave={() => setHoverIndex(null)}><UserCheck size={14}/></div>)}</div>
    <div className="waffle-legend">{hoverIndex !== null ? <span>Each square represents 10% of your decided requests</span> : <span><strong>{manual}</strong> of {total} decided requests were manually reviewed · {pct}%</span>}</div>
  </div>;
}

// Doctor-scoped analytics — a separate page from pages/Analytics.jsx (the
// insurance/admin version), not a variant rendered by it. That page calls
// GET /analytics/summary, which is authorize('ADMIN')-gated server-side
// (see authorizationRoutes.js) and reports global counts across every
// provider — a DOCTOR token gets a 403, and even if it didn't, the numbers
// wouldn't be this doctor's own. Everything below is instead computed
// client-side from this doctor's own already-loaded requests, same "real
// data, no new endpoint" pattern dashboardService already uses for the
// insurance dashboard's automated/manual buckets. Visual components are
// intentionally duplicated from Analytics.jsx rather than imported (they
// aren't exported there, and this page's data shape differs enough — no
// summary object, doctor-scoped totals — that sharing one function across
// both would need more branching than just keeping two small copies).
export default function DoctorAnalytics() {
  const { user } = useAuth();
  const { status: listStatus, error: listError } = useLiveRequests();

  if (listStatus !== 'done') {
    return <SimplePage title="Your analytics" subtitle="Patterns across the requests you've submitted.">
      <DataState status={listStatus} error={listError}/>
    </SimplePage>;
  }

  const dashboard = dashboardService.getDoctorDashboard(user.id);
  const totalDecided = dashboard.automatedApprovals.length + dashboard.manualApprovals.length;
  const approvalRate = dashboard.requests.length ? Math.round((dashboard.approvedRequests.length / dashboard.requests.length) * 1000) / 10 : 0;
  const automationRate = dashboard.requests.length ? Math.round((dashboard.automatedApprovals.length / dashboard.requests.length) * 1000) / 10 : 0;
  const volumeData = buildVolumeData(dashboard.requests);

  return <SimplePage title="Your analytics" subtitle="Patterns across the requests you've submitted.">
    <div className="analytics-grid">
      <StatCard label="Approval rate" value={`${approvalRate}%`} note={`${dashboard.approvedRequests.length} of ${dashboard.requests.length} requests`} tone="green" icon={<Activity/>}/>
      <StatCard label="Straight-through rate" value={`${automationRate}%`} note={`${dashboard.automatedApprovals.length} auto-decided, no human touch`} tone="blue" icon={<Zap/>}/>
      <StatCard label="This week" value={dashboard.requestsThisWeek.length} note="Requests submitted in the last 7 days" tone="amber" icon={<TrendingUp/>}/>
      <Card className="chart">
        <div className="section-title"><h3>Your authorization volume</h3><Badge>Last 7 days</Badge></div>
        <VolumeBar data={volumeData}/>
      </Card>
    </div>
    <div className="split-charts">
      <Card className="split-chart-card">
        <div className="section-title"><div><p className="eyebrow">STRAIGHT-THROUGH PROCESSING</p><h3>Automated approval</h3></div><Badge type="green"><Zap size={11}/>Automated</Badge></div>
        <AutomatedGauge automated={dashboard.automatedApprovals.length} total={totalDecided}/>
      </Card>
      <Card className="split-chart-card">
        <div className="section-title"><div><p className="eyebrow">HUMAN-IN-THE-LOOP</p><h3>Manual approval</h3></div><Badge type="blue"><UserCheck size={11}/>Reviewer-confirmed</Badge></div>
        <ManualWaffle manual={dashboard.manualApprovals.length} total={totalDecided}/>
      </Card>
    </div>
    <Card className="chart" style={{ marginTop: 15 }}>
      <div className="section-title"><div><p className="eyebrow">PENDING</p><h3>Awaiting a reviewer decision</h3></div><Clock3 size={18}/></div>
      <p className="body-copy">{dashboard.needsReviewRequests.length} of your request{dashboard.needsReviewRequests.length === 1 ? '' : 's'} {dashboard.needsReviewRequests.length === 1 ? 'is' : 'are'} currently sitting in the nurse/admin review queue, out of {dashboard.requests.length} total request{dashboard.requests.length === 1 ? '' : 's'} you've submitted.</p>
    </Card>
  </SimplePage>;
}
