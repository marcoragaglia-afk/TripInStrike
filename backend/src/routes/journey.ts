import type { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { getGuaranteedTrains, searchStations } from '../db';
import { findItineraries } from '../engine/router';
import type { DayType, TableType } from '../engine/router';

interface JourneyQuery {
  from: string;
  to: string;
  dep_time?: string;
  day_type: string;        // feriale | festivo
  table_type?: string;     // tabella_a | tabella_b
  max_changes?: string;
}

interface StationQuery {
  q: string;
  limit?: string;
}

export default async function journeyRoutes(fastify: FastifyInstance) {

  // GET /stations?q=Roma
  fastify.get<{ Querystring: StationQuery }>('/stations', async (req, reply) => {
    const { q = '', limit = '20' } = req.query;
    if (!q || q.trim().length < 2) {
      return reply.code(400).send({ error: 'query troppo corta (min 2 caratteri)' });
    }
    const stations = searchStations(q.trim(), Math.min(parseInt(limit), 50));
    return { stations };
  });

  // GET /journey?from=Roma+Termini&to=Milano+Centrale&day_type=feriale
  fastify.get<{ Querystring: JourneyQuery }>('/journey', async (req, reply) => {
    const { from, to, dep_time, day_type, table_type, max_changes } = req.query;

    // Validazione
    if (!from?.trim() || !to?.trim()) {
      return reply.code(400).send({ error: 'from e to sono obbligatori' });
    }
    if (!['feriale', 'festivo'].includes(day_type)) {
      return reply.code(400).send({ error: 'day_type deve essere feriale o festivo' });
    }
    if (table_type && !['tabella_a', 'tabella_b'].includes(table_type)) {
      return reply.code(400).send({ error: 'table_type deve essere tabella_a o tabella_b' });
    }
    if (dep_time && !/^\d{1,2}:\d{2}$/.test(dep_time)) {
      return reply.code(400).send({ error: 'dep_time deve essere in formato HH:MM' });
    }

    const dayType = day_type as DayType;
    const tableType = (table_type as TableType) || null;
    const maxChanges = max_changes ? Math.min(parseInt(max_changes), 2) : 1;

    // Carica treni garantiti filtrati
    const trains = getGuaranteedTrains(dayType, tableType);

    // Calcola itinerari
    const itineraries = findItineraries(trains, {
      from: from.trim(),
      to: to.trim(),
      depTime: dep_time,
      dayType,
      tableType: tableType ?? undefined,
      maxChanges,
    });

    return {
      query: { from: from.trim(), to: to.trim(), day_type: dayType, table_type: tableType, dep_time },
      count: itineraries.length,
      itineraries,
      meta: {
        trains_available: trains.length,
        note: itineraries.length === 0
          ? 'Nessun itinerario garantito trovato. Verifica i nomi delle stazioni.'
          : null,
      },
    };
  });

  // GET /trains?day_type=feriale&table_type=tabella_a
  fastify.get<{ Querystring: { day_type?: string; table_type?: string } }>('/trains', async (req, reply) => {
    const { day_type = 'feriale', table_type } = req.query;
    if (!['feriale', 'festivo'].includes(day_type)) {
      return reply.code(400).send({ error: 'day_type non valido' });
    }
    const trains = getGuaranteedTrains(
      day_type as DayType,
      (table_type as TableType) || null,
    );
    return {
      count: trains.length,
      trains: trains.slice(0, 200), // limit per performance
    };
  });

  // GET /health
  fastify.get('/health', async () => ({
    status: 'ok',
    timestamp: new Date().toISOString(),
  }));
}
