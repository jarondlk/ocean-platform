"use strict";

// Deployment startup gate: retain request-based billing while keeping startup
// CPU allocated until the private API is ready. No application/auth changes.
const http = require("node:http");
const researchMode = process.env.OCEAN_V1_EXPECT_RESEARCH_API ?? "false";
if (researchMode !== "true" && researchMode !== "false") {
  throw new Error("Explicit beta API startup mode required");
}
const expectedExecution = researchMode === "true";
const deadline = Date.now() + 150000;
function ready() {
  return new Promise(resolve => {
    const request = http.get("http://127.0.0.1:8000/health/live", response => {
      let data = "";
      response.setEncoding("utf8");
      response.on("data", chunk => {
        data += chunk;
        if (data.length > 2048) response.destroy();
      });
      response.on("error", () => resolve(false));
      response.on("end", () => {
        try {
          const value = JSON.parse(data);
          resolve(response.statusCode === 200 && value.status === "live"
            && value.execution_enabled === expectedExecution);
        } catch { resolve(false); }
      });
    });
    request.setTimeout(1500, () => request.destroy());
    request.on("error", () => resolve(false));
  });
}
(async () => {
  while (Date.now() < deadline) {
    if (await ready()) {
      console.info("Independent beta API ready; starting frontend");
      require("/opt/ocean/hosting/server.js");
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  console.error("Independent beta API startup deadline exceeded");
  process.exit(1);
})();
