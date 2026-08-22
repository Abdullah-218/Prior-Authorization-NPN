def explain(row):
    reasons=[]
    if bool(row['is_emergency']): reasons.append('Emergency request')
    if bool(row['is_sla_breached']): reasons.append('SLA already breached')
    elif bool(row['is_sla_breach_imminent']): reasons.append('SLA breach is imminent')
    if row['clinical_risk_tier'] in ('HIGH','CRITICAL'): reasons.append(f"{row['clinical_risk_tier'].title()} clinical risk")
    if float(row['num_criteria_missing'])>0: reasons.append(f"{int(row['num_criteria_missing'])} criteria missing")
    if not reasons: reasons.append('Priority determined from urgency, queue age, SLA pressure, clinical risk and evidence/documentation gaps')
    return reasons
