/**
 * lib/db.js
 * Serverless-safe MongoDB client using the Node.js driver.
 *
 * Reuses a single MongoClient across warm lambda invocations
 * (cached on the module-level `_client` variable).
 */

const { MongoClient } = require("mongodb");

const URI  = process.env.MONGO_URI || "mongodb://localhost:27017";
const NAME = process.env.MONGO_DB  || "bot";

let _client = null;

async function getDb() {
  if (_client && _client.topology && _client.topology.isConnected()) {
    return _client.db(NAME);
  }
  _client = new MongoClient(URI, {
    serverSelectionTimeoutMS: 5000,
    connectTimeoutMS: 5000,
  });
  await _client.connect();
  return _client.db(NAME);
}

module.exports = { getDb };
