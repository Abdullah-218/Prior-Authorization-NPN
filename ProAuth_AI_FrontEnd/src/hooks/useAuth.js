import React, { createContext, useContext, useEffect, useState } from 'react';
import { apiClient, setToken } from '../services/apiClient';

const AuthContext = createContext(null);
const USER_KEY = 'user';

// Backend roles (ProAuth_AI_BackEnd's User.role, uppercase) -> this
// frontend's canonical role strings (src/constants/roles.js's ROLES —
// AppRouter's RoleRoute checks this raw, un-normalized value against
// allowedRoutes, so it must be the canonical form, not an alias).
// PATIENT -> 'user' is the read-only member panel — backed by real
// patient-scoped endpoints as of 2026-08-20 (see
// seedPatientAccounts.js / authorizationRoutes.js's patientId scoping).
const BACKEND_ROLE_TO_FRONTEND_ROLE = {
  DOCTOR: 'doctor',
  NURSE: 'nurse',
  ADMIN: 'insurance',
  PATIENT: 'user',
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY)) || null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    else localStorage.removeItem(USER_KEY);
  }, [user]);

  // Real POST /api/auth/login (ProAuth_AI_BackEnd/src/routes/authRoutes.js)
  // — no role parameter sent; the backend is the source of truth for who
  // this account actually is. Returns false (not the auth error string)
  // on any failure, matching this hook's existing boolean contract so
  // Login.jsx's error handling doesn't need to change shape.
  const login = async (email, password) => {
    try {
      const data = await apiClient.post('/auth/login', { email, password });
      const role = BACKEND_ROLE_TO_FRONTEND_ROLE[data.user.role];
      if (!role) return false;
      setToken(data.token);
      setUser({ ...data.user, role });
      return true;
    } catch {
      return false;
    }
  };

  const logout = () => {
    setUser(null);
    setToken(null);
  };

  return React.createElement(
    AuthContext.Provider,
    { value: { user, role: user?.role || null, isAuthenticated: Boolean(user), login, logout } },
    children
  );
}

export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error('useAuth must be used inside AuthProvider');
  return auth;
}
