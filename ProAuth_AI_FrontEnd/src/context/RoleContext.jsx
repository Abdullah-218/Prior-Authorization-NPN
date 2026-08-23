import React, { createContext, useContext } from 'react';
import { useAuth } from '../hooks/useAuth';
import { ROLE_LABELS } from '../constants/roles';
import { ROLE_PERMISSIONS } from '../constants/permissions';
import { normalizeRole } from '../utils/permissions';

const RoleContext = createContext();

export const roleProfiles = {
  doctor: { label: ROLE_LABELS.doctor, detail: 'Ordering provider' },
  nurse: { label: ROLE_LABELS.nurse, detail: 'Clinical review' },
  insurance: { label: ROLE_LABELS.insurance, detail: 'Payer operations' },
  user: { label: ROLE_LABELS.user, detail: 'Read-only access' }
};

export function RoleProvider({ children }) {
  const { user, role } = useAuth();
  const normalizedRole = normalizeRole(role);
  const baseProfile = roleProfiles[normalizedRole || 'user'];
  const profile = user ? { ...baseProfile, name: user.name, email: user.email, initials: user.name.split(' ').map(part => part[0]).join('').slice(0, 2) } : baseProfile;
  return <RoleContext.Provider value={{ role: normalizedRole, profile, can: (permission) => Boolean(normalizedRole && ROLE_PERMISSIONS[normalizedRole]?.includes(permission)) }}>{children}</RoleContext.Provider>;
}

export const useRole = () => useContext(RoleContext);
