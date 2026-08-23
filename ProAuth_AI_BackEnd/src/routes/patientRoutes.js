import express from 'express';
import { Op } from 'sequelize';
import { authenticate } from '../middleware/authMiddleware.js';
import { authorize } from '../middleware/roleMiddleware.js';
import { Patient } from '../database/index.js';

const router = express.Router();

router.get('/', authenticate, authorize('ADMIN', 'DOCTOR'), async (req, res, next) => {
  try {
    const patients = await Patient.findAll({ order: [['id', 'ASC']] });
    res.json({ success: true, data: patients });
  } catch (error) {
    next(error);
  }
});

router.get('/:id', authenticate, authorize('ADMIN', 'DOCTOR'), async (req, res, next) => {
  try {
    // Case-insensitive — a doctor typing "pat047" should find the same
    // record as "PAT047". findByPk() is an exact (case-sensitive) match on
    // the string primary key, which silently looked like "patient not
    // found" for any casing other than exactly what's stored.
    const patient = await Patient.findOne({ where: { id: { [Op.iLike]: req.params.id.trim() } } });
    if (!patient) {
      return res.status(404).json({ success: false, message: 'Patient not found.' });
    }
    res.json({ success: true, data: patient });
  } catch (error) {
    next(error);
  }
});

export default router;
