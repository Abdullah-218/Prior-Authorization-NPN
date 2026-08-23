import { useEffect, useState } from 'react';
import { Activity, Clock3, UserCheck, Users, Zap } from 'lucide-react';
import { Badge, Card, DataState } from '../components/ui';
import { StatCard } from '../components/dashboard/DashboardWidgets';
import { dashboardService } from '../services/dashboardService';
import { analyticsApi } from '../services/analyticsApi';
import { useLiveRequests } from '../hooks/useLiveRequests';
import SimplePage from './SimplePage';
import './analytics.css';

function formatMs(ms) {
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.round((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function buildVolumeData(allRequests) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    return d;
  });
  return days.map(d => ({
    day: d.toLocaleDateString('en-US', { weekday: 'short' }),
    count: allRequests.filter(r => r.submittedAtRaw && new Date(r.submittedAtRaw).toDateString() === d.toDateString()).length,
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
    <div className="waffle-legend">{hoverIndex !== null ? <span>Each square represents 10% of decided requests</span> : <span><strong>{manual}</strong> of {total} decided requests were manually reviewed · {pct}%</span>}</div>
  </div>;
}

export default function Analytics() {
  const { status: listStatus, error: listError } = useLiveRequests();
  const [summary, setSummary] = useState(null);
  const [summaryStatus, setSummaryStatus] = useState('loading');

  useEffect(() => {
    let cancelled = false;
    analyticsApi.getSummary()
      .then(data => { if (!cancelled) { setSummary(data); setSummaryStatus('done'); } })
      .catch(() => { if (!cancelled) setSummaryStatus('error'); });
    return () => { cancelled = true; };
  }, []);

  if (listStatus !== 'done' || summaryStatus !== 'done') {
    return <SimplePage title="Authorization analytics" subtitle="Operational patterns across your authorization workflow.">
      <DataState status={listStatus !== 'done' ? listStatus : summaryStatus} error={listError}/>
    </SimplePage>;
  }

  const dashboard = dashboardService.getInsuranceDashboard();
  const totalDecided = summary.autoApproved + summary.autoDenied + summary.manualApproved + summary.humanDenied;
  const approvalRate = summary.totalRequests ? Math.round(((summary.autoApproved + summary.manualApproved) / summary.totalRequests) * 1000) / 10 : 0;
  const automationRate = summary.totalRequests ? Math.round((summary.autoProcessed / summary.totalRequests) * 1000) / 10 : 0;
  const overrideRate = totalDecided ? Math.round(((summary.manualApproved + summary.humanDenied) / totalDecided) * 1000) / 10 : 0;
  const volumeData = buildVolumeData(dashboard.requests);

  return <SimplePage title="Authorization analytics" subtitle="Operational patterns across your authorization workflow.">
    <div className="analytics-grid">
      <StatCard label="Approval rate" value={`${approvalRate}%`} note={`${summary.autoApproved + summary.manualApproved} of ${summary.totalRequests} requests`} tone="green" icon={<Activity/>}/>
      <StatCard label="Straight-through rate" value={`${automationRate}%`} note={`${summary.autoProcessed} auto-decided, no human touch`} tone="blue" icon={<Zap/>}/>
      <StatCard label="Human override rate" value={`${overrideRate}%`} note={`${summary.manualApproved + summary.humanDenied} of ${totalDecided} decided requests`} tone="amber" icon={<Users/>}/>
      <Card className="chart">
        <div className="section-title"><h3>Authorization volume</h3><Badge>Last 7 days</Badge></div>
        <VolumeBar data={volumeData}/>
      </Card>
    </div>
    <div className="split-charts">
      <Card className="split-chart-card">
        <div className="section-title"><div><p className="eyebrow">STRAIGHT-THROUGH PROCESSING</p><h3>Automated approval</h3></div><Badge type="green"><Zap size={11}/>Automated</Badge></div>
        <AutomatedGauge automated={summary.autoApproved} total={totalDecided}/>
      </Card>
      <Card className="split-chart-card">
        <div className="section-title"><div><p className="eyebrow">HUMAN-IN-THE-LOOP</p><h3>Manual approval</h3></div><Badge type="blue"><UserCheck size={11}/>Reviewer-confirmed</Badge></div>
        <ManualWaffle manual={summary.manualApproved} total={totalDecided}/>
      </Card>
    </div>
    <Card className="chart" style={{ marginTop: 15 }}>
      <div className="section-title"><div><p className="eyebrow">PENDING REVIEWER QUEUE</p><h3>Awaiting a final decision</h3></div><Clock3 size={18}/></div>
      <p className="body-copy">{summary.manualReviewPending} request{summary.manualReviewPending === 1 ? '' : 's'} currently sitting in the nurse/admin review queue, out of {summary.totalRequests} total requests on record.</p>
      <p className="hint">{summary.processingTime?.hasData
        ? <>Average automated processing time: <b>{formatMs(summary.processingTime.avgProcessingTimeMs)}</b>{summary.processingTime.medianProcessingTimeMs != null && ` (median ${formatMs(summary.processingTime.medianProcessingTimeMs)})`}, across {summary.processingTime.evaluatedCount} AI-evaluated request{summary.processingTime.evaluatedCount === 1 ? '' : 's'}{summary.processingTime.isEstimated && ' — shown as the typical range, since a few individual evaluations ran unusually slow (e.g. a rate-limit retry) and would have skewed the raw average'}. Measures the RAG + Agents + ML evaluation itself, not any human nurse/admin review time afterward.</>
        : 'No processing-time data available yet — this appears once at least one request has gone through the AI evaluation pipeline.'}</p>
    </Card>
  </SimplePage>;
}
