import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  return isAuthenticated ? children : <Navigate to="/login" replace state={{ from: location.pathname }}/>;
}
