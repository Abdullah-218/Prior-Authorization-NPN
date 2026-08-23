import express from 'express';
import { authenticate } from '../middleware/authMiddleware.js';
import { authorize } from '../middleware/roleMiddleware.js';

const router = express.Router();

router.get('/', authenticate, authorize('ADMIN', 'DOCTOR'), (_req, res) => {
  res.json({ success: true, data: [{ id: 'DOC001', name: 'Dr. Sarah Johnson', specialty: 'Orthopedics', organization: 'City Medical Center' }] });
});

router.get('/:id', authenticate, authorize('ADMIN', 'DOCTOR'), (req, res) => {
  res.json({ success: true, data: { id: req.params.id, name: 'Dr. Sarah Johnson', specialty: 'Orthopedics', organization: 'City Medical Center' } });
});

export default router;
