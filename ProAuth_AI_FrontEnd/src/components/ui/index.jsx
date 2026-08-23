export const Icon = ({ children, tone = '' }) => <span className={`icon ${tone}`}>{children}</span>;
export const Badge = ({ children, type = 'neutral' }) => <span className={`badge ${type}`}>{children}</span>;
export const Card = ({ children, className = '' }) => <section className={`card ${className}`}>{children}</section>;

// Shared loading/error placeholder for any page driven by useLiveRequests()
// — every real-data page needs the same "still fetching / fetch failed"
// state, so this is one small shared component instead of repeating the
// same markup at every call site.
export const DataState = ({ status, error, children }) => {
  if (status === 'loading') return <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--muted, #71878e)' }}>Loading live data…</div>;
  if (status === 'error') return <div className="card" style={{ padding: 32, textAlign: 'center', color: '#c0392b' }}>Couldn't load data from the server: {error}</div>;
  return children;
};

// Server-side pagination controls for usePaginatedAuthorizations() — Prev/
// Next plus a page indicator, no library, matching the plain-button style
// already used everywhere else in this app.
export const Pager = ({ page, totalPages, total, onChange }) => {
  if (totalPages <= 1) return null;
  return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14, padding: '16px 0 4px' }}>
    <button className="button compact" type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button>
    <span style={{ fontSize: 11, color: 'var(--muted, #71878e)' }}>Page {page} of {totalPages}{typeof total === 'number' ? ` · ${total} total` : ''}</span>
    <button className="button compact" type="button" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>Next</button>
  </div>;
};
