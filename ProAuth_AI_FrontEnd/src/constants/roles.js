export const ROLES = {
  DOCTOR: 'doctor',
  NURSE: 'nurse',
  INSURANCE: 'insurance',
  USER: 'user'
};

export const ROLE_LABELS = {
  [ROLES.DOCTOR]: 'Doctor',
  [ROLES.NURSE]: 'Nurse',
  [ROLES.INSURANCE]: 'Insurer',
  [ROLES.USER]: 'User / Member'
};

export const ROLE_ALIASES = {
  reviewer: ROLES.INSURANCE,
  readonly: ROLES.USER
};
