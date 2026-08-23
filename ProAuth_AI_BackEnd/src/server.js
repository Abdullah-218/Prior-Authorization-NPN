import app from './app.js';
import { env } from './config/env.js';
import { bootstrapDatabase } from './config/database.js';
import { startTriageService, stopTriageService } from './config/triageServiceManager.js';

const port = env.port;

async function startServer() {
  await startTriageService();

  let retries = 0;
  while (retries < 10) {
    try {
      await bootstrapDatabase();
      app.listen(port, () => {
        console.log(`PriorAuth API listening on port ${port}`);
      });
      return;
    } catch (error) {
      retries += 1;
      console.error(`Database startup attempt ${retries} failed:`, error.message);
      if (retries >= 10) {
        console.error('Failed to start server after multiple attempts.');
        process.exit(1);
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }
}

function shutdown() {
  stopTriageService();
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

startServer();
