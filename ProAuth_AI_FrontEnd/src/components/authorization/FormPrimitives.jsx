import React from 'react';
import { Check } from 'lucide-react';

export const authorizationSteps = ['Patient', 'Insurance', 'Clinical', 'Treatment', 'Documents', 'Review', 'Submit'];

export function Stepper({ step }) {
  return <div className="stepper">{authorizationSteps.map((label, index) => <React.Fragment key={label}><div className={`step ${index <= step ? 'done' : ''} ${index === step ? 'selected' : ''}`}><span>{index < step ? <Check size={13}/> : index + 1}</span><label>{label}</label></div>{index < authorizationSteps.length - 1 && <div className={index < step ? 'step-line filled' : 'step-line'}/>}</React.Fragment>)}</div>;
}

export function Field({ label, placeholder, wide, type = 'text', value, onChange, onBlur }) {
  return <label className={`field ${wide ? 'wide' : ''}`}><span>{label}</span><input type={type} placeholder={placeholder} value={value ?? ''} onChange={onChange} onBlur={onBlur}/></label>;
}
