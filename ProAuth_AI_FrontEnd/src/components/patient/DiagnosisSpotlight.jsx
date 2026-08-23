import { Activity, Bone, Brain, Check, Droplet, FileText, FlaskConical, Gauge, Heart, HeartHandshake, Layers, Shield, Sun, Syringe, Utensils } from 'lucide-react';
import { mapIcdToSystem } from '../../utils/icdToSystem';
import LungsIcon from './LungsIcon';

// icdToSystem.js returns `icon` as a plain string key (kept UI-agnostic on
// purpose) — this is the one place that resolves it to an actual icon
// component. Lucide has no literal "lungs" glyph, so that key resolves to
// the hand-drawn LungsIcon (see LungsIcon.jsx) instead of borrowing an
// unrelated icon. Each system gets its OWN icon here — none of these keys
// are reused across unrelated systems (diabetes/cholesterol/vitamin-D used
// to all share one generic droplet; they don't anymore).
const ICON_COMPONENTS = {
  bone: Bone, heart: Heart, lungs: LungsIcon, droplet: Droplet, activity: Activity,
  brain: Brain, shield: Shield, check: Check, syringe: Syringe, gauge: Gauge,
  sun: Sun, utensils: Utensils, flask: FlaskConical, layers: Layers, 'heart-handshake': HeartHandshake
};

const URGENCY_METER = {
  routine: { percent: 33, color: 'var(--blue)' },
  urgent: { percent: 66, color: 'var(--amber)' },
  emergency: { percent: 100, color: 'var(--red)' }
};

// Icon-based read-only diagnosis summary — no WebGL, no 3D, no camera
// controls. Fully data-driven off icdCode (see icdToSystem.js);
// mapIcdToSystem() always returns a valid entry (falls back to
// General/Systemic), so this never renders blank for an unmapped code. The
// urgency meter, secondary-diagnosis badge, and clinical-history block are
// each independently optional — any missing field just omits that piece
// rather than showing a placeholder.
export default function DiagnosisSpotlight({ diagnosis, icdCode, secondaryDiagnoses, clinicalHistory, urgency, status }) {
  const result = mapIcdToSystem(icdCode);
  const Icon = ICON_COMPONENTS[result.icon] || Activity;
  const isSystemic = result.visualType === 'systemic';
  const statusText = String(status || '').toLowerCase();
  const isUrgent = statusText.includes('needs review') || statusText.includes('critical') || statusText.includes('urgent');

  const urgencyMeter = URGENCY_METER[String(urgency || '').toLowerCase()];
  const hasSecondary = secondaryDiagnoses && !/^none/i.test(secondaryDiagnoses.trim());
  const hasHistory = clinicalHistory && !/^no clinical/i.test(clinicalHistory.trim());

  return <div className="card">
    <div className="section-title">
      <div><p className="eyebrow">DIAGNOSIS SPOTLIGHT</p><h3>{diagnosis || 'Diagnosis context'}</h3></div>
      <span className="badge blue">View only</span>
    </div>
    <div className="diagnosis-spotlight">
      <div className={`diagnosis-spotlight-badge${isUrgent ? ' urgent' : ''}`}>
        <Icon size={38} strokeWidth={1.75}/>
      </div>
      {isSystemic && <p className="diagnosis-spotlight-systemic-note">Systemic condition — not localized to one region</p>}
      <h3>{result.system}</h3>
      {icdCode && <span className="diagnosis-spotlight-code">{icdCode}</span>}
      <p className="body-copy">{result.description}</p>
    </div>
    {urgencyMeter && <div className="score diagnosis-spotlight-urgency"><div><span>Urgency</span><b>{urgency}</b></div><i><em style={{ width: urgencyMeter.percent + '%', background: urgencyMeter.color }}/></i></div>}
    {hasSecondary && <div className="diagnosis-spotlight-secondary"><span>Secondary diagnosis</span><strong>{secondaryDiagnoses}</strong></div>}
    {hasHistory && <div className="evidence-quote diagnosis-spotlight-history"><span><FileText size={15}/></span><div><strong>Clinical history</strong><p>{clinicalHistory}</p></div></div>}
  </div>;
}
