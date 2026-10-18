/**
 * lib/crypto.js
 * AES-256-GCM symmetric encryption / decryption.
 *
 * ENCRYPTION_KEY must be a 64-char hex string (32 bytes).
 * Generate one with:  node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
 *
 * Encrypted payload format (all base64-encoded, colon-separated):
 *   <iv_b64>:<authTag_b64>:<ciphertext_b64>
 */

const crypto = require("crypto");

const ALGORITHM   = "aes-256-gcm";
const IV_LENGTH   = 12;   // 96-bit IV — recommended for GCM
const TAG_LENGTH  = 16;   // 128-bit auth tag

function _getKey() {
  const hex = process.env.ENCRYPTION_KEY;
  if (!hex || hex.length !== 64) {
    throw new Error("ENCRYPTION_KEY must be a 64-character hex string (32 bytes).");
  }
  return Buffer.from(hex, "hex");
}

/**
 * Encrypt a plain-text string.
 * @param {string} plaintext
 * @returns {string}  "<iv>:<tag>:<ciphertext>" all base64
 */
function encrypt(plaintext) {
  const key    = _getKey();
  const iv     = crypto.randomBytes(IV_LENGTH);
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv, { authTagLength: TAG_LENGTH });

  const encrypted = Buffer.concat([
    cipher.update(plaintext, "utf8"),
    cipher.final(),
  ]);

  const tag = cipher.getAuthTag();
  return [iv.toString("base64"), tag.toString("base64"), encrypted.toString("base64")].join(":");
}

/**
 * Decrypt a payload produced by encrypt().
 * @param {string} payload
 * @returns {string} original plaintext
 */
function decrypt(payload) {
  const key = _getKey();
  const [ivB64, tagB64, ciphertextB64] = payload.split(":");
  if (!ivB64 || !tagB64 || !ciphertextB64) throw new Error("Invalid encrypted payload format.");

  const iv         = Buffer.from(ivB64,         "base64");
  const tag        = Buffer.from(tagB64,         "base64");
  const ciphertext = Buffer.from(ciphertextB64,  "base64");

  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv, { authTagLength: TAG_LENGTH });
  decipher.setAuthTag(tag);

  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
}

/**
 * Utility: hash sensitive strings (tokens, etc.) for safe storage.
 * Uses SHA-256 + HMAC with the encryption key as the secret.
 */
function hmacHash(value) {
  return crypto.createHmac("sha256", _getKey()).update(value).digest("hex");
}

module.exports = { encrypt, decrypt, hmacHash };
