import express from 'express';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';
import { env } from '../config/env.js';
import { User } from '../database/index.js';

const router = express.Router();

// Self-registration is only meaningful for DOCTOR/NURSE — ADMIN must never
// be self-assignable (this endpoint used to accept ANY role string
// unchecked, letting any caller mint themselves an admin account), and
// PATIENT accounts can't be created here either: a real patient login has
// to link to an existing patients.id row (see patientId below), which a
// bare name/email/password call has no way to establish. Real patient
// accounts are provisioned by src/scripts/seedPatientAccounts.js instead.
const SELF_REGISTERABLE_ROLES = ['DOCTOR', 'NURSE'];

router.post('/register', async (req, res, next) => {
  try {
    const { name, email, password, role = 'DOCTOR' } = req.body;
    if (!name || !email || !password) {
      return res.status(400).json({ success: false, message: 'Name, email and password are required.' });
    }
    if (!SELF_REGISTERABLE_ROLES.includes(role)) {
      return res.status(400).json({ success: false, message: `role must be one of: ${SELF_REGISTERABLE_ROLES.join(', ')}` });
    }

    const existing = await User.findOne({ where: { email } });
    if (existing) {
      return res.status(409).json({ success: false, message: 'User already exists.' });
    }

    const user = await User.create({
      id: `user-${Date.now()}`,
      name,
      email,
      password: bcrypt.hashSync(password, 10),
      role,
      hospital: null,
      specialization: null,
      providerId: null,
      patientId: null,
    });
    const token = jwt.sign({ sub: user.id, role: user.role, email: user.email, patientId: user.patientId }, env.jwtSecret, { expiresIn: env.jwtExpiresIn });

    res.status(201).json({ success: true, message: 'User registered successfully.', data: { token, user: { id: user.id, name: user.name, email: user.email, role: user.role } } });
  } catch (error) {
    next(error);
  }
});

router.post('/login', async (req, res, next) => {
  try {
    const { email, password } = req.body;
    if (!email || !password) {
      return res.status(400).json({ success: false, message: 'Email and password are required.' });
    }

    const user = await User.findOne({ where: { email } });
    if (!user || !bcrypt.compareSync(password, user.password)) {
      return res.status(401).json({ success: false, message: 'Invalid credentials.' });
    }

    const token = jwt.sign({ sub: user.id, role: user.role, email: user.email, patientId: user.patientId }, env.jwtSecret, { expiresIn: env.jwtExpiresIn });

    res.json({ success: true, message: 'Login successful.', data: { token, user: { id: user.id, name: user.name, email: user.email, role: user.role, hospital: user.hospital, specialization: user.specialization, providerId: user.providerId, patientId: user.patientId } } });
  } catch (error) {
    next(error);
  }
});

router.get('/me', async (req, res) => {
  const authHeader = req.headers.authorization;
  if (!authHeader) {
    return res.status(401).json({ success: false, message: 'Authentication required.' });
  }

  const token = authHeader.replace('Bearer ', '');
  try {
    const payload = jwt.verify(token, env.jwtSecret);
    const user = await User.findByPk(payload.sub);
    if (!user) {
      return res.status(401).json({ success: false, message: 'User not found.' });
    }

    res.json({ success: true, data: { user: { id: user.id, name: user.name, email: user.email, role: user.role, hospital: user.hospital, specialization: user.specialization, providerId: user.providerId, patientId: user.patientId } } });
  } catch (error) {
    return res.status(401).json({ success: false, message: 'Invalid token.' });
  }
});

export default router;
