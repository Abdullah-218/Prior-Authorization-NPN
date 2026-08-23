/**
 * Notification Routes — real, per-user, persisted (see notificationModel.js
 * for why this replaces the frontend's previous 100%-mock Notifications.jsx).
 */
import express from 'express';
import { authenticate } from '../middleware/authMiddleware.js';
import { Notification } from '../database/index.js';

const router = express.Router();

// ─── GET /api/notifications ─────────────────────────────────────────────────
// The current user's own notifications only — never another user's.

router.get('/', authenticate, async (req, res, next) => {
  try {
    const notifications = await Notification.findAll({
      where: { userId: req.user.sub },
      order: [['createdAt', 'DESC']],
      limit: 100,
    });
    res.json({ success: true, data: notifications });
  } catch (error) {
    next(error);
  }
});

// ─── PATCH /api/notifications/:id/read ──────────────────────────────────────

router.patch('/:id/read', authenticate, async (req, res, next) => {
  try {
    const notification = await Notification.findByPk(req.params.id);
    if (!notification) return res.status(404).json({ success: false, message: 'Notification not found.' });
    if (notification.userId !== req.user.sub) {
      return res.status(403).json({ success: false, message: 'Access denied.' });
    }
    await notification.update({ read: true });
    res.json({ success: true, data: notification });
  } catch (error) {
    next(error);
  }
});

export default router;
