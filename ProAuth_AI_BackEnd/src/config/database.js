import { initializeDatabase } from '../database/index.js';

export async function bootstrapDatabase() {
  await initializeDatabase();
}
