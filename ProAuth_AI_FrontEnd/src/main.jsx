import { createRoot } from 'react-dom/client';
import { RoleProvider } from './context/RoleContext';
import { AuthProvider, useAuth } from './hooks/useAuth';
import AppRouter from './router/AppRouter';
import RoleDashboard from './components/dashboard/RoleDashboard';
import DoctorRequests from './features/doctor/pages/DoctorRequests';
import DoctorDocuments from './features/doctor/pages/DoctorDocuments';
import DoctorPatientDetail from './features/doctor/pages/DoctorPatientDetail';
import DoctorPatients from './features/doctor/pages/DoctorPatients';
import ReviewerAuthorization from './features/insurance/pages/ReviewerAuthorization';
import ReviewerRequests from './features/insurance/pages/ReviewerRequests';
import ReviewerPatientDetail from './features/insurance/pages/ReviewerPatientDetail';
import ReviewerPatients from './features/insurance/pages/ReviewerPatients';
import NursePatients from './features/nurse/pages/NursePatients';
import NursePatientDetail from './features/nurse/pages/NursePatientDetail';
import { ReadonlyAuthorizationPage, ReadonlyDiagnosisPage, ReadonlyDocumentsPage, ReadonlyPolicyCategoryPage, ReadonlyProfilePage, ReadonlyRequestPage, ReadonlyDecisionPage, ReadonlyTimelinePage } from './pages/ReadonlyViews';
import ResultPage from './pages/ResultPage';
import NewAuthorization from './pages/NewAuthorization';
import Queue from './pages/Queue';
import SimplePage from './pages/SimplePage';
import Analytics from './pages/Analytics';
import DoctorAnalytics from './pages/DoctorAnalytics';
import NurseAnalytics from './pages/NurseAnalytics';
import AuditTrail from './pages/AuditTrail';
import Policies from './pages/Policies';
import Notifications from './pages/Notifications';
import ResubmitApplication from './pages/ResubmitApplication';
import './styles.css';
import './access.css';
import './sidebar.css';
import './login.css';
import './landing.css';
import './readonly.css';
import './layout-consistency.css';
import './audit-trail.css';

function RoleScopedPage({ readonly, standard, doctor, insurance, nurse }){const { role } = useAuth();const insuranceRole = role === 'insurance' || role === 'reviewer';return role === 'user' || role === 'readonly' ? readonly : role === 'doctor' && doctor ? doctor : insuranceRole && insurance ? insurance : role === 'nurse' && nurse ? nurse : standard;}
function Root(){return <AppRouter pages={{dashboard:<RoleScopedPage readonly={<ReadonlyProfilePage/>} standard={<RoleDashboard/>}/>,profile:<ReadonlyProfilePage/>,myPolicy:<ReadonlyPolicyCategoryPage/>,diagnosis:<ReadonlyDiagnosisPage/>,myRequest:<ReadonlyRequestPage/>,decision:<ReadonlyDecisionPage/>,documents:<ReadonlyDocumentsPage/>,doctorDocuments:<DoctorDocuments/>,timeline:<ReadonlyTimelinePage/>,newAuthorization:<NewAuthorization/>,patients:<RoleScopedPage nurse={<NursePatients/>} insurance={<ReviewerPatients/>} standard={<SimplePage title="Patient profiles" subtitle="Your patients and authorization status."/>}/>,patientDetail:<RoleScopedPage nurse={<NursePatientDetail/>} insurance={<ReviewerPatientDetail/>} standard={<SimplePage title="Patient profile" subtitle="Patient authorization details."/>}/>,doctorPatients:<DoctorPatients/>,doctorPatientDetail:<DoctorPatientDetail/>,doctorRequests:<DoctorRequests/>,notifications:<Notifications/>,resubmitApplication:<ResubmitApplication/>,queue:<Queue/>,reviewerRequests:<ReviewerRequests/>,authorization:<RoleScopedPage readonly={<ReadonlyAuthorizationPage/>} insurance={<ReviewerAuthorization/>} standard={<ResultPage/>}/>,policies:<Policies/>,analytics:<RoleScopedPage doctor={<DoctorAnalytics/>} nurse={<NurseAnalytics/>} standard={<Analytics/>}/>,audit:<AuditTrail/>}}/>}
createRoot(document.getElementById('root')).render(<AuthProvider><RoleProvider><Root/></RoleProvider></AuthProvider>);
