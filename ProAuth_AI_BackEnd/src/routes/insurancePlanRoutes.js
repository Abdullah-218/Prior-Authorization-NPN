import express from 'express';
import { v4 as uuidv4 } from 'uuid';
import { authenticate } from '../middleware/authMiddleware.js';
import { authorize } from '../middleware/roleMiddleware.js';
import { InsurancePlan } from '../database/index.js';

const router = express.Router();

// ─── GET /api/insurance-plans ──────────────────────────────────────────────────
// Any authenticated user (doctors need this to populate the plan selector
// on the new-authorization form).

router.get('/', authenticate, async (req, res, next) => {
  try {
    const where = req.query.active === undefined ? {} : { active: req.query.active === 'true' };
    const plans = await InsurancePlan.findAll({ where, order: [['planName', 'ASC']] });
    res.json({ success: true, data: plans });
  } catch (error) {
    next(error);
  }
});

// ─── GET /api/insurance-plans/:id ──────────────────────────────────────────────

router.get('/:id', authenticate, async (req, res, next) => {
  try {
    const plan = await InsurancePlan.findByPk(req.params.id);
    if (!plan) return res.status(404).json({ success: false, message: 'Insurance plan not found.' });
    res.json({ success: true, data: plan });
  } catch (error) {
    next(error);
  }
});

// ─── POST /api/insurance-plans ─────────────────────────────────────────────────
// Admin-managed reference data — plans aren't created by doctors submitting requests.

router.post('/', authenticate, authorize('ADMIN'), async (req, res, next) => {
  try {
    const { planId, planName, payerName, coverageType, jurisdiction, active } = req.body;
    if (!planId || !planName || !payerName) {
      return res.status(400).json({ success: false, message: 'planId, planName, and payerName are required.' });
    }

    const existing = await InsurancePlan.findOne({ where: { planId } });
    if (existing) {
      return res.status(409).json({ success: false, message: `Insurance plan ${planId} already exists.` });
    }

    const plan = await InsurancePlan.create({
      id: uuidv4(),
      planId,
      planName,
      payerName,
      coverageType: coverageType || null,
      jurisdiction: jurisdiction || null,
      active: active === undefined ? true : !!active,
    });

    res.status(201).json({ success: true, data: plan });
  } catch (error) {
    next(error);
  }
});

export default router;
