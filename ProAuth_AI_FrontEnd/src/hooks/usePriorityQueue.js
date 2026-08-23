import { useEffect, useState } from 'react';
import { priorityApi } from '../services/priorityApi';

// Priority ranking is an enhancement on top of the real "Needs Review"
// queue, not a prerequisite for it — a nurse still needs to see and act
// on requests even if the priority service is slow or briefly down. This
// hook therefore fails soft (status: 'error', empty map) rather than
// blocking the page: NurseReview.jsx falls back to the queue's normal
// order when priority data isn't available, instead of showing a loading
// spinner over the whole page for a secondary feature.
export function usePriorityQueue() {
  const [priorityByAuthorization, setPriorityByAuthorization] = useState({});
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    let cancelled = false;
    priorityApi.getQueue()
      .then(rows => {
        if (cancelled) return;
        const map = {};
        (rows || []).forEach(row => { map[row.authorizationId] = row; });
        setPriorityByAuthorization(map);
        setStatus('done');
      })
      .catch(() => { if (!cancelled) setStatus('error'); });
    return () => { cancelled = true; };
  }, []);

  return { priorityByAuthorization, status };
}
