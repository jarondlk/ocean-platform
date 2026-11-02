"use strict";

// Cloud Run adds RFC Forwarded after the trusted LB's header action. Keep the
// accepted Next/auth code unchanged; remove only that redundant transport field.
const http = require("node:http");
const context = process.env;
if (context.K_SERVICE !== "ocean-v1-beta-serving"
    || context.DEPLOYMENT_ENV !== "production" || context.AUTH_MODE !== "required"
    || context.V1_PUBLIC_ORIGIN !== "https://beta.oceaninfobio.com") {
  throw new Error("Independent beta transport configuration rejected");
}

const expected = Object.freeze({
  host: "beta.oceaninfobio.com",
  "x-forwarded-host": "beta.oceaninfobio.com",
  "x-forwarded-proto": "https",
  "x-forwarded-port": "443",
});
const own = Object.prototype.hasOwnProperty;
const originalEmit = http.Server.prototype.emit;

function canonicalRequest(request) {
  if (!(request instanceof http.IncomingMessage) || !Array.isArray(request.rawHeaders)
      || request.rawHeaders.length > 512 || request.rawHeaders.length % 2 !== 0) return false;
  const headers = request.headers;
  if (Object.entries(expected).some(([name, value]) => headers[name] !== value)) return false;
  const counts = { host: 0, "x-forwarded-host": 0, "x-forwarded-proto": 0, "x-forwarded-port": 0 };
  let forwarded = 0;
  for (let index = 0; index < request.rawHeaders.length; index += 2) {
    const name = request.rawHeaders[index], value = request.rawHeaders[index + 1];
    if (typeof name !== "string" || typeof value !== "string") return false;
    const lower = name.toLowerCase();
    if (own.call(expected, lower)) {
      if (value !== expected[lower] || ++counts[lower] !== 1) return false;
    }
    if (lower === "forwarded") forwarded++;
  }
  return forwarded > 0 && Object.values(counts).every(count => count === 1);
}

http.Server.prototype.emit = function (event, ...args) {
  if (event === "request" && canonicalRequest(args[0])) {
    const request = args[0], raw = [];
    // Materialize Node's public lazy view while rawHeaders still has its original
    // parser length; otherwise a later headersDistinct getter uses stale counts.
    const distinct = request.headersDistinct;
    for (let index = 0; index < request.rawHeaders.length; index += 2) {
      if (request.rawHeaders[index].toLowerCase() !== "forwarded") {
        raw.push(request.rawHeaders[index], request.rawHeaders[index + 1]);
      }
    }
    delete request.headers.forwarded;
    delete distinct.forwarded;
    request.rawHeaders = raw;
  }
  return Reflect.apply(originalEmit, this, [event, ...args]);
};
