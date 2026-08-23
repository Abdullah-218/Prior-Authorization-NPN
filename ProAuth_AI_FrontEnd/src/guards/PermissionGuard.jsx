import { Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { hasPermission } from '../utils/permissions';

export default function PermissionGuard({ permission, children }) {
  const { user } = useAuth();
  return hasPermission(user, permission) ? children : <Navigate to="/dashboard" replace/>;
}
