import { useEffect, useState } from 'react';
import { ArrowUpRight, Check, ChevronRight, CircleHelp, FileText, Search, ShieldCheck, Sparkles, UploadCloud, X } from 'lucide-react';
import AppLayout from '../components/layout/AppLayout';
import { Badge, Card } from '../components/ui';
import { Field, Stepper } from '../components/authorization/FormPrimitives';
import Processing from './Processing';
import { submitAuthorizationForTriage } from '../services/submitAuthorizationPipeline';
import { useAuth } from '../hooks/useAuth';
import { insurancePlanApi } from '../services/insurancePlanApi';
import { patientLookupApi } from '../services/patientLookupApi';

const initialFormData = {
  patientId: '', dob: '', firstName: '', lastName: '', age: '', sex: 'Female', phone: '', email: '',
  diagnosis: '', icd10: '', secondaryDiagnoses: '', duration: '', symptoms: '', clinicalJustification: '',
  serviceType: 'Imaging', procedure: '', procedureCode: '', requestedDate: '', urgency: 'Routine', careSetting: 'Outpatient',
  insuranceProvider: '', planName: '', memberId: '', planId: '', policyType: 'Medicare', coverageType: 'Active',
  // Real insurance_plans.planId — see InsuranceStep; distinct from the
  // free-text planId/policyType fields above, which are just member-
  // facing labels and don't scope real RAG retrieval.
  realPlanId: '',
};

const DOCUMENT_CATEGORIES = [
  ['clinicalNotes', 'Clinical notes'],
  ['labReports', 'Lab reports'],
  ['previousTreatmentRecords', 'Previous treatment records'],
  ['prescriptions', 'Prescriptions'],
  ['imagingReports', 'Imaging reports'],
];

function PatientLookupBanner({ status }) {
  if (status === 'loading') return <div className="connected muted"><Search size={16}/><span><strong>Looking up patient…</strong><small>Checking records for this patient ID</small></span></div>;
  if (status === 'found') return <div className="connected"><Check size={16}/><span><strong>Patient record found</strong><small>Demographics filled in below — review before submitting</small></span></div>;
  if (status === 'not-found') return <div className="connected warn"><CircleHelp size={16}/><span><strong>No matching patient record</strong><small>Enter this patient's details manually below</small></span></div>;
  return <div className="connected muted"><Search size={16}/><span><strong>Look up a patient</strong><small>Enter a patient ID, then tab out of the field to auto-fill their details</small></span></div>;
}

function PatientStep({ formData, set, onPatientIdLookup, lookupStatus }){return <><div className="form-title"><div><p className="eyebrow">STEP 1 OF 7</p><h2>Patient information</h2><p>Identify the patient or create a new patient record.</p></div><button type="button" className="button compact" onClick={()=>onPatientIdLookup(formData.patientId)}><Search size={15}/>Search existing patient</button></div><PatientLookupBanner status={lookupStatus}/><div className="fields"><Field label="Patient ID" placeholder="PAT-009821" value={formData.patientId} onChange={set('patientId')} onBlur={e=>onPatientIdLookup(e.target.value)}/><Field label="Date of birth" placeholder="MM / DD / YYYY" value={formData.dob} onChange={set('dob')}/><Field label="First name" placeholder="Maya" value={formData.firstName} onChange={set('firstName')}/><Field label="Last name" placeholder="Rodriguez" value={formData.lastName} onChange={set('lastName')}/><Field label="Age" placeholder="58" value={formData.age} onChange={set('age')}/><label className="field"><span>Sex</span><select value={formData.sex} onChange={set('sex')}><option>Female</option><option>Male</option></select></label><Field label="Phone" placeholder="(415) 555-0128" value={formData.phone} onChange={set('phone')}/><Field label="Email" placeholder="maya.rodriguez@example.com" wide value={formData.email} onChange={set('email')}/></div></>}
function ClinicalStep({ formData, set }){return <><div className="form-title"><div><p className="eyebrow">STEP 3 OF 7</p><h2>Clinical information</h2><p>Provide the clinical context for this authorization request.</p></div></div><div className="fields"><Field label="Primary diagnosis" placeholder="Knee osteoarthritis" value={formData.diagnosis} onChange={set('diagnosis')}/><Field label="ICD-10 code" placeholder="M17.11" value={formData.icd10} onChange={set('icd10')}/><Field label="Secondary diagnoses" placeholder="Search and select diagnoses" wide value={formData.secondaryDiagnoses} onChange={set('secondaryDiagnoses')}/><Field label="Duration of symptoms" placeholder="e.g. 6 months" value={formData.duration} onChange={set('duration')}/><Field label="Clinical symptoms" placeholder="Pain, limited mobility" wide value={formData.symptoms} onChange={set('symptoms')}/></div><label className="field textarea"><span>Clinical justification</span><textarea placeholder="Describe the patient’s condition, prior treatments, and clinical rationale for the requested service…" value={formData.clinicalJustification} onChange={set('clinicalJustification')}/></label><div className="ai-note"><Sparkles size={17}/><span><strong>AI-readable clinical summary</strong><small>A concise summary will be generated after submission for your review.</small></span></div></>}
function TreatmentStep({ formData, set, choose }){return <><div className="form-title"><div><p className="eyebrow">STEP 4 OF 7</p><h2>Requested service</h2><p>Tell us what is being requested and where it will be delivered.</p></div></div><div className="choice-row">{['Procedure','Imaging','Medication','Therapy','Specialist service'].map(x=><button type="button" className={`choice ${formData.serviceType===x?'chosen':''}`} key={x} onClick={()=>choose('serviceType')(x)}>{x}</button>)}</div><div className="fields"><Field label="Requested procedure" placeholder="MRI lower extremity" wide value={formData.procedure} onChange={set('procedure')}/><Field label="Procedure code / CPT / HCPCS" placeholder="73721" value={formData.procedureCode} onChange={set('procedureCode')}/><Field label="Requested date" placeholder="MM / DD / YYYY" value={formData.requestedDate} onChange={set('requestedDate')}/><label className="field"><span>Urgency</span><select value={formData.urgency} onChange={set('urgency')}><option>Routine</option><option>Urgent</option><option>Emergency</option></select></label><label className="field"><span>Care setting</span><select value={formData.careSetting} onChange={set('careSetting')}><option>Outpatient</option><option>Inpatient</option></select></label></div></>}

function InsuranceStep({ formData, set, plans, plansStatus, planNotice }){
  const setRealPlan = e => {
    const plan = plans.find(p => p.planId === e.target.value);
    set('realPlanId')(e);
    if (plan) { set('policyType')({ target: { value: plan.coverageType === 'MEDICARE' ? 'Medicare' : 'Commercial' } }); }
  };
  return <><div className="form-title"><div><p className="eyebrow">STEP 2 OF 7</p><h2>Insurance & policy</h2><p>Enter member coverage details. Policy evidence is retrieved only after submission.</p></div></div>
    {planNotice && <div className="connected warn"><CircleHelp size={16}/><span><strong>Coverage plan needs review</strong><small>{planNotice}</small></span></div>}
    <div className="fields">
      <Field label="Insurance provider" placeholder="Meridian Health Plan" value={formData.insuranceProvider} onChange={set('insuranceProvider')}/>
      <Field label="Plan name" placeholder="Medicare Advantage Plus" value={formData.planName} onChange={set('planName')}/>
      <Field label="Member ID" placeholder="MHP-8821094" value={formData.memberId} onChange={set('memberId')}/>
      <Field label="Plan ID (member-facing)" placeholder="MA-2026-CA" value={formData.planId} onChange={set('planId')}/>
      <label className="field"><span>Coverage plan (used for AI policy retrieval)</span>
        <select value={formData.realPlanId} onChange={setRealPlan} required>
          <option value="" disabled>{plansStatus === 'loading' ? 'Loading plans…' : 'Select a plan'}</option>
          {plans.map(plan => <option key={plan.planId} value={plan.planId}>{plan.planName}{plan.tier ? ` (${plan.tier})` : ''}</option>)}
        </select>
      </label>
      <label className="field"><span>Coverage type</span><select value={formData.coverageType} onChange={set('coverageType')}><option>Active</option><option>Unknown</option></select></label>
    </div>
    <div className="policy-wait"><ShieldCheck size={19}/><div><strong>Policy intelligence</strong><span>Waiting for policy retrieval after submission</span></div><Badge>Not evaluated</Badge></div>
  </>;
}

function DocumentsStep({ files, onFilesChange }){
  return <><div className="form-title"><div><p className="eyebrow">STEP 5 OF 7</p><h2>Supporting documents</h2><p>Upload documentation that supports this request.</p></div></div>
    {DOCUMENT_CATEGORIES.map(([category, label]) => <label className="doc-row" key={category} style={{ cursor: 'pointer' }}>
      <div className="doc-icon"><FileText size={19}/></div>
      <div><strong>{label}</strong><small>PDF, DOCX, PNG, or JPG · Maximum file size 20 MB</small></div>
      {files[category]?.length ? <Badge type="green"><Check size={12}/>{files[category].length} file{files[category].length === 1 ? '' : 's'}</Badge> : <Badge type="amber">Not attached</Badge>}
      <input type="file" multiple accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" style={{ display: 'none' }}
        onChange={e => onFilesChange(category, Array.from(e.target.files || []))}/>
      {files[category]?.length > 0 && <button type="button" onClick={e => { e.preventDefault(); onFilesChange(category, []); }}><X size={16}/></button>}
    </label>)}
    <div className="uploader"><UploadCloud size={28}/><strong>Click a document type above to attach files</strong><span>All fields are optional, but missing required evidence may route the request to a reviewer</span></div>
  </>;
}
function ReviewStep({ formData, user }){const patientName=`${formData.firstName} ${formData.lastName}`.trim();const rows=[['Requesting provider',[user.name,user.providerId&&`ID ${user.providerId}`,user.specialization||'No specialty on file'].filter(Boolean).join(' · '),user.specialization?'green':'amber'],['Patient',[patientName||'Not provided',formData.age&&`${formData.age} years`,formData.sex].filter(Boolean).join(' · '),patientName?'green':'amber'],['Clinical information',[formData.diagnosis||'Not provided',formData.icd10].filter(Boolean).join(' · '),formData.diagnosis?'green':'amber'],['Requested service',[formData.procedure||formData.serviceType||'Not provided',formData.procedureCode&&`CPT ${formData.procedureCode}`].filter(Boolean).join(' · '),formData.procedure?'green':'amber'],['Insurance',[formData.insuranceProvider||'Not provided',formData.realPlanId?'Coverage plan selected':'No coverage plan selected'].filter(Boolean).join(' · '),formData.realPlanId?'green':'amber']];return <><div className="form-title"><div><p className="eyebrow">STEP 6 OF 7</p><h2>Review request</h2><p>Confirm the details below before submitting for AI triage.</p></div></div><p className="hint" style={{marginBottom:14}}>Your specialty is sent with every request and factored into the AI's clinical-appropriateness check — it comes from your account, not something you enter per request.</p>{rows.map(x=><div className="review-row" key={x[0]}><span className={`review-check ${x[2]}`}><Check size={14}/></span><div><strong>{x[0]}</strong><small>{x[1]}</small></div><ChevronRight size={16}/></div>)}</>}
function AsideHelp({step}){return <aside className="aside-help"><Card><div className="help-icon"><CircleHelp size={18}/></div><h3>Request guidance</h3><p>{step===0?'Search to prefill patient details from your connected clinical system.':step===4?'Add clinical notes and prior-treatment records when they support medical necessity.':'Only the information needed for this step is shown. You can edit it before submission.'}</p><a>Learn about authorizations <ArrowUpRight size={13}/></a></Card><div className="privacy"><ShieldCheck size={16}/><span><strong>Protected information</strong><small>Your data is encrypted and access is audited.</small></span></div></aside>}

export default function NewAuthorization(){
  const { user } = useAuth();
  const [step,setStep]=useState(0);
  const [formData,setFormData]=useState(initialFormData);
  const [files, setFiles] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [plans, setPlans] = useState([]);
  const [plansStatus, setPlansStatus] = useState('loading');
  const [patientLookup, setPatientLookup] = useState({ status: 'idle', patient: null });
  const [planNotice, setPlanNotice] = useState('');
  const set = key => e => setFormData(prev => ({ ...prev, [key]: e.target.value }));
  const choose = key => value => setFormData(prev => ({ ...prev, [key]: value }));
  const onFilesChange = (category, categoryFiles) => setFiles(prev => ({ ...prev, [category]: categoryFiles }));

  useEffect(() => {
    let cancelled = false;
    insurancePlanApi.listActive()
      .then(list => { if (!cancelled) { setPlans(list); setPlansStatus('done'); } })
      .catch(() => { if (!cancelled) setPlansStatus('error'); });
    return () => { cancelled = true; };
  }, []);

  // Only demographic/administrative fields are safe to blind-autofill —
  // patient.insurancePlanId is a real FK, but most seeded patients point
  // at LEGACY payer rows that were never made active (no RAG policy
  // documents behind them; only 4 plans are). Silently selecting one of
  // those in the dropdown would send a planId the RAG layer can't resolve
  // to any payer, degrading the evaluation to "no policy found" without
  // the doctor knowing why — so the plan is only auto-selected when it's
  // confirmed to be one of the currently active, RAG-scoped plans.
  const onPatientIdLookup = async rawId => {
    const patientId = (rawId || '').trim();
    if (!patientId) return;
    setPatientLookup({ status: 'loading', patient: null });
    try {
      const patient = await patientLookupApi.getById(patientId);
      setPatientLookup({ status: 'found', patient });
      setFormData(prev => ({
        ...prev,
        firstName: patient.firstName || prev.firstName,
        lastName: patient.lastName || prev.lastName,
        dob: patient.dateOfBirth || prev.dob,
        age: patient.age != null ? String(patient.age) : prev.age,
        sex: patient.gender || prev.sex,
        phone: patient.phone || prev.phone,
        email: patient.email || prev.email,
        memberId: patient.insuranceMemberId || prev.memberId,
        planId: patient.policyNumber || prev.planId,
        coverageType: patient.coverageActive ? 'Active' : 'Unknown',
      }));
    } catch {
      setPatientLookup({ status: 'not-found', patient: null });
    }
  };

  // Reconciles the looked-up patient's insurancePlanId against the real
  // active-plan list once BOTH are ready (plans may still be loading at
  // the moment the lookup resolves) — see onPatientIdLookup's comment for
  // why a non-active plan is never silently auto-selected.
  useEffect(() => {
    const patient = patientLookup.patient;
    if (!patient || plansStatus !== 'done') return;
    const match = patient.insurancePlanId ? plans.find(p => p.planId === patient.insurancePlanId) : null;
    if (match) {
      setFormData(prev => ({ ...prev, realPlanId: match.planId, insuranceProvider: match.payerName || prev.insuranceProvider, planName: match.planName || prev.planName }));
      setPlanNotice('');
    } else if (patient.insurancePlanId) {
      setPlanNotice(`This patient's coverage on file (${patient.insurancePlanId}) isn't one of the plans currently supported for AI policy retrieval — select an applicable plan below.`);
    } else {
      setPlanNotice('No coverage plan on file for this patient — select an applicable plan below.');
    }
  }, [patientLookup, plans, plansStatus]);

  if (submitting) return <Processing task={() => submitAuthorizationForTriage({ formData, files, user })}/>;

  return <AppLayout><div className="page workflow"><div className="crumb">Authorization <ChevronRight size={14}/> <span>New request</span></div><div className="workflow-head"><div><h1>New authorization request</h1><p>Complete the request details. You’ll be able to review everything before it is submitted for AI triage.</p></div><button className="text-button">Save as draft</button></div><Stepper step={step}/><div className="form-layout"><Card className="form-card">{step===0&&<PatientStep formData={formData} set={set} onPatientIdLookup={onPatientIdLookup} lookupStatus={patientLookup.status}/>}{step===1&&<InsuranceStep formData={formData} set={set} plans={plans} plansStatus={plansStatus} planNotice={planNotice}/>}{step===2&&<ClinicalStep formData={formData} set={set}/>}{step===3&&<TreatmentStep formData={formData} set={set} choose={choose}/>}{step===4&&<DocumentsStep files={files} onFilesChange={onFilesChange}/>}{step>=5&&<ReviewStep formData={formData} user={user}/>}<div className="form-actions"><button className="button" disabled={step===0} onClick={()=>setStep(step-1)}>Back</button>{step<5?<button className="button primary" onClick={()=>setStep(step+1)}>Continue <ChevronRight size={16}/></button>:<button className="button primary" onClick={()=>setSubmitting(true)}><Sparkles size={16}/>Submit for AI triage</button>}</div></Card><AsideHelp step={step}/></div></div></AppLayout>;
}
