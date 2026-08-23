import express from 'express';
import multer from 'multer';
import path from 'path';
import fs from 'fs';
import { v4 as uuidv4 } from 'uuid';
import { authenticate } from '../middleware/authMiddleware.js';
import { authorize } from '../middleware/roleMiddleware.js';
import { Document, AuditEvent, Authorization } from '../database/index.js';

const router = express.Router();
const uploadDir = path.resolve('uploads');
fs.mkdirSync(uploadDir, { recursive: true });

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, uploadDir),
  filename: (_req, file, cb) => cb(null, `${Date.now()}-${file.originalname}`),
});

// Scanned clinical documents (multi-page PDFs especially) routinely
// exceed a few MB — 5MB was tuned for nothing in particular and rejected
// real scans in practice.
const upload = multer({ storage, limits: { fileSize: 15 * 1024 * 1024 } });

// authorizationId/documentType are supplied by the frontend. Document's
// authorizationId is FK-constrained against authorizations.id, so the
// Authorization row must already exist by the time a file is uploaded
// against it — the frontend uploads only after POST /api/authorizations
// confirms creation (see NewApplication.jsx / ResubmitApplication.jsx).
router.post('/', authenticate, authorize('DOCTOR'), upload.single('file'), async (req, res, next) => {
  if (!req.file) {
    return res.status(400).json({ success: false, message: 'A file is required.' });
  }

  try {
    const document = await Document.create({
      id: uuidv4(),
      authorizationId: req.body.authorizationId || null,
      fileName: req.file.originalname,
      mimeType: req.file.mimetype,
      storageUrl: req.file.path,
      documentType: req.body.documentType || null,
    });

    // Part of the audit trail (2026-08-19+) — what was submitted, when,
    // and by whom, same AuditEvent table every other stage writes to.
    if (document.authorizationId) {
      await AuditEvent.create({
        id: uuidv4(),
        authorizationId: document.authorizationId,
        action: 'DOCUMENT_UPLOADED',
        actor: req.user.sub,
        details: { documentId: document.id, documentType: document.documentType, fileName: document.fileName },
      });
    }

    res.status(201).json({
      success: true,
      message: 'Document uploaded successfully.',
      data: {
        id: document.id,
        fileName: document.fileName,
        storageUrl: document.storageUrl,
        mimeType: document.mimeType,
        documentType: document.documentType,
      },
    });
  } catch (error) {
    next(error);
  }
});

// ─── GET /api/documents?authorizationId=X ──────────────────────────────────
// Every file on record for a request — needed on resubmission (see
// authorizationRoutes.js's resubmit flow in NewApplication/Resubmit UI):
// the Document Agent evaluates whatever attachedDocuments a single triage
// call is given, with no memory of a PRIOR call's uploads, so resubmitting
// must resend the full set (old + newly-added), not just what changed.
//
// Ownership check added 2026-08-20 — previously any authenticated user
// could read any authorization's documents just by knowing/guessing its
// id. Load-bearing now that PATIENT accounts exist and can reach this
// endpoint directly from their own Documents view; same DOCTOR/PATIENT
// ownership rule as GET /api/authorizations/:id and
// GET /api/triage/evaluations/:authorizationId.
router.get('/', authenticate, async (req, res, next) => {
  try {
    const { authorizationId } = req.query;
    if (!authorizationId) {
      return res.status(400).json({ success: false, message: 'authorizationId query param is required.' });
    }

    if (req.user.role === 'DOCTOR' || req.user.role === 'PATIENT') {
      const authorization = await Authorization.findByPk(authorizationId);
      if (!authorization) return res.status(404).json({ success: false, message: 'Authorization not found.' });
      const owns = req.user.role === 'DOCTOR' ? authorization.createdBy === req.user.sub : authorization.patientId === req.user.patientId;
      if (!owns) return res.status(403).json({ success: false, message: 'Access denied.' });
    }

    const documents = await Document.findAll({ where: { authorizationId }, order: [['createdAt', 'ASC']] });
    res.json({ success: true, data: documents });
  } catch (error) {
    next(error);
  }
});

// ─── GET /api/documents/:id/file ────────────────────────────────────────────
// Streams the actual file bytes so a reviewer can open/view a submitted
// document — previously only the filename/badge was visible anywhere in
// either frontend, no way to see the actual content. Same ownership rule
// as GET /?authorizationId=X above (DOCTOR/PATIENT must own the parent
// authorization; ADMIN/NURSE are reviewer roles and stay unrestricted).
//
// Never exposes the on-disk path to the client — the response is only
// bytes plus a Content-Type/Content-Disposition header; the real
// filesystem path (document.storageUrl) is read server-side only and
// never appears in the response.
router.get('/:id/file', authenticate, async (req, res, next) => {
  try {
    const document = await Document.findByPk(req.params.id);
    if (!document) return res.status(404).json({ success: false, message: 'Document not found.' });

    if (req.user.role === 'DOCTOR' || req.user.role === 'PATIENT') {
      const authorization = await Authorization.findByPk(document.authorizationId);
      if (!authorization) return res.status(404).json({ success: false, message: 'Authorization not found.' });
      const owns = req.user.role === 'DOCTOR' ? authorization.createdBy === req.user.sub : authorization.patientId === req.user.patientId;
      if (!owns) return res.status(403).json({ success: false, message: 'Access denied.' });
    }

    if (!document.storageUrl || !fs.existsSync(document.storageUrl)) {
      return res.status(404).json({ success: false, message: 'The stored file could not be found.' });
    }

    const safeFileName = (document.fileName || 'document').replace(/["\r\n]/g, '');
    res.setHeader('Content-Type', document.mimeType || 'application/octet-stream');
    res.setHeader('Content-Disposition', `inline; filename="${safeFileName}"`);
    fs.createReadStream(document.storageUrl).pipe(res);
  } catch (error) {
    next(error);
  }
});

export default router;
