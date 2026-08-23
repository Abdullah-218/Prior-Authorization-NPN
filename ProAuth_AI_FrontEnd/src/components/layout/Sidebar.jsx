import { Activity, Bell, ChevronDown, Clock3, ClipboardCheck, FileText, HeartPulse, LayoutDashboard, MoreHorizontal, Plus, Settings, ShieldCheck, UploadCloud, UserCheck, Users, Zap } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useRole } from '../../context/RoleContext';
import { useAuth } from '../../hooks/useAuth';
import { useLiveRequests } from '../../hooks/useLiveRequests';
import { usePriorityQueue } from '../../hooks/usePriorityQueue';
import { requests } from '../../data/requests';
import { dashboardService } from '../../services/dashboardService';

// The real pipeline a request moves through — doctor files it, nurse (or
// admin) reviews it, insurance/admin makes the final call. "Active
// workspace" used to be the literal same "Clinical command center" label
// with 7 identical decorative bars under it for every role; this instead
// names each role's actual station and highlights where that role sits
// in the real 3-stage pipeline. Patient/readonly isn't a pipeline actor
// (they only ever view their own status), so they get a label with no
// stage strip rather than a misleading "stage 0 of 3".
const WORKSPACE_TITLE = {
  doctor: 'Doctor workspace',
  nurse: 'Nurse review station',
  insurance: 'Insurance authorization center',
  reviewer: 'Insurance authorization center',
  user: 'Member portal',
  readonly: 'Member portal',
};
const PIPELINE_STAGES = ['Doctor', 'Nurse', 'Insurance'];
const PIPELINE_STAGE_INDEX = { doctor: 0, nurse: 1, insurance: 2, reviewer: 2 };

export default function Sidebar() {
  const { role, profile, can } = useRole();
  const { user } = useAuth();
  // Keeps the shared requests[] array fresh for the "Authorization queue"
  // badge below — same shared array every page reads/polls, so this is an
  // additional poller on the same underlying data, not a new data source.
  const { status: liveStatus } = useLiveRequests();
  const { priorityByAuthorization, status: priorityStatus } = usePriorityQueue();
  const pendingQueueCount = requests.filter(r => r.status === 'Needs Review').length;

  // "Review capacity" used to be a hardcoded '12'/'68%' vs '3'/'42%' pair
  // keyed only on whether the role can review at all — same two fake
  // numbers regardless of anyone's actual queue. Replaced with a real,
  // role-appropriate metric: reviewers see their real queue size + how
  // much of it is high-priority; a doctor (who doesn't review anything)
  // sees their own active requests + their real approval rate instead of
  // a borrowed "review" framing that never applied to them.
  let workload = { label: 'ACTIVE REQUESTS', count: 0, pct: 0, pctTitle: '' };
  if (liveStatus === 'done') {
    if (role === 'nurse') {
      const queue = dashboardService.getNurseDashboard().requests;
      const highCount = queue.filter(r => priorityByAuthorization[r.id]?.priorityTier === 'HIGH').length;
      workload = {
        label: 'REVIEW QUEUE', count: queue.length,
        pct: priorityStatus === 'done' && queue.length ? Math.round((highCount / queue.length) * 100) : 0,
        pctTitle: 'Share of your queue that is high priority',
      };
    } else if (role === 'insurance' || role === 'reviewer') {
      const queue = requests.filter(r => r.status === 'Needs Review');
      const highCount = queue.filter(r => priorityByAuthorization[r.id]?.priorityTier === 'HIGH').length;
      workload = {
        label: 'PENDING QUEUE', count: queue.length,
        pct: priorityStatus === 'done' && queue.length ? Math.round((highCount / queue.length) * 100) : 0,
        pctTitle: 'Share of the queue that is high priority',
      };
    } else if (role === 'doctor' && user) {
      const dashboard = dashboardService.getDoctorDashboard(user.id);
      const activeCount = dashboard.requests.filter(r => !['Approved', 'Denied', 'Rejected'].includes(r.status)).length;
      workload = {
        label: 'ACTIVE REQUESTS', count: activeCount,
        pct: dashboard.requests.length ? Math.round((dashboard.approvedRequests.length / dashboard.requests.length) * 100) : 0,
        pctTitle: 'Share of your submitted requests that were approved',
      };
    } else if ((role === 'user' || role === 'readonly')) {
      const own = requests;
      const approved = own.filter(r => r.status === 'Approved').length;
      workload = {
        label: 'MY REQUESTS', count: own.length,
        pct: own.length ? Math.round((approved / own.length) * 100) : 0,
        pctTitle: 'Share of your requests that were approved',
      };
    }
  }
  const workloadReady = liveStatus === 'done' && ((role !== 'nurse' && role !== 'insurance' && role !== 'reviewer') || priorityStatus === 'done');
  const readonlyWorkspace = [[Users, 'Profile', '/profile', true], [ShieldCheck, 'My Policy', '/my-policy', true], [Activity, 'Diagnosis', '/diagnosis', true], [ClipboardCheck, 'My Request', '/my-request', true], [FileText, 'Decision', '/decision', true], [UploadCloud, 'Documents', '/documents', true], [Clock3, 'Timeline', '/timeline', true]];
  const workspace = (role === 'user' || role === 'readonly') ? readonlyWorkspace : role === 'nurse' ? [[LayoutDashboard, 'Overview', '/dashboard', true], [ClipboardCheck, 'Clinical review queue', '/nurse/review', true], [Users, 'Patients', '/patients', can('patients')]] : role === 'doctor' ? [[LayoutDashboard, 'Dashboard', '/dashboard', true], [Plus, 'New authorization', '/new-authorization', can('create')], [FileText, 'Total Requests', '/doctor/requests', true], [Activity, 'Approved Requests', '/doctor/requests/approved', true], [UploadCloud, 'Need More Information', '/doctor/requests/need-information', true], [Users, 'Patients', '/doctor/patients', can('patients')], [Bell, 'Notifications', '/doctor/notifications', true]] : [[LayoutDashboard, 'Overview', '/dashboard', true], [Plus, 'New authorization', '/new-authorization', can('create')], [FileText, 'All Requests', '/insurance/requests', true], [Zap, 'Automated Approval', '/insurance/requests/automated', true], [UserCheck, 'Manual Approval', '/insurance/requests/manual', true], [ClipboardCheck, 'Authorization queue', '/queue', can('queue')], [Users, 'Patients', '/patients', can('patients')]];
  const intelligence = [[ShieldCheck, 'Policies', '/policies', can('policies')], [Activity, 'Analytics', '/analytics', can('analytics')], [Clock3, 'Audit trail', '/audit', can('audit')]];
  const links = (items) => <>{items.filter(item => item[3]).map(([ItemIcon, label, to]) => <NavLink end={to === '/dashboard' || to === '/doctor/requests' || to === '/insurance/requests'} key={to} to={to} className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}><span className="nav-icon"><ItemIcon size={17}/></span><span>{label}</span>{label === 'Authorization queue' && can('queue') && <em>{liveStatus === 'done' ? pendingQueueCount : '—'}</em>}</NavLink>)}</>;
  const pipelineStage = PIPELINE_STAGE_INDEX[role];
  return <aside className="sidebar sidebar-new"><div className="brand"><span className="brand-mark"><HeartPulse size={20}/></span><span>PROAUTH <b>IQ</b></span></div><div className="clinical-station"><div className="station-top"><span className="workspace-dot"></span><small>ACTIVE WORKSPACE</small><ChevronDown size={13}/></div><strong>{WORKSPACE_TITLE[role] || 'Clinical command center'}</strong>{pipelineStage != null && <div className="station-line">{PIPELINE_STAGES.map((stage, i) => <div key={stage} className={`station-stage ${i === pipelineStage ? 'current' : ''}`} title={i === pipelineStage ? `You are here — ${stage}` : stage}><i/><small>{stage}</small></div>)}</div>}</div><nav><p className="nav-label">WORKSPACE</p>{links(workspace)}{role !== 'user' && role !== 'readonly' && <><p className="nav-label intelligence-label">INTELLIGENCE</p>{links(intelligence)}</>}</nav><div className="sidebar-bottom"><div className="workload"><div><small>{workload.label}</small><strong>{workloadReady ? workload.count : '—'} <span>{role === 'doctor' || role === 'user' || role === 'readonly' ? 'total' : 'active'}</span></strong></div><div className="ring" style={workloadReady ? { background: `conic-gradient(#4d9e98 ${workload.pct}%, #dce9ed 0)` } : undefined} title={workload.pctTitle}><span>{workloadReady ? `${workload.pct}%` : '—'}</span></div></div><a className="nav-item settings-link"><span className="nav-icon"><Settings size={17}/></span>Settings</a><div className="profile"><div className="avatar navy">{profile.initials}</div><div><strong>{profile.name}</strong><small>{profile.detail}</small></div><MoreHorizontal size={17}/></div></div></aside>;
}
