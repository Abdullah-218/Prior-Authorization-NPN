import { useEffect, useState } from 'react';
import { ChevronRight, Plus, Search, SlidersHorizontal } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import { Badge, Card, DataState, Pager } from '../components/ui';
import { useAuth } from '../hooks/useAuth';
import { useLiveRequests } from '../hooks/useLiveRequests';
import { usePriorityQueue } from '../hooks/usePriorityQueue';
import { requests } from '../data/requests';

const TIER_TONE = { HIGH: 'red', MEDIUM: 'amber', LOW: 'blue' };
const TIER_TABS = [
  { id: 'ALL', label: 'All priorities' },
  { id: 'HIGH', label: 'High' },
  { id: 'MEDIUM', label: 'Moderate' },
  { id: 'LOW', label: 'Low' },
];
const PAGE_SIZE = 10;

// Client-side pagination + priority filtering (2026-08-21+) — priority tier
// comes from usePriorityQueue(), which ranks the FULL "Needs Review" set
// server-side in one call (same source NurseReview.jsx already uses), not
// per-page. That's incompatible with the previous server-side pagination
// here (a tier filter over just one 10-row server page would silently miss
// same-tier rows sitting on other pages), so this now reads the full
// role-scoped requests[] array via useLiveRequests() and paginates the
// already-filtered result client-side instead — same pattern already
// proven on NurseReview.jsx/ReviewerPatients.jsx.
export default function Queue(){
  const { role } = useAuth();
  const navigate = useNavigate();
  const [search,setSearch]=useState('');
  const [attentionOnly,setAttentionOnly]=useState(false);
  const [tier,setTier]=useState('ALL');
  const [page,setPage]=useState(1);
  const { status: listStatus, error: listError } = useLiveRequests();
  const { priorityByAuthorization, status: priorityStatus } = usePriorityQueue();

  useEffect(() => { setPage(1); }, [tier, search, attentionOnly]);

  if(listStatus!=='done')return <AppLayout><div className="page queue"><DataState status={listStatus} error={listError}/></div></AppLayout>;

  const needsReview = requests.filter(r => r.status === 'Needs Review');
  const sortedByPriority = priorityStatus === 'done'
    ? [...needsReview].sort((a, b) => (priorityByAuthorization[a.id]?.queueRank ?? Infinity) - (priorityByAuthorization[b.id]?.queueRank ?? Infinity))
    : needsReview;
  const tierFiltered = tier === 'ALL' ? sortedByPriority : sortedByPriority.filter(r => priorityByAuthorization[r.id]?.priorityTier === tier);
  const visibleRequests=tierFiltered.filter(r=>{const matchesSearch=!search||[r.id,r.patient,r.diagnosis].some(field=>field?.toLowerCase().includes(search.toLowerCase()));const matchesAttention=!attentionOnly||r.tone!=='green';return matchesSearch&&matchesAttention;});
  const totalPages=Math.max(1, Math.ceil(visibleRequests.length / PAGE_SIZE));
  const currentPage=Math.min(page, totalPages);
  const pageRequests=visibleRequests.slice((currentPage-1)*PAGE_SIZE, currentPage*PAGE_SIZE);
  const viewPatient=r=>navigate(`/patients/${r.patientId || r.id}`);
  // minmax() floors + an explicit min-width (same defensive pattern as
  // nurse-review.css's .clinical-review-table) — plain fr units with no
  // floor let columns get visually squeezed/wrapped at typical viewport
  // widths once a Priority column was added; this instead guarantees each
  // column a minimum, and lets .request-table's overflow-x:auto scroll
  // horizontally if the viewport is too narrow, rather than cramming.
  const columns='72px minmax(150px,.8fr) minmax(190px,1.25fr) minmax(190px,1.25fr) minmax(140px,.9fr) minmax(120px,.85fr) minmax(110px,.8fr) 30px';
  const tableMinWidth=1180;

  return <AppLayout><div className="page queue"><div className="page-heading"><div><h1>Authorization queue</h1><p>Cases awaiting a final decision. Click any request to review and approve, deny, or ask for more information.</p></div>{role !== 'insurance' && <button className="button primary"><Plus size={16}/>New authorization</button>}</div><Card><div className="table-tools"><div className="search small"><Search size={16}/><input placeholder="Search this page — request ID, patient, diagnosis…" aria-label="Search request ID, patient, diagnosis" value={search} onChange={event=>setSearch(event.target.value)}/></div><div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{TIER_TABS.map(t => <button key={t.id} className={`button compact ${tier===t.id?'primary':''}`} type="button" onClick={()=>setTier(t.id)}>{t.label}</button>)}</div><button className={`button compact ${attentionOnly?'primary':''}`} type="button" onClick={()=>setAttentionOnly(value=>!value)}><SlidersHorizontal size={15}/>{attentionOnly?'Attention only':'Filters'}</button></div><div className="request-table"><div className="thead" style={{ gridTemplateColumns: columns, minWidth: tableMinWidth }}><span>Priority</span><span>Request</span><span>Patient & diagnosis</span><span>Requested service</span><span>AI triage</span><span>Status</span><span>Submitted</span><span></span></div>{pageRequests.map(r=>{ const priority = priorityByAuthorization[r.id]; return <div className="trow" style={{ gridTemplateColumns: columns, minWidth: tableMinWidth }} key={r.id} role="link" tabIndex="0" onClick={() => viewPatient(r)} onKeyDown={event => event.key === 'Enter' && viewPatient(r)}><span title={priority?.reasonCodes?.join(' · ') || ''}>{priority?.priorityTier ? <Badge type={TIER_TONE[priority.priorityTier] || 'blue'}>{priority.priorityTier}</Badge> : <Badge type="blue">—</Badge>}</span><strong>{r.id}</strong><div className="patient-cell"><div className={`mini-avatar ${r.tone}`}>{r.initials}</div><span><b>{r.patient}</b><small>{r.diagnosis}</small></span></div><span>{r.service}<small>{r.policy}</small></span><span><Badge type={r.tone}>{r.prediction}</Badge>{r.confidence && <small>{r.confidence} confidence</small>}</span><Badge type={r.tone}>{r.status}</Badge><small>{r.date}</small><button className="open" type="button" onClick={event=>{event.stopPropagation();viewPatient(r);}}><ChevronRight size={17}/></button></div>; })}{visibleRequests.length===0&&<div className="empty"><Search size={27}/><h3>No pending cases</h3><p>Cases awaiting a decision will appear here.</p></div>}</div></Card><Pager page={currentPage} totalPages={totalPages} total={visibleRequests.length} onChange={setPage}/></div></AppLayout>;
}
