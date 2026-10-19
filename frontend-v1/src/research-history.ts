/** List discovery plus fresh authorization for explicitly acknowledged off-page runs. */
import { assertRunBinding, mergeRunEvents, mergeRunSnapshot, researchRunAddress, sameRunBinding, ResearchRunContractError, type ResearchRun, type ResearchRunTransport } from "./research-run-contract.ts";
import { MAX_RETAINED_RUNS_PER_CONVERSATION, type RetainedResearchRun } from "./research-state.ts";

export type RunHistoryRequest = {
  transport: ResearchRunTransport;
  address: Readonly<{ investigation_id: string; conversation_id: string }>;
  pages: number;
  cached: readonly ResearchRun[];
  retained: readonly RetainedResearchRun[];
  signal: AbortSignal;
  isCurrent: () => boolean;
};
export type RunHistoryPage = { runs: ResearchRun[]; next_cursor: string | null; unavailable_ids: string[] };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
function fail(): never { throw new ResearchRunContractError("Saved activity could not be verified"); }
function unavailable(error: unknown): boolean { return error !== null && typeof error === "object" && "status_code" in error && error.status_code === 404; }

export async function loadResearchRunHistory(request: RunHistoryRequest): Promise<RunHistoryPage> {
  const { transport, address, cached, retained, signal } = request;
  const fresh = () => { if (signal.aborted || !request.isCurrent()) throw new DOMException("History read cancelled", "AbortError"); };
  fresh();
  if (!transport.list || !Number.isSafeInteger(request.pages) || request.pages < 1 || retained.length > MAX_RETAINED_RUNS_PER_CONVERSATION || !uuid.test(address.investigation_id) || !uuid.test(address.conversation_id)) return fail();
  const selected = (run: ResearchRun, expected?: RetainedResearchRun) => {
    assertRunBinding(run.context.binding);
    if (!uuid.test(run.id) || run.context.binding.investigation_id !== address.investigation_id || run.context.binding.conversation_id !== address.conversation_id
      || (expected && (run.id !== expected.id || !sameRunBinding(run.context.binding, expected.binding)))) return fail();
  };
  const explicit = new Map<string, RetainedResearchRun>();
  for (const item of retained) {
    assertRunBinding(item.binding);
    if (!uuid.test(item.id) || item.binding.investigation_id !== address.investigation_id || item.binding.conversation_id !== address.conversation_id || explicit.has(item.id)) return fail();
    explicit.set(item.id, item);
  }
  const snapshots = new Map<string, ResearchRun>(), cursors = new Set<string>(), unavailable_ids: string[] = [];
  let cursor: string | null = null;
  for (let index = 0; index < request.pages; index++) {
    const page = await transport.list({ ...address, limit: 25, cursor }, signal); fresh();
    for (const item of page.items) { selected(item, explicit.get(item.id)); if (snapshots.has(item.id)) return fail(); snapshots.set(item.id, item); }
    cursor = page.next_cursor; if (cursor === null) break;
    if (cursors.has(cursor)) return fail(); cursors.add(cursor);
  }
  for (const item of explicit.values()) {
    if (snapshots.has(item.id)) continue;
    fresh();
    try {
      const run = await transport.status({ run_id: item.id, ...address }, signal); fresh(); selected(run, item); snapshots.set(run.id, run);
    } catch (error) {
      fresh(); if (!unavailable(error)) throw error;
      unavailable_ids.push(item.id);
    }
  }
  const runs: ResearchRun[] = [];
  for (const snapshot of snapshots.values()) {
    fresh(); let item = mergeRunSnapshot(cached.find(prior => prior.id === snapshot.id), snapshot);
    for (let index = 0; index < 20 && item.event_cursor < (item.latest_event_cursor ?? item.event_cursor); index++) {
      const page = await transport.events({ ...researchRunAddress(item), after_cursor: item.event_cursor, limit: 100 }, signal); fresh();
      item = mergeRunEvents(item, page);
    }
    runs.push(item);
  }
  fresh(); return { runs, next_cursor: cursor, unavailable_ids };
}
