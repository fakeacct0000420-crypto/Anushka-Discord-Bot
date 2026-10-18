/**
 * api/stats.js
 * GET /api/stats  — public endpoint, no auth required
 *
 * Returns aggregate bot statistics from MongoDB:
 *   - Total guilds configured
 *   - Total warnings issued
 *   - Total active strikes
 *   - Total bans logged by antinuke
 *
 * Sensitive fields (guild IDs etc.) are NEVER returned here.
 */

const { getDb } = require("../lib/db");

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Cache-Control":                "s-maxage=30, stale-while-revalidate=60",
};

module.exports = async function handler(req, res) {
  if (req.method === "OPTIONS") return res.status(204).set(CORS_HEADERS).end();
  Object.entries(CORS_HEADERS).forEach(([k, v]) => res.setHeader(k, v));

  if (req.method !== "GET") return res.status(405).json({ error: "Method not allowed." });

  try {
    const db = await getDb();

    const [guildsCount, warnsStats, antinukeCount] = await Promise.all([
      // Total configured guilds
      db.collection("servers").countDocuments(),

      // Total warnings & active strikes from the warns collection
      db.collection("warns").aggregate([
        {
          $group: {
            _id: null,
            totalStrikes:  { $sum: "$strikes" },
            totalWarnings: { $sum: { $size: { $ifNull: ["$history", []] } } },
            activeUsers:   { $sum: 1 },
          },
        },
      ]).toArray(),

      // Antinuke events (total logged lockdowns)
      db.collection("antinuke").countDocuments(),
    ]);

    const warns = warnsStats[0] || { totalStrikes: 0, totalWarnings: 0, activeUsers: 0 };

    return res.status(200).json({
      guilds:        guildsCount,
      totalWarnings: warns.totalWarnings,
      totalStrikes:  warns.totalStrikes,
      usersStrucked: warns.activeUsers,
      antinukeEvents: antinukeCount,
      timestamp:     new Date().toISOString(),
    });
  } catch (err) {
    console.error("[/api/stats]", err);
    return res.status(500).json({ error: "Database error." });
  }
};
