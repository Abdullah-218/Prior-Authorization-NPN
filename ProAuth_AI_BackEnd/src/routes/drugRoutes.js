import express from 'express';
import { authenticate } from '../middleware/authMiddleware.js';
import { searchDrugReferences, getDrugReferenceById } from '../services/drugReferenceService.js';

const router = express.Router();

// GET /api/drugs/search?q=metformin
router.get('/search', authenticate, async (req, res, next) => {
  try {
    const q = String(req.query.q || '').trim();
    if (q.length < 2) {
      return res.status(400).json({ success: false, message: 'Query must be at least 2 characters.' });
    }
    const results = await searchDrugReferences(q, 20);
    res.json({ success: true, data: results, count: results.length });
  } catch (error) {
    next(error);
  }
});

// GET /api/drugs/:id
router.get('/:id', authenticate, async (req, res, next) => {
  try {
    const drug = await getDrugReferenceById(req.params.id);
    if (!drug) return res.status(404).json({ success: false, message: 'Drug not found.' });
    // Return safe fields only — never expose rawData
    res.json({
      success: true,
      data: {
        id:                drug.id,
        setId:             drug.setId,
        genericName:       drug.genericName,
        brandName:         drug.brandName,
        activeIngredients: drug.activeIngredients,
        productType:       drug.productType,
        route:             drug.route,
        pharmClass:        drug.pharmClass,
        source:            drug.source,
        // Truncated snippets for display — never the full text
        indicationsSnippet:       drug.indications?.slice(0, 500) || null,
        contraindicationsSnippet: drug.contraindications?.slice(0, 400) || null,
        warningsSnippet:          drug.warnings?.slice(0, 400) || null,
        drugInteractionsSnippet:  drug.drugInteractions?.slice(0, 400) || null,
      },
    });
  } catch (error) {
    next(error);
  }
});

export default router;
