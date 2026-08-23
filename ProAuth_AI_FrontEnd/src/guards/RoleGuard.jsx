import { Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { normalizeRole } from '../utils/permissions';

export default function RoleGuard({ allowedRoles, children }) {
  const { user } = useAuth();
  return user && allowedRoles.includes(normalizeRole(user.role)) ? children : <Navigate to="/dashboard" replace/>;
}
