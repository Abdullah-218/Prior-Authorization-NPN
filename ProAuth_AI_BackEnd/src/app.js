import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import { env } from './config/env.js';
import authRoutes from './routes/authRoutes.js';
import authorizationRoutes from './routes/authorizationRoutes.js';
import patientRoutes from './routes/patientRoutes.js';
import providerRoutes from './routes/providerRoutes.js';
import documentRoutes from './routes/documentRoutes.js';
import drugRoutes from './routes/drugRoutes.js';
import referenceRoutes from './routes/referenceRoutes.js';
import insurancePlanRoutes from './routes/insurancePlanRoutes.js';
import policyRoutes from './routes/policyRoutes.js';
import triageRoutes from './routes/triageRoutes.js';
import priorityRoutes from './routes/priorityRoutes.js';
import notificationRoutes from './routes/notificationRoutes.js';
import { errorHandler, notFoundHandler } from './middleware/errorMiddleware.js';
import { requestLogger } from './middleware/requestLogger.js';
import swaggerSpec from './config/swagger.js';
import swaggerUi from 'swagger-ui-express';

const app = express();

app.use(helmet());
app.use(
  cors({
    origin: env.frontendUrl ? env.frontendUrl.split(',').map((url) => url.trim()) : true,
    credentials: true,
  })
);
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));
app.use(morgan('dev'));
app.use(requestLogger);

const healthHandler = (_req, res) => {
  res.json({ success: true, message: 'PriorAuth AI backend is healthy.' });
};
// Bare path for the ECS/ALB target-group health check (hits the container
// directly, bypassing listener path rules). /api/health is the same check
// reachable through the shared ALB's /api path rule for external curl tests.
app.get('/health', healthHandler);
app.get('/api/health', healthHandler);

app.use('/api/auth', authRoutes);
app.use('/api/authorizations', authorizationRoutes);
app.use('/api/patients', patientRoutes);
app.use('/api/providers', providerRoutes);
app.use('/api/documents', documentRoutes);
app.use('/api/drugs', drugRoutes);
app.use('/api/reference', referenceRoutes);
app.use('/api/insurance-plans', insurancePlanRoutes);
app.use('/api/policies', policyRoutes);
app.use('/api/triage', triageRoutes);
app.use('/api/priority', priorityRoutes);
app.use('/api/notifications', notificationRoutes);
app.use('/api/docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec));

app.use(notFoundHandler);
app.use(errorHandler);

export default app;
