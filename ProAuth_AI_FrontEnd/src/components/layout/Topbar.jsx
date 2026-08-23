import { useEffect, useState } from 'react';
import { Bell, LogOut, Menu, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useRole } from '../../context/RoleContext';
import { useAuth } from '../../hooks/useAuth';
import { useSystemStatus } from '../../hooks/useSystemStatus';
import { notificationsApi } from '../../services/notificationsApi';

const SYSTEM_STATUS_LABEL = { checking: 'Checking systems…', operational: 'All systems operational', down: 'Connection issue' };

export default function Topbar() {
  const { profile } = useRole();
  const { logout, role } = useAuth(); const navigate = useNavigate();
  const systemStatus = useSystemStatus();
  const [unreadCount, setUnreadCount] = useState(0);
  const signOut = () => { logout(); navigate('/login', { replace: true }); };

  // Only doctors ever receive a notification (see notificationRoutes.js —
  // rows are created against the request's createdBy, always the filing
  // doctor) — skip the fetch entirely for other roles rather than make a
  // real request that will only ever return an empty list.
  useEffect(() => {
    if (role !== 'doctor') { setUnreadCount(0); return undefined; }
    let cancelled = false;
    notificationsApi.list()
      .then(list => { if (!cancelled) setUnreadCount(list.filter(n => !n.read).length); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [role]);

  return <header className="topbar"><button className="mobile-menu" aria-label="Open menu"><Menu /></button>{role !== 'user' && <div className="search"><Search size={18}/><input placeholder="Search patients, requests, policies…" aria-label="Search patients, requests, policies"/></div>}<div className="top-actions"><div className={`system system-${systemStatus}`} title={systemStatus === 'down' ? "Couldn't reach the ProAuth IQ backend" : undefined}><span></span>{SYSTEM_STATUS_LABEL[systemStatus]}</div><div className="active-role"><small>{profile.name}</small><strong>{profile.label}</strong></div><button className="round-button" aria-label={unreadCount ? `Notifications (${unreadCount} unread)` : 'Notifications'} onClick={() => navigate('/doctor/notifications')} style={{ display: role === 'doctor' ? undefined : 'none' }}><Bell size={18}/>{unreadCount > 0 && <i></i>}</button><div className="top-avatar">{profile.initials}</div><button className="logout-button" onClick={signOut}><LogOut size={15}/>Log out</button></div></header>;
}
