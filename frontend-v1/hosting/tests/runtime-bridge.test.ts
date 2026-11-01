import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import * as runtime from "../../src/runtime.ts";
import * as catalogue from "../../src/catalogue-service.ts";
import * as investigations from "../../src/investigation-service.ts";
import * as runs from "../../src/research-run-service.ts";
import * as evidence from "../../src/research-evidence-service.ts";
import * as experiments from "../../src/experiment-service.ts";
import * as executions from "../../src/experiment-execution-service.ts";
import * as presentation from "../../src/presentation.ts";
import { sessionFetcher } from "../lib/session-fetch.ts";

function ready() {
  const permissions = ["chat:use", "data:read", "data:export", "profile:read", "feedback:write"];
  return runtime.parseRuntimeBootstrap({ version: runtime.RUNTIME_VERSION, deployment: "v1",
    identity: { id: "11111111-1111-4111-8111-111111111111", display_name: "Fixture", role: "researcher", account_type: "research", status: "active", permissions },
    permission_revision: "fixture-permissions-1",
    capabilities: Object.fromEntries(runtime.RUNTIME_DESTINATIONS.map(key => [key, {
      status: ["research", "catalogue", "settings", "about"].includes(key) ? "ready" : "unavailable",
      reason: ["research", "catalogue", "settings", "about"].includes(key) ? null : "Not integrated", required_permissions: [...runtime.REQUIRED_PERMISSIONS[key]],
    }])),
  });
}

/** Evaluate the actual component with only React scheduling/visual children isolated.
 * The client factories and request serialization remain the real implementations. */
function render(destination: "research" | "catalogue", fetcher?: runtime.Fetcher) {
  const require = createRequire(import.meta.url); let state = 0;
  const react = require("react");
  const dependencies: Record<string, unknown> = {
    react: { ...react, useMemo: (f: () => unknown) => f(), useCallback: (f: unknown) => f,
      useState: (initial: unknown) => [state++ === 0 ? { status: "ready", bootstrap: ready() } : typeof initial === "function" ? initial() : initial, () => undefined],
      useRef: (value: unknown) => ({ current: value }), useEffect() {} },
    "lucide-react": new Proxy({}, { get: () => () => null }),
    "./application-shell": { ApplicationShell: () => null, ShellDialog: () => null },
    "./shell-panels": { ShellSplitPanels: () => null },
    "./catalogue-browser": { CatalogueBrowser: () => null },
    "./research-workspace": { ResearchWorkspace: () => null, createResearchSession: () => ({}) },
    "./runtime": runtime, "./catalogue-service": catalogue, "./investigation-service": investigations,
    "./research-run-service": runs, "./research-evidence-service": evidence,
    "./experiment-service": experiments, "./experiment-execution-service": executions, "./presentation": presentation,
  };
  const source = readFileSync(new URL("../../src/runtime-app.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const module = { exports: {} as { RuntimeApp?: (props: unknown) => any } };
  new Function("require", "module", "exports", compiled)((name: string) => Object.hasOwn(dependencies, name) ? dependencies[name] : require(name), module, module.exports);
  const root = module.exports.RuntimeApp!({ initialDestination: destination, fetcher });
  return root.props.children[0].props.children.props;
}

test("actual RuntimeApp opt-in transport reaches catalogue and investigation children with session credentials", async () => {
  const calls: Array<{ path: string; credentials: RequestCredentials | undefined }> = [];
  const fetcher = sessionFetcher((async (path, init) => { calls.push({ path: String(path), credentials: init?.credentials }); return Response.json({}, { status: 503 }); }) as typeof fetch);
  const research = render("research", fetcher);
  assert(research.client); assert(research.catalogueClient);
  await assert.rejects(research.client.get({ investigation_id: "11111111-1111-4111-8111-111111111111" }));
  await assert.rejects(research.catalogueClient.snapshots({ scope: catalogue.defaultCatalogueScope() }));
  const standalone = render("catalogue", fetcher);
  assert(standalone.client);
  await assert.rejects(standalone.client.snapshots({ scope: catalogue.defaultCatalogueScope() }));
  assert.deepEqual(calls.map(row => row.path), ["/research/investigations/get", "/catalogue/snapshots", "/catalogue/snapshots"]);
  assert(calls.every(row => row.credentials === "same-origin"));
});

test("RuntimeApp callers without host opt-in retain original child/client defaults", () => {
  const research = render("research"); assert.equal(research.client, undefined); assert.equal(research.catalogueClient, undefined);
  const standalone = render("catalogue"); assert.equal(standalone.client, undefined);
});
