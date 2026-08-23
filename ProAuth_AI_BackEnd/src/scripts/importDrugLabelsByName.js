/**
 * FDA Drug Label Import — by name, via the live openFDA query API
 *
 * Usage:
 *   node src/scripts/importDrugLabelsByName.js
 *
 * Alternative to importDrugLabels.js's bulk-file approach: instead of
 * downloading the full ~1.8GB/14-partition dataset from
 * download.open.fda.gov (blocked by a CloudFront 403 in this
 * environment, 2026-08-19), this queries api.fda.gov/drug/label.json —
 * a different host, live and reachable — once per real drug name this
 * app actually cares about (treatmentCatalog.json's 56 curated generic
 * names), rather than everything openFDA has on file. Same underlying
 * dataset, same record schema, same normalizeRecord() — just fetched
 * per-drug instead of in bulk, and targeted at the drugs this system's
 * demo data references instead of a random slice of ~262k labels.
 *
 * Idempotent (findOrCreate by set_id, same as importDrugLabels.js).
 */
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { initializeDatabase, DrugReference, sequelize } from '../database/index.js';
import { normalizeRecord } from './importDrugLabels.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OPENFDA_LABEL_URL = 'https://api.fda.gov/drug/label.json';
// Polite pacing — openFDA's unauthenticated tier allows 240 req/min; 56
// drugs at this interval finishes in well under a minute either way.
const REQUEST_DELAY_MS = 300;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchLabelByGenericName(genericName) {
  const url = `${OPENFDA_LABEL_URL}?search=${encodeURIComponent(`openfda.generic_name:"${genericName}"`)}&limit=1`;
  const response = await fetch(url);
  if (!response.ok) {
    if (response.status === 404) return null; // openFDA returns 404 for "no matches", not an error
    throw new Error(`openFDA returned ${response.status}`);
  }
  const data = await response.json();
  return data.results?.[0] || null;
}

async function importByName(names) {
  let inserted = 0, updated = 0, notFound = 0, failed = 0;

  for (const name of names) {
    try {
      const raw = await fetchLabelByGenericName(name);
      if (!raw) {
        console.log(`  ⏭️  ${name}: no openFDA label found`);
        notFound++;
        await sleep(REQUEST_DELAY_MS);
        continue;
      }

      const record = normalizeRecord(raw);
      if (!record) {
        console.log(`  ⏭️  ${name}: label found but had no usable identifiers`);
        notFound++;
        await sleep(REQUEST_DELAY_MS);
        continue;
      }

      if (record.setId) {
        const [row, created] = await DrugReference.findOrCreate({
          where: { setId: record.setId },
          defaults: record,
        });
        if (created) {
          inserted++;
          console.log(`  ✅ ${name}: inserted (${record.genericName || record.brandName})`);
        } else {
          await row.update(record);
          updated++;
          console.log(`  🔄 ${name}: updated (${record.genericName || record.brandName})`);
        }
      } else {
        await DrugReference.create({ ...record, id: uuidv4() });
        inserted++;
        console.log(`  ✅ ${name}: inserted (no set_id)`);
      }
    } catch (err) {
      console.warn(`  ⚠️  ${name}: ${err.message}`);
      failed++;
    }
    await sleep(REQUEST_DELAY_MS);
  }

  return { inserted, updated, notFound, failed };
}

async function main() {
  console.log('🚀 ProAuth AI — FDA Drug Label Import (live openFDA API, by name)\n');

  const catalog = JSON.parse(
    readFileSync(path.join(__dirname, '..', 'data', 'treatmentCatalog.json'), 'utf-8')
  );
  const names = catalog.drugs.map((d) => d.name);
  console.log(`📋 ${names.length} drug names from treatmentCatalog.json\n`);

  await initializeDatabase();
  const { inserted, updated, notFound, failed } = await importByName(names);

  console.log('\n🎉 Import complete!');
  console.log(`   Inserted: ${inserted}`);
  console.log(`   Updated:  ${updated}`);
  console.log(`   Not found on openFDA: ${notFound}`);
  console.log(`   Failed:   ${failed}`);

  const total = await DrugReference.count();
  console.log(`   Total records now in drug_references table: ${total}\n`);

  await sequelize.close();
}

main().catch((err) => {
  console.error('❌ Import failed:', err.message);
  process.exit(1);
});
