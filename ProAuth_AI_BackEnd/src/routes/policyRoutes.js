import express from 'express';
import { v4 as uuidv4 } from 'uuid';
import { authenticate } from '../middleware/authMiddleware.js';
import { authorize } from '../middleware/roleMiddleware.js';
import { Policy, PolicyVersion, PolicyCriterion, POLICY_SOURCE } from '../database/index.js';

const router = express.Router();

// ─── GET /api/policies ──────────────────────────────────────────────────────
// Optional filters matching the structured-metadata-first retrieval design
// (payer/jurisdiction) — the same filters the Policy Evidence Agent's
// findApplicablePolicy() tool will use.

router.get('/', authenticate, async (req, res, next) => {
  try {
    const where = {};
    if (req.query.payerName)    where.payerName = req.query.payerName;
    if (req.query.jurisdiction) where.jurisdiction = req.query.jurisdiction;
    if (req.query.source)       where.source = req.query.source;
    if (req.query.status)       where.status = req.query.status;

    const policies = await Policy.findAll({ where, order: [['policyName', 'ASC']] });
    res.json({ success: true, data: policies });
  } catch (error) {
    next(error);
  }
});

// ─── GET /api/policies/:id ──────────────────────────────────────────────────
// Full detail — versions + criteria included, so a reviewer can see exactly
// what's being evaluated against without a second round trip.

router.get('/:id', authenticate, async (req, res, next) => {
  try {
    const policy = await Policy.findByPk(req.params.id, {
      include: [
        { model: PolicyVersion, as: 'versions' },
        { model: PolicyCriterion, as: 'criteria' },
      ],
      order: [[{ model: PolicyVersion, as: 'versions' }, 'createdAt', 'DESC']],
    });
    if (!policy) return res.status(404).json({ success: false, message: 'Policy not found.' });
    res.json({ success: true, data: policy });
  } catch (error) {
    next(error);
  }
});

// ─── POST /api/policies ──────────────────────────────────────────────────────

router.post('/', authenticate, authorize('ADMIN'), async (req, res, next) => {
  try {
    const {
      policyId, policyName, policyType, source, payerName,
      jurisdiction, effectiveDate, expirationDate, documentPath, status,
    } = req.body;

    if (!policyId || !policyName || !source) {
      return res.status(400).json({ success: false, message: 'policyId, policyName, and source are required.' });
    }
    if (!Object.values(POLICY_SOURCE).includes(source)) {
      return res.status(400).json({ success: false, message: `source must be one of: ${Object.values(POLICY_SOURCE).join(', ')}` });
    }

    const existing = await Policy.findOne({ where: { policyId } });
    if (existing) {
      return res.status(409).json({ success: false, message: `Policy ${policyId} already exists.` });
    }

    const policy = await Policy.create({
      id: uuidv4(),
      policyId,
      policyName,
      policyType: policyType || null,
      source,
      payerName: payerName || null,
      jurisdiction: jurisdiction || null,
      effectiveDate: effectiveDate || null,
      expirationDate: expirationDate || null,
      documentPath: documentPath || null,
      status: status || 'ACTIVE',
    });

    res.status(201).json({ success: true, data: policy });
  } catch (error) {
    next(error);
  }
});

// ─── POST /api/policies/:id/versions ─────────────────────────────────────────

router.post('/:id/versions', authenticate, authorize('ADMIN'), async (req, res, next) => {
  try {
    const policy = await Policy.findByPk(req.params.id);
    if (!policy) return res.status(404).json({ success: false, message: 'Policy not found.' });

    const { version, effectiveDate, expirationDate, documentHash } = req.body;
    if (!version) return res.status(400).json({ success: false, message: 'version is required.' });

    const policyVersion = await PolicyVersion.create({
      id: uuidv4(),
      policyId: policy.id,
      version,
      effectiveDate: effectiveDate || null,
      expirationDate: expirationDate || null,
      documentHash: documentHash || null,
    });

    res.status(201).json({ success: true, data: policyVersion });
  } catch (error) {
    next(error);
  }
});

// ─── POST /api/policies/:id/criteria ─────────────────────────────────────────

router.post('/:id/criteria', authenticate, authorize('ADMIN'), async (req, res, next) => {
  try {
    const policy = await Policy.findByPk(req.params.id);
    if (!policy) return res.status(404).json({ success: false, message: 'Policy not found.' });

    const { criterionType, criterionText, requirement, sourceSection } = req.body;
    if (!criterionText) return res.status(400).json({ success: false, message: 'criterionText is required.' });

    const criterion = await PolicyCriterion.create({
      id: uuidv4(),
      policyId: policy.id,
      criterionType: criterionType || null,
      criterionText,
      requirement: requirement || null,
      sourceSection: sourceSection || null,
    });

    res.status(201).json({ success: true, data: criterion });
  } catch (error) {
    next(error);
  }
});

export default router;
