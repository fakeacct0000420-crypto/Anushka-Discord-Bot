/**
 * api/guilds.js
 * GET /api/guilds   — JWT protected
 *
 * Returns a list of all configured guilds.
 * Sensitive values (role IDs, log channel IDs) are AES-256-GCM encrypted
 * at rest in MongoDB by the bot's Python side; this endpoint decrypts them
 * before returning to the admin dashboard.
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

/**
 * Safely attempt to decrypt a value; return the raw value if it wasn't
 * encrypted (e.g. legacy docs or plain integers).
 */
function safeDec(value) {
  if (typeof value !== "string" || !value.includes(":")) return value;
  try {
    return decrypt(value);
  } catch {
    return value;
  }
}

module.exports = async function handler(req, res) {
  if (req.method === "OPTIONS") return res.status(204).set(CORS_HEADERS).end();
  Object.entries(CORS_HEADERS).forEach(([k, v]) => res.setHeader(k, v));

  // ── auth gate ──────────────────────────────────────────────────────────────
  let passed = false;
  requireAuth(req, res, () => { passed = true; });
  if (!passed) return;

  if (req.method !== "GET") return res.status(405).json({ error: "Method not allowed." });

  try {
    const db    = await getDb();
    const docs  = await db.collection("servers").find({}).toArray();

    const guilds = docs.map(doc => ({
      guildId:       doc.guild_id,
      moderatorRole: safeDec(doc.moderator_role),
      musicRole:     safeDec(doc.music_role),
      lockdownRole:  safeDec(doc.lockdown_role),
      logChannel:    safeDec(doc.log_channel),
      createdAt:     doc.created_at ?? null,
    }));

    return res.status(200).json({ count: guilds.length, guilds });
  } catch (err) {
    console.error("[/api/guilds]", err);
    return res.status(500).json({ error: "Database error." });
  }
};
