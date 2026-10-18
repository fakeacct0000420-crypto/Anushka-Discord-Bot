/**
 * api/auth.js
 * POST /api/auth
 *
 * Body: { "password": "<admin password>" }
 *
 * Verifies the password against ADMIN_PASSWORD_HASH (bcrypt hash stored
 * as a Vercel env var), then returns a signed JWT.
 *
 * Generate the hash once:
 *   node -e "const b=require('bcryptjs'); b.hash('yourpassword',12).then(console.log)"
 * Paste that hash into Vercel → Settings → Environment Variables as ADMIN_PASSWORD_HASH.
 */

const bcrypt    = require("bcryptjs");
const { sign }  = require("../lib/jwt");

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

module.exports = async function handler(req, res) {
  // CORS preflight
  if (req.method === "OPTIONS") {
    return res.status(204).set(CORS_HEADERS).end();
  }

  Object.entries(CORS_HEADERS).forEach(([k, v]) => res.setHeader(k, v));

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed." });
  }

  const { password } = req.body || {};
  if (!password || typeof password !== "string") {
    return res.status(400).json({ error: "password is required." });
  }

  const hash = process.env.ADMIN_PASSWORD_HASH;
  if (!hash) {
    return res.status(500).json({ error: "Server misconfiguration: ADMIN_PASSWORD_HASH not set." });
  }

  const valid = await bcrypt.compare(password, hash);
  if (!valid) {
    // Generic delay to slow brute-force attempts
    await new Promise(r => setTimeout(r, 800));
    return res.status(401).json({ error: "Invalid credentials." });
  }

  const token = sign({ sub: "admin", role: "admin" });
  return res.status(200).json({ token, expiresIn: "8h" });
};
