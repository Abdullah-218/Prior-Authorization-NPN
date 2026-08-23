/**
 * FDA Drug Label Import Script
 *
 * Usage:
 *   node src/scripts/importDrugLabels.js <path-to-json-file>
 *
 * Example:
 *   node src/scripts/importDrugLabels.js drug-label-0001-of-0014.json
 *
 * - Reads the FDA drug label JSON file in streaming chunks
 * - Filters records to only those with openfda.generic_name or indications_and_usage
 * - Upserts into drug_references table (deduplicates by set_id)
 * - Reports progress every 500 records
 */

import { readFile } from 'fs/promises';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { initializeDatabase, DrugReference, sequelize } from '../database/index.js';

const BATCH_SIZE = 200;

function extractText(field) {
  if (!field) return null;
  if (Array.isArray(field)) return field.join('\n').trim() || null;
  if (typeof field === 'string') return field.trim() || null;
  return null;
}

function extractJsonb(field) {
  if (!field) return null;
  if (Array.isArray(field)) return field;
  return [field];
}

export function normalizeRecord(raw) {
  const openfda = raw.openfda || {};
  const genericName  = extractText(openfda.generic_name);
  const brandName    = extractText(openfda.brand_name);
  const substances   = extractJsonb(openfda.substance_name);
  const rxcui        = extractJsonb(openfda.rxcui);
  const pharmClass   = extractJsonb(openfda.pharm_class_epc);
  const productType  = extractText(openfda.product_type);
  const route        = extractText(openfda.route);
  const setId        = raw.set_id || raw.id || null;

  // Skip records with no useful identification
  if (!genericName && !brandName && !substances?.length) return null;

  return {
    id:                   uuidv4(),
    externalId:           raw.id || null,
    setId,
    genericName:          genericName?.toLowerCase() || null,
    brandName:            brandName?.toLowerCase() || null,
    activeIngredients:    substances?.map(s => s.toLowerCase()) || [],
    productType,
    route,
    indications:          extractText(raw.indications_and_usage),
    contraindications:    extractText(raw.contraindications),
    warnings:             extractText(raw.warnings_and_cautions),
    adverseReactions:     extractText(raw.adverse_reactions),
    drugInteractions:     extractText(raw.drug_interactions),
    dosageInformation:    extractText(raw.dosage_and_administration),
    pregnancyInformation: extractText(raw.pregnancy),
    pediatricInformation: extractText(raw.pediatric_use),
    geriatricInformation: extractText(raw.geriatric_use),
    pharmClass,
    rxcui,
    source:               'FDA_LABEL',
    sourceVersion:        String(raw.version || ''),
    sourceUpdatedAt:      raw.effective_time || null,
  };
}

async function importFile(filePath) {
  console.log(`\n📂 Reading: ${filePath}`);
  console.log('⏳ Parsing JSON (large file — may take a moment)...\n');

  const raw = await readFile(filePath, 'utf8');
  const data = JSON.parse(raw);
  const results = data?.results;

  if (!Array.isArray(results)) {
    console.error('❌ Expected data.results to be an array. File may be invalid.');
    process.exit(1);
  }

  console.log(`📊 Total records in file: ${results.length}`);

  const normalized = results.map(normalizeRecord).filter(Boolean);
  console.log(`✅ Records with usable drug identifiers: ${normalized.length}`);
  console.log(`⏭️  Skipped (no identifiers): ${results.length - normalized.length}\n`);

  let inserted = 0;
  let skipped  = 0;

  for (let i = 0; i < normalized.length; i += BATCH_SIZE) {
    const batch = normalized.slice(i, i + BATCH_SIZE);

    for (const record of batch) {
      try {
        if (record.setId) {
          const [, created] = await DrugReference.findOrCreate({
            where: { setId: record.setId },
            defaults: record,
          });
          if (created) inserted++;
          else skipped++;
        } else {
          await DrugReference.create(record);
          inserted++;
        }
      } catch (err) {
        // Skip duplicate / constraint errors silently
        if (err.name !== 'SequelizeUniqueConstraintError') {
          console.warn(`⚠️  Record skipped: ${err.message}`);
        }
        skipped++;
      }
    }

    if ((i + BATCH_SIZE) % 1000 === 0 || i + BATCH_SIZE >= normalized.length) {
      console.log(`  Progress: ${Math.min(i + BATCH_SIZE, normalized.length)} / ${normalized.length} processed (inserted: ${inserted}, skipped: ${skipped})`);
    }
  }

  console.log(`\n🎉 Import complete!`);
  console.log(`   Inserted: ${inserted}`);
  console.log(`   Skipped (already exists or no identifiers): ${skipped}`);

  const total = await DrugReference.count();
  console.log(`   Total records now in drug_references table: ${total}\n`);
}

// ─── Main ─────────────────────────────────────────────────────────────────────
// Guarded so importDrugLabelsByName.js (the live-API alternative) can
// import normalizeRecord() above without triggering this CLI's own run.

const isMain = import.meta.url === `file://${process.argv[1]}`;

if (isMain) {
  const filePath = process.argv[2];
  if (!filePath) {
    console.error('Usage: node src/scripts/importDrugLabels.js <path-to-json-file>');
    process.exit(1);
  }

  const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(process.cwd(), filePath);

  console.log('🚀 ProAuth AI — FDA Drug Label Import\n');

  initializeDatabase()
    .then(() => importFile(absolutePath))
    .then(() => {
      console.log('✅ Done. Closing database connection.');
      return sequelize.close();
    })
    .catch((err) => {
      console.error('❌ Import failed:', err.message);
      process.exit(1);
    });
}
