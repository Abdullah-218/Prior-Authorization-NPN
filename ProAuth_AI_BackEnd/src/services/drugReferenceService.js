/**
 * Drug Reference Service
 *
 * All drug lookups go through here — no direct DB queries in evaluators.
 * Search priority:
 *   1. Exact generic name match
 *   2. Exact brand name match
 *   3. Active ingredient contains
 *   4. Partial generic name ILIKE match (fallback)
 *
 * Returns the best-matching DrugReference record or null.
 */
import { Op } from 'sequelize';
import { DrugReference } from '../database/index.js';
import { normalizeDrugName } from '../utils/normalizationUtils.js';

/**
 * Find a drug reference by treatment name.
 * Search priority:
 *   1. Exact generic name match
 *   2. Exact brand name match
 *   3. Active ingredient JSONB contains any word
 *   4. Partial generic/brand ILIKE (first significant word)
 *   5. Partial generic/brand ILIKE (any significant word — broader fallback)
 */
export async function findDrugReference(treatmentName) {
  if (!treatmentName) return null;

  const normalized = normalizeDrugName(treatmentName);
  if (!normalized) return null;

  // 1. Exact generic name match
  let record = await DrugReference.findOne({ where: { genericName: normalized } });
  if (record) return record;

  // 2. Exact brand name match
  record = await DrugReference.findOne({ where: { brandName: normalized } });
  if (record) return record;

  // 3. Active ingredient contains
  const words = normalized.split(/\s+/).filter(w => w.length > 3);
  for (const word of words) {
    try {
      record = await DrugReference.findOne({
        where: { activeIngredients: { [Op.contains]: [word] } },
      });
      if (record) return record;
    } catch (_) { /* JSONB contains may fail on non-PG — ignore */ }
  }

  // 4. Partial ILIKE on first meaningful word (≥4 chars)
  const firstWord = words[0];
  if (firstWord && firstWord.length >= 4) {
    record = await DrugReference.findOne({
      where: {
        [Op.or]: [
          { genericName: { [Op.iLike]: `%${firstWord}%` } },
          { brandName:   { [Op.iLike]: `%${firstWord}%` } },
        ],
      },
      order: [['genericName', 'ASC']],
    });
    if (record) return record;
  }

  // 5. Broader fallback — try every significant word
  for (const word of words.slice(1)) {
    if (word.length < 4) continue;
    record = await DrugReference.findOne({
      where: {
        [Op.or]: [
          { genericName: { [Op.iLike]: `%${word}%` } },
          { brandName:   { [Op.iLike]: `%${word}%` } },
        ],
      },
      order: [['genericName', 'ASC']],
    });
    if (record) return record;
  }

  return null;
}

/**
 * Search drug references for the drug search endpoint.
 * Returns safe, non-PHI fields only.
 */
export async function searchDrugReferences(query, limit = 20) {
  if (!query || query.trim().length < 2) return [];

  const q = normalizeDrugName(query);

  const results = await DrugReference.findAll({
    where: {
      [Op.or]: [
        { genericName: { [Op.iLike]: `%${q}%` } },
        { brandName:   { [Op.iLike]: `%${q}%` } },
      ],
    },
    attributes: ['id', 'setId', 'genericName', 'brandName', 'activeIngredients', 'productType', 'route', 'pharmClass'],
    limit,
    order: [['genericName', 'ASC']],
  });

  return results;
}

/**
 * Get a single drug reference by ID (for the drug detail endpoint).
 * Excludes rawData.
 */
export async function getDrugReferenceById(id) {
  return DrugReference.findByPk(id, {
    attributes: {
      exclude: [], // rawData is never stored, so nothing to exclude
    },
  });
}
