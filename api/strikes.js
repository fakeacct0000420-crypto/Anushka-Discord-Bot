/**
 * api/strikes.js
 * GET /api/strikes?guildId=<id>   — JWT protected
 * GET /api/strikes?userId=<id>&guildId=<id>  — specific user
 *
 * Returns strike records for a guild, decrypting any encrypted fields.
 * Reason strings stored by the bot are encrypted with AES-256-GCM before
 * being written to MongoDB; this endpoint decrypts them on read.
 *
 * Authorization: Bearer <token>
 */

const { requireAuth }   = require("../lib/jwt");
const { decrypt }       = require("../lib/crypto");
const { getDb }         = require("../lib/db");

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

function safeDec(value) {
  if (typeof value !== "string" || !value.includes(":")) return value;
  try { return decrypt(value); } catch { return value; }
}

module.exports = async function handler(req, res) {
  if (req.method === "OPTIONS") return res.status(204).set(CORS_HEADERS).end();
  Object.entries(CORS_HEADERS).forEach(([k, v]) => res.setHeader(k, v));

  // ── auth gate ──────────────────────────────────────────────────────────────
  let passed = false;
  requireAuth(req, res, () => { passed = true; });
  if (!passed) return;

  if (req.method !== "GET") return res.status(405).json({ error: "Method not allowed." });

  const { guildId, userId } = req.query;
  if (!guildId) return res.status(400).json({ error: "guildId query param is required." });

  try {
    const db     = await getDb();
    const filter = { guild_id: parseInt(guildId, 10) };
    if (userId) filter.user_id = parseInt(userId, 10);

    const docs = await db.collection("warns").find(filter).toArray();

    const records = docs.map(doc => ({
      userId:   doc.user_id,
      guildId:  doc.guild_id,
      strikes:  doc.strikes,
      history:  (doc.history || []).map(h => ({
        reason:   safeDec(h.reason),      // decrypts if encrypted
        issuedAt: h.issued_at,
      })),
      createdAt: doc.created_at,
    }));

    return res.status(200).json({ count: records.length, records });
  } catch (err) {
    console.error("[/api/strikes]", err);
    return res.status(500).json({ error: "Database error." });
  }
};
