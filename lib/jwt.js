/**
 * lib/jwt.js
 * Thin wrapper around jsonwebtoken with sane defaults.
 *
 * JWT_SECRET must be set in Vercel env vars.
 * Tokens expire in 8 hours by default.
 */

const jwt = require("jsonwebtoken");

const EXPIRY = "8h";

function _secret() {
  if (!process.env.JWT_SECRET) throw new Error("JWT_SECRET env var is not set.");
  return process.env.JWT_SECRET;
}

/**
 * Sign a payload and return a signed JWT.
 * @param {object} payload  – e.g. { sub: "admin", role: "admin" }
 * @returns {string}
 */
function sign(payload) {
  return jwt.sign(payload, _secret(), { expiresIn: EXPIRY, algorithm: "HS256" });
}

/**
 * Verify and decode a JWT.  Throws if invalid or expired.
 * @param {string} token
 * @returns {object} decoded payload
 */
function verify(token) {
  return jwt.verify(token, _secret(), { algorithms: ["HS256"] });
}

/**
 * Express/Vercel middleware that reads the Authorization header.
 * Calls next() on success, returns 401 JSON on failure.
 */
function requireAuth(req, res, next) {
  const header = req.headers["authorization"] || "";
  const token  = header.startsWith("Bearer ") ? header.slice(7) : null;

  if (!token) {
    res.status(401).json({ error: "Missing Authorization header." });
    return;
  }

  try {
    req.user = verify(token);
    next();
  } catch {
    res.status(401).json({ error: "Invalid or expired token." });
  }
}

module.exports = { sign, verify, requireAuth };
