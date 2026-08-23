import { ROLE_ALIASES } from '../constants/roles';
import { ROLE_PERMISSIONS } from '../constants/permissions';

export function normalizeRole(role) {
  return ROLE_ALIASES[role] || role;
}

export function hasPermission(user, permission) {
  return Boolean(user && ROLE_PERMISSIONS[normalizeRole(user.role)]?.includes(permission));
}
