import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Bell, Check, Zap } from 'lucide-react';
import AppLayout from '../components/layout/AppLayout';
import { Badge, Card, DataState, Pager } from '../components/ui';
import { notificationsApi } from '../services/notificationsApi';

const PAGE_SIZE = 15;

// Fixed vocabulary set by the backend (notificationModel.js) at the exact
// events that create a real row: an automated approval, a nurse/admin
// review decision, or a request being bounced back for more information.
const TYPE_META = {
  AUTO_APPROVED: { label: 'Automatically approved', icon: Zap, tone: 'green' },
  MANUALLY_APPROVED: { label: 'Approved by reviewer', icon: Check, tone: 'green' },
  MANUALLY_DENIED: { label: 'Denied by reviewer', icon: AlertTriangle, tone: 'red' },
  ADDITIONAL_INFORMATION_REQUIRED: { label: 'Additional information required', icon: AlertTriangle, tone: 'amber' },
};

function timeAgo(dateStr) {
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

export default function Notifications() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => {
    let cancelled = false;
    notificationsApi.list()
      .then(list => { if (!cancelled) { setNotifications(list); setStatus('done'); } })
      .catch(err => { if (!cancelled) { setError(err.message || 'Failed to load notifications.'); setStatus('error'); } });
    return () => { cancelled = true; };
  }, []);

  const openNotification = notification => {
    if (!notification.read) {
      setNotifications(prev => prev.map(n => n.id === notification.id ? { ...n, read: true } : n));
      notificationsApi.markRead(notification.id).catch(() => {});
    }
    if (notification.authorizationId) navigate(`/authorizations/${notification.authorizationId}`);
  };

  const unreadCount = notifications.filter(n => !n.read).length;
  // Client-side pagination — the whole list is already fetched in one
  // call (no server-side pagination on this endpoint), so this is a
  // slice, not a new fetch.
  const totalPages = Math.max(1, Math.ceil(notifications.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visibleNotifications = notifications.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return <AppLayout><div className="page simple notifications-page">
    <div className="page-heading"><div><h1>Notifications</h1><p>Recent workflow events and actions that need your attention.</p></div>{unreadCount > 0 && <Badge type="blue">{unreadCount} unread</Badge>}</div>
    {status !== 'done' ? <DataState status={status} error={error}/> : (
      <>
      <Card className="notification-list">
        {notifications.length === 0 && <div className="empty"><Bell size={27}/><h3>Nothing yet</h3><p>You'll see updates here as your requests move through review.</p></div>}
        {visibleNotifications.map(n => {
          const meta = TYPE_META[n.type] || { label: n.type, icon: Bell, tone: 'blue' };
          const Icon = meta.icon;
          return <button className={`notification-row ${n.read ? 'is-read' : ''}`} type="button" key={n.id} onClick={() => openNotification(n)}>
            <div className={`notification-icon ${meta.tone}`}><Icon size={16}/></div>
            <div className="notification-body">
              <div className="notification-title-row"><strong>{meta.label}</strong>{!n.read && <span className="notification-dot"/>}</div>
              <p>{n.message}</p>
            </div>
            <div className="notification-meta">
              {!n.read && <Badge type={meta.tone}>New</Badge>}
              <small>{timeAgo(n.createdAt)}</small>
            </div>
          </button>;
        })}
      </Card>
      <Pager page={currentPage} totalPages={totalPages} total={notifications.length} onChange={setPage}/>
      </>
    )}
  </div></AppLayout>;
}
