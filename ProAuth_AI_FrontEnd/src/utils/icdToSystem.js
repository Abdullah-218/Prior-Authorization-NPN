// ICD-10 code -> body system lookup. Pure data/logic, no lucide-react
// import here on purpose — `icon` is a string key (see ICON_COMPONENTS in
// DiagnosisSpotlight.jsx); the component layer owns resolving that key to
// an actual icon component, so this file has zero UI dependency. Icon keys
// are intentionally NOT shared across unrelated systems (e.g. diabetes,
// cholesterol, and vitamin D each get their own icon rather than all
// showing the same generic droplet) — an icon that's reused everywhere
// stops meaning anything.
//
// The table is keyed by ICD-10 CATEGORY (the part of the code before the
// first '.', e.g. "M17.11" -> "M17"). That's deliberate: it's what makes
// "match M17.11 and M17.12 to the same knee entry" and "a future M17.9
// still resolves sensibly" both true from one table entry, per spec.
export const ICD_TO_SYSTEM = {
  // ── Localized ──────────────────────────────────────────────────────────
  M17: { system: 'Musculoskeletal (Knee)', icon: 'bone', description: 'Affects the knee joint, involving cartilage and joint structure.', visualType: 'localized' },
  M75: { system: 'Musculoskeletal (Shoulder)', icon: 'bone', description: 'Affects the rotator cuff tendons stabilizing the shoulder joint.', visualType: 'localized' },
  S83: { system: 'Musculoskeletal (Knee)', icon: 'bone', description: 'Affects ligament or cartilage structures within the knee.', visualType: 'localized' },
  M48: { system: 'Musculoskeletal (Spine)', icon: 'bone', description: 'Affects the lumbar spinal canal, which can compress nearby nerves.', visualType: 'localized' },
  M06: { system: 'Musculoskeletal (Joints)', icon: 'bone', description: 'Affects joint tissue through chronic inflammation.', visualType: 'localized' },

  I50: { system: 'Cardiovascular System', icon: 'heart', description: "Affects the heart's structure, rhythm, or blood supply.", visualType: 'localized' },
  I48: { system: 'Cardiovascular System', icon: 'heart', description: "Affects the heart's structure, rhythm, or blood supply.", visualType: 'localized' },
  I35: { system: 'Cardiovascular System', icon: 'heart', description: "Affects the heart's structure, rhythm, or blood supply.", visualType: 'localized' },
  I25: { system: 'Cardiovascular System', icon: 'heart', description: "Affects the heart's structure, rhythm, or blood supply.", visualType: 'localized' },

  J44: { system: 'Pulmonary System', icon: 'lungs', description: 'Affects the lungs and airways, involved in breathing and gas exchange.', visualType: 'localized' },
  J43: { system: 'Pulmonary System', icon: 'lungs', description: 'Affects the lungs and airways, involved in breathing and gas exchange.', visualType: 'localized' },
  C34: { system: 'Pulmonary System', icon: 'lungs', description: 'Affects the lungs and airways, involved in breathing and gas exchange.', visualType: 'localized' },
  R91: { system: 'Pulmonary System', icon: 'lungs', description: 'Affects the lungs and airways, involved in breathing and gas exchange.', visualType: 'localized' },
  G47: { system: 'Pulmonary System', icon: 'lungs', description: 'Affects the lungs and airways, involved in breathing and gas exchange.', visualType: 'localized' },

  Z87: { system: 'Pulmonary System (Screening)', icon: 'lungs', description: 'Relates to lung cancer screening due to smoking history.', visualType: 'localized' },

  N18: { system: 'Renal System', icon: 'droplet', description: "Affects kidney function and the body's filtration system.", visualType: 'localized' },

  K50: { system: 'Digestive System', icon: 'utensils', description: 'Affects the digestive tract, causing inflammation.', visualType: 'localized' },

  B18: { system: 'Hepatic System', icon: 'flask', description: 'Affects liver function and tissue health.', visualType: 'localized' },

  E11: { system: 'Endocrine System', icon: 'syringe', description: 'Affects blood sugar regulation and related organ function.', visualType: 'localized' },

  G40: { system: 'Neurological System', icon: 'brain', description: 'Affects brain electrical activity, causing recurrent seizures.', visualType: 'localized' },
  G43: { system: 'Neurological System', icon: 'brain', description: 'Affects neurological pathways involved in headache regulation.', visualType: 'localized' },

  L40: { system: 'Integumentary System (Skin)', icon: 'layers', description: 'Affects the skin, causing chronic inflammatory plaques.', visualType: 'localized' },

  // ── Systemic ───────────────────────────────────────────────────────────
  M32: { system: 'Systemic (Autoimmune)', icon: 'shield', description: 'A systemic autoimmune condition that can affect multiple organs.', visualType: 'systemic' },
  F33: { system: 'Behavioral Health', icon: 'heart-handshake', description: 'A mental health condition affecting mood regulation.', visualType: 'systemic' },
  I10: { system: 'Cardiovascular System (Systemic)', icon: 'heart', description: 'Affects blood pressure throughout the circulatory system.', visualType: 'systemic' },
  E78: { system: 'Metabolic (Systemic)', icon: 'gauge', description: 'Affects lipid levels throughout the bloodstream.', visualType: 'systemic' },
  E55: { system: 'Metabolic (Systemic)', icon: 'sun', description: 'A nutritional deficiency affecting overall health.', visualType: 'systemic' },
  Z00: { system: 'General Wellness', icon: 'check', description: 'A routine preventive care visit, not a specific condition.', visualType: 'systemic' }
};

const DEFAULT_ENTRY = { system: 'General/Systemic', icon: 'activity', description: 'General clinical evaluation.', visualType: 'systemic' };

// Maps a single ICD-10 code to { system, icon, description, visualType },
// plus `matched`/`code` for callers that want to show their own fallback UI
// or debug info. Never throws, never returns nothing — a missing or
// unmapped code always resolves to DEFAULT_ENTRY.
export function mapIcdToSystem(icdCode) {
  const code = String(icdCode || '').trim().toUpperCase();
  if (!code) return { ...DEFAULT_ENTRY, matched: false, code: null };

  const category = code.split('.')[0];
  const entry = ICD_TO_SYSTEM[category];
  if (entry) return { ...entry, matched: true, code };

  return { ...DEFAULT_ENTRY, matched: false, code };
}
