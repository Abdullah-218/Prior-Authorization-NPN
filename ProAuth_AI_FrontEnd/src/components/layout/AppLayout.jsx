import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function AppLayout({ children }) {
  return <div className="app"><Sidebar/><main><Topbar/>{children}</main></div>;
}
