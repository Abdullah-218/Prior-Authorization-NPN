/**
 * Notification — real, persisted, in-app notifications for the doctor
 * <-> nurse reviewer loop. Previously ProAuth_AI_FrontEnd's
 * Notifications.jsx was 100% hardcoded mock data with no backend behind
 * it at all — nothing ever actually told a doctor their request was
 * approved, or that a nurse needs more information from them. This
 * closes that gap: a real row is created at each of those events (see
 * authorizationRoutes.js's PATCH /:id/review and triageRoutes.js's
 * automated-approve write-back).
 */
import { DataTypes } from 'sequelize';

export function defineNotification(sequelize) {
  return sequelize.define(
    'Notification',
    {
      id:              { type: DataTypes.STRING, primaryKey: true, allowNull: false },
      userId:          { type: DataTypes.STRING, allowNull: false }, // recipient — User.id
      authorizationId: { type: DataTypes.STRING, allowNull: true },
      // e.g. 'AUTO_APPROVED' | 'MANUALLY_APPROVED' | 'MANUALLY_DENIED' |
      // 'ADDITIONAL_INFORMATION_REQUIRED' — a fixed vocabulary the
      // frontend can icon/color without parsing message text.
      type:            { type: DataTypes.STRING, allowNull: false },
      message:         { type: DataTypes.TEXT, allowNull: false },
      read:            { type: DataTypes.BOOLEAN, defaultValue: false },
    },
    {
      tableName: 'notifications',
      timestamps: true,
      updatedAt: false,
      indexes: [
        { fields: ['userId'], name: 'idx_notifications_user_id' },
      ],
    }
  );
}
