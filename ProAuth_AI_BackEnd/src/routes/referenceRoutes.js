import express from 'express';
import { authenticate } from '../middleware/authMiddleware.js';
import { CONDITION_VOCABULARY } from '../data/conditionVocabulary.js';

const router = express.Router();

// GET /api/reference/conditions — the diagnosis vocabulary the ML model was
// trained on, used to auto-fill ICD-10 codes from a typed diagnosis.
router.get('/conditions', authenticate, (_req, res) => {
  res.json({ success: true, data: CONDITION_VOCABULARY });
});

export default router;
