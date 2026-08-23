import { FileText } from 'lucide-react';
import AppLayout from '../../../components/layout/AppLayout';
import { Card, DataState } from '../../../components/ui';
import { useAuth } from '../../../hooks/useAuth';
import { dashboardService } from '../../../services/dashboardService';
import { useLiveRequests } from '../../../hooks/useLiveRequests';
import { useDocumentsForAuthorizations, mapDocumentsToRows } from '../../../hooks/useDocuments';
import { DocumentRow } from '../../../components/documents/DocumentRow';

export default function DoctorDocuments() {
  const { user } = useAuth();
  const { status: listStatus, error: listError } = useLiveRequests();
  const { requests } = dashboardService.getDoctorDashboard(user.id);
  const { documentsByAuthorization, status: docsStatus } = useDocumentsForAuthorizations(requests.map(r => r.id));

  if (listStatus !== 'done' || docsStatus !== 'done') return <AppLayout><div className="page simple"><h1>Documents</h1><DataState status={listStatus !== 'done' ? listStatus : docsStatus} error={listError}/></div></AppLayout>;

  const documents = requests.flatMap(request => mapDocumentsToRows(documentsByAuthorization[request.id]).map(document => ({ document, request })));

  return <AppLayout><div className="page simple"><h1>Documents</h1><Card>{documents.length ? documents.map(({ document, request }) => <DocumentRow key={`${request.id}-${document.id}`} document={document} subtitle={`${request.id} · ${request.patient}`}/>) : <div className="empty"><FileText size={27}/><h3>No documents yet</h3><p>Supporting documents from your authorization requests will appear here.</p></div>}</Card></div></AppLayout>;
}