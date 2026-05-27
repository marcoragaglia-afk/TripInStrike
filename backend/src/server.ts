import Fastify from 'fastify';
import cors from '@fastify/cors';
import { initDb } from './db';
import journeyRoutes from './routes/journey';

const PORT = parseInt(process.env.PORT || '3001');
const HOST = process.env.HOST || '0.0.0.0';

async function build() {
  const fastify = Fastify({
    logger: {
      level: process.env.LOG_LEVEL || 'info',
    },
  });

  // CORS
  await fastify.register(cors, {
    origin: [
      'http://localhost:3000',
      'http://127.0.0.1:3000',
      /^http:\/\/192\.168\.\d+\.\d+:3000$/,
    ],
    methods: ['GET'],
  });

  // Inizializza database (async con sql.js)
  try {
    await initDb();
    fastify.log.info('Database SQLite caricato');
  } catch (err) {
    fastify.log.error({ err }, 'Errore DB - eseguire: cd etl && python build_db.py');
    process.exit(1);
  }

  // Routes
  await fastify.register(journeyRoutes, { prefix: '/api' });

  // Root info
  fastify.get('/', async () => ({
    name: 'Sciopero Treni API',
    version: '1.0.0',
    endpoints: {
      stations: 'GET /api/stations?q=<query>',
      journey: 'GET /api/journey?from=<stazione>&to=<stazione>&day_type=<feriale|festivo>&table_type=<tabella_a|tabella_b>',
      trains: 'GET /api/trains?day_type=<feriale|festivo>',
      health: 'GET /api/health',
    },
  }));

  return fastify;
}

async function main() {
  const fastify = await build();
  try {
    await fastify.listen({ port: PORT, host: HOST });
    fastify.log.info(`Server avviato su http://localhost:${PORT}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
}

main();
