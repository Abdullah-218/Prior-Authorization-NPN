import { useEffect, useState } from 'react';
import { apiClient } from '../services/apiClient';

const POLL_INTERVAL_MS = 45000;

// Pings the backend's real /api/health liveness check (see
// ProAuth_AI_BackEnd/src/app.js — the same endpoint used for its own
// ECS/ALB health checks). Deliberately its own lightweight ping rather
// than reusing useLiveRequests() — that hook triggers a full GET
// /api/authorizations plus its own poll loop, and Topbar renders on every
// page, so piggybacking on it would double every page's data traffic just
// to answer "is the API up".
export function useSystemStatus() {
  const [status, setStatus] = useState('checking'); // 'checking' | 'operational' | 'down'

  useEffect(() => {
    let cancelled = false;
    const check = () => apiClient.get('/health')
      .then(() => { if (!cancelled) setStatus('operational'); })
      .catch(() => { if (!cancelled) setStatus('down'); });

    check();
    const id = setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      check();
    }, POLL_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return status;
}
