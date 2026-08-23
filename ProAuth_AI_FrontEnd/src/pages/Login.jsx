import { useState } from 'react';
import { ArrowRight, Check, ClipboardCheck, Eye, HeartPulse, KeyRound, ShieldCheck, Stethoscope } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const roles = [
  { id: 'doctor', label: 'Doctor', detail: 'Submit and track patient authorizations.', icon: Stethoscope, email: 'doctor@hospital.com', password: 'doctor123' },
  { id: 'nurse', label: 'Nurse', detail: 'Review clinical evidence and requests.', icon: ClipboardCheck, email: 'nurse@insurance.com', password: 'nurse123' },
  { id: 'insurance', label: 'Insurance', detail: 'Manage payer decisions and policy scope.', icon: ShieldCheck, email: 'admin@insurance.com', password: 'admin123' },
  { id: 'user', label: 'User / Member', detail: 'View your own authorization information.', icon: Eye, email: 'PAT002@gmail.com', password: 'patient123' }
];

const proofPoints = [
  { icon: ShieldCheck, label: 'Trusted triage workflow', detail: 'Evidence-backed, policy-aware' },
  { icon: HeartPulse, label: 'Built for clinical teams', detail: 'Doctors, nurses, payers' }
];

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('doctor');
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const submit = async event => {
    event.preventDefault();
    setError('');
    // Role is picked for a convenient credential-autofill only — the real
    // account's actual role always comes back from the backend, not from
    // whichever button was clicked (see useAuth.js's login()).
    const authenticated = await login(email.trim(), password);
    if (!authenticated) {
      setError('Invalid email or password.');
      return;
    }
    navigate('/dashboard', { replace: true });
  };

  const pickRole = option => {
    setRole(option.id);
    if (option.email) {
      setEmail(option.email);
      setPassword(option.password);
    }
  };

  return <div className="login-page">
    <div className="login-rings" aria-hidden="true"><div className="login-rings-stage"><div className="login-ring r1"><span className="login-ring-dot"/></div><div className="login-ring r2"></div><div className="login-ring r3"><span className="login-ring-dot"/></div><div className="login-ring r4"></div></div></div>
    <div className="login-frame">
    <header className="login-header"><div className="login-brand"><span className="brand-mark"><HeartPulse size={19}/></span><span>PROAUTH <b>IQ</b></span></div></header>
    <main className="login-content">
      <section className="login-copy">
        <span className="login-tag"><i></i>Prior Authorization Intelligence</span>
        <span className="login-accent"></span>
        <h1>One workspace.<br/><em>Right perspective.</em></h1>
        <p>AI-assisted triage that keeps every clinical decision with your team, not a black box.</p>
        <div className="login-proof">{proofPoints.map(({ icon: Icon, label, detail }) => <div className="login-proof-item" key={label}><span><Icon size={15}/></span><div><strong>{label}</strong><small>{detail}</small></div></div>)}</div>
      </section>
      <section className="login-panel">
        <div className="login-panel-top"><div className="login-panel-mark"><KeyRound size={19}/></div><div><p className="eyebrow">WELCOME BACK</p><h2>Sign in</h2></div></div>
        <form onSubmit={submit}>
          <fieldset className="role-picker"><div className="role-grid">{roles.map(option => <button type="button" key={option.id} className={`role-option ${role === option.id ? 'selected' : ''}`} onClick={() => pickRole(option)}><span className="role-option-icon"><option.icon size={18}/></span><span><strong>{option.label}</strong><small>{option.detail}</small></span><i>{role === option.id && <Check size={12}/>}</i></button>)}</div></fieldset>
          <div className="login-inputs"><label className="login-field"><span>Email</span><input type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="you@proauth.ai" required /></label><label className="login-field"><span>Password</span><input type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder="demo1234" required /></label></div>
          {error && <p className="login-error" role="alert">{error}</p>}
          <button className="login-submit" type="submit">Continue to workspace <ArrowRight size={17}/></button>
        </form>
        <p className="login-notice"><ShieldCheck size={14}/>Signs in against the real ProAuth IQ backend.</p>
      </section>
    </main>
  </div></div>;
}
