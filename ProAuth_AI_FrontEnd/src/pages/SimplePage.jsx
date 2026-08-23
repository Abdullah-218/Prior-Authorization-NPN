import { BrainCircuit } from 'lucide-react';
import AppLayout from '../components/layout/AppLayout';
import { Card } from '../components/ui';

export default function SimplePage({title,subtitle,children}){return <AppLayout><div className="page simple"><h1>{title}</h1>{subtitle && <p className="lead">{subtitle}</p>}{children||<Card className="empty"><BrainCircuit size={27}/><h3>No records available</h3><p>Information for this workspace will appear when records are available.</p></Card>}</div></AppLayout>}
