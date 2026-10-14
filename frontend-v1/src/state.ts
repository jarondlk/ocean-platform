import { fixtureAdapter } from "./adapter.ts";
import { text, type ContextRevision, type Conversation, type Investigation, type Location, type PreviewState, type Proposal, type Run, type Scenario } from "./model.ts";

let sequence = 0;
export const createId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${(++sequence).toString(36)}`;
export const STORAGE_KEY = "ocean-p00-synthetic-v1";
export function conversationTitle(question: string) {
  if (/temperature|sst|水温|温度/i.test(question)) return text("Temperature changes", "水温の変化");
  if (/method|protocol|手法|方法/i.test(question)) return text("Sampling methods", "サンプリング手法");
  if (/available|data|データ/i.test(question)) return text("Available data", "利用できるデータ");
  const title = question.length > 44 ? `${question.slice(0, 41).trim()}…` : question;
  return text(title, title);
}
export function newConversation(title = text("Conversation 1", "会話1")): Conversation {
  return { id: createId("conversation"), title, draft: "", messages: [], runs: [] };
}
export function newInvestigation(title: string, now = Date.now()): Investigation {
  return { id: createId("investigation"), title, snapshotId: "sample-02", context: { revision: 1, attachments: [], constraints: [] }, conversations: [newConversation()], proposals: [], updatedAt: now };
}
export function createPreviewState(): PreviewState {
  const coastal = newInvestigation("Miyagi coastal context", Date.UTC(2026, 9, 13, 0));
  coastal.id = "miyagi";
  coastal.context.attachments = ["sst-2022", "ctd-2022"];
  const conversation = coastal.conversations[0];
  conversation.id = "available-data";
  conversation.title = text("Available data", "利用できるデータ");
  const run: Run = { id: "seed-inventory", question: "What data is available for Miyagi?", snapshotId: "sample-02", context: structuredClone(coastal.context), scenario: "normal", status: "completed", startedAt: coastal.updatedAt, elapsedMs: 4200 };
  conversation.runs = [run];
  const answer = fixtureAdapter.answer(run);
  conversation.messages = [
    { id: "seed-question", role: "user", body: text(run.question, "宮城について、どんなデータが利用できますか？"), runId: run.id },
    { id: "seed-answer", role: "assistant", body: answer.body, runId: run.id, answer },
  ];
  const temperature = newConversation(text("Temperature changes", "水温の変化"));
  temperature.id = "temperature";
  coastal.conversations.push(temperature);
  const field = newInvestigation("Summer field observations", Date.UTC(2026, 9, 12, 0));
  field.id = "summer"; field.snapshotId = "sample-01"; field.context.attachments = ["ctd-2021", "sst-2022"];
  field.conversations[0].id = "field-notes";
  return { version: 1, investigations: [coastal, field], feedback: [], feedbackDraft: { category: "idea", message: "", reason: "" }, preferences: { locale: "en", theme: "light", workspaceWidth: 390, workspaceOpen: true, role: "researcher", accountType: "research" } };
}
export function changeContext(current: ContextRevision, id: string, action: "attach" | "pin" | "remove" | "unpin"): ContextRevision {
  const next = structuredClone(current);
  if (action === "attach" && !next.attachments.includes(id)) next.attachments.push(id);
  if (action === "pin" && !next.constraints.includes(id)) next.constraints.push(id);
  if (action === "remove") next.attachments = next.attachments.filter((item) => item !== id);
  if (action === "unpin") next.constraints = next.constraints.filter((item) => item !== id);
  next.revision = current.revision + 1;
  return next;
}
export function beginRun(investigation: Investigation, conversation: Conversation, question: string, scenario: Scenario, now = Date.now(), previous?: Run): Conversation {
  const run: Run = {
    id: createId("run"), question, snapshotId: previous?.snapshotId ?? investigation.snapshotId,
    context: structuredClone(previous?.context ?? investigation.context), scenario, status: "queued", startedAt: now, elapsedMs: 0, continuationOf: previous?.id,
  };
  return { ...conversation, draft: previous ? conversation.draft : "", title: conversation.messages.length ? conversation.title : conversationTitle(question),
    messages: [...conversation.messages, { id: createId("message"), role: "user", body: text(question, question), runId: run.id }], runs: [...conversation.runs, run] };
}
export const activeRun = (conversation: Conversation) => conversation.runs.findLast((run) => ["queued", "running", "cancelling"].includes(run.status));
export function advanceRun(run: Run, now: number): Run {
  if (!["queued", "running", "cancelling"].includes(run.status)) return run;
  const elapsedMs = Math.max(0, now - run.startedAt);
  if (run.status === "cancelling") return now - (run.cancellationAt ?? now) > 450 ? { ...run, status: "cancelled", elapsedMs } : { ...run, elapsedMs };
  if (elapsedMs < 600) return { ...run, status: "queued", elapsedMs };
  if (elapsedMs > 1800 && ["error", "unavailable", "revoked"].includes(run.scenario)) return { ...run, status: "error", elapsedMs };
  if (elapsedMs > 1800 && run.scenario === "clarification" && !run.clarified) return { ...run, status: "clarification", elapsedMs };
  if (elapsedMs > 2100 && run.scenario === "interrupted") return { ...run, status: "interrupted", elapsedMs };
  if (elapsedMs > 4200) return { ...run, status: run.scenario === "partial" ? "partial" : "completed", elapsedMs };
  return { ...run, status: "running", elapsedMs };
}
export function tickConversation(conversation: Conversation, now: number): Conversation {
  const run = activeRun(conversation);
  if (!run) return conversation;
  const updated = advanceRun(run, now);
  const terminal = ["completed", "partial"].includes(updated.status);
  const answer = terminal ? fixtureAdapter.answer(updated) : undefined;
  const messages = answer && !conversation.messages.some((message) => message.role === "assistant" && message.runId === run.id)
    ? [...conversation.messages, { id: `answer-${run.id}`, role: "assistant" as const, body: answer.body, runId: run.id, answer }] : conversation.messages;
  return { ...conversation, messages, runs: conversation.runs.map((item) => item.id === run.id ? updated : item), draft: updated.status === "clarification" ? run.question : conversation.draft };
}
export function refreshInvestigation(investigation: Investigation): Investigation {
  const branch = structuredClone(investigation);
  branch.id = createId("investigation"); branch.title = `${investigation.title} · 02`; branch.branchOf = investigation.id; branch.snapshotId = "sample-02";
  branch.removedContextIds = [...new Set([...branch.context.attachments, ...branch.context.constraints])].filter((id) => !fixtureAdapter.open(id, branch.snapshotId));
  branch.context = { revision: branch.context.revision + 1, attachments: branch.context.attachments.filter((id) => !branch.removedContextIds?.includes(id)), constraints: branch.context.constraints.filter((id) => !branch.removedContextIds?.includes(id)) };
  branch.updatedAt = Date.now();
  return branch;
}
export function newProposal(investigation: Investigation): Proposal | undefined {
  const candidates = investigation.context.constraints.length ? investigation.context.constraints : investigation.context.attachments.length ? investigation.context.attachments : ["sst-2022"];
  const datasetIds = candidates.filter((id) => fixtureAdapter.open(id, investigation.snapshotId)?.source === "SST");
  if (!datasetIds.length) return undefined;
  return {
    id: createId("proposal"), title: text("Seasonal temperature comparison", "季節別の水温比較"), method: text("Monthly descriptive summary; no causal inference.", "月別の記述的集計。因果関係は推論しません。"),
    limitations: text("Sample input only. No point-to-region pairing or silent sampling.", "サンプル入力のみ。地点と地域の対応付けや暗黙のサンプリングは行いません。"), datasetIds: [...datasetIds], snapshotId: investigation.snapshotId,
    code: "# Synthetic preview — this code is never executed\nimport pandas as pd\n\ndata['month'] = pd.to_datetime(data['date']).dt.month\nmonthly = data.groupby('month')['temperature'].mean()\nresult = monthly.rename('temperature_c').reset_index()", version: 1, status: "draft",
  };
}
export function reviseProposal(proposal: Proposal, code: string): Proposal {
  return { ...proposal, code, version: proposal.version + 1, status: "draft", approvedVersion: undefined, submittedAt: undefined };
}
export function approveProposal(proposal: Proposal, reviewedVersion: number): Proposal {
  if (proposal.version !== reviewedVersion || proposal.status !== "draft") return proposal;
  return { ...proposal, status: "approved", approvedVersion: reviewedVersion };
}
export function simulateProposal(proposal: Proposal, now = Date.now()): Proposal {
  if (proposal.status !== "approved" || proposal.approvedVersion !== proposal.version) return proposal;
  return { ...proposal, status: "queued", submittedAt: now };
}
export function parseLocation(search: string, defaultView: Location["view"] = "research"): Location {
  const params = new URLSearchParams(search);
  const view = params.get("view"); const inspectorTab = params.get("section"); const workspaceTab = params.get("workspace");
  const page = Number(params.get("page"));
  return {
    view: (["research", "catalogue", "tools", "about", "feedback", "admin"].includes(view ?? "") ? view : defaultView) as Location["view"], investigationId: params.get("investigation") || undefined, conversationId: params.get("conversation") || undefined,
    nodeId: params.get("node") || "catalogue-home", snapshotId: snapshotsValid(params.get("snapshot")),
    inspectorTab: (["tables", "coverage", "methods", "provenance", "related"].includes(inspectorTab ?? "") ? inspectorTab : "overview") as Location["inspectorTab"],
    workspaceTab: (["results", "experiments", "evidence"].includes(workspaceTab ?? "") ? workspaceTab : "context") as Location["workspaceTab"], receiptId: params.get("receipt") || undefined, search: params.get("q") ?? "", page: Number.isFinite(page) ? Math.max(1, Math.floor(page)) : 1,
  };
}
const snapshotsValid = (id: string | null) => id === "sample-01" ? id : "sample-02";
export function locationUrl(location: Location): string {
  const params = new URLSearchParams(); params.set("view", location.view);
  if (location.investigationId) params.set("investigation", location.investigationId);
  if (location.conversationId) params.set("conversation", location.conversationId);
  if (location.view === "catalogue") { params.set("node", location.nodeId); params.set("snapshot", location.snapshotId); params.set("section", location.inspectorTab); if (location.search) params.set("q", location.search); if (location.page > 1) params.set("page", String(location.page)); }
  if (location.investigationId) { params.set("workspace", location.workspaceTab); if (location.receiptId) params.set("receipt", location.receiptId); }
  const pathname = ["about", "feedback", "admin"].includes(location.view) ? `/${location.view}` : "/";
  return `${pathname}?${params.toString()}`;
}
/** Reject stale/corrupt browser data rather than treating it as real evidence. */
export function restoreState(serialized: string | null): PreviewState | undefined {
  if (!serialized) return undefined;
  try {
    const value = JSON.parse(serialized) as PreviewState;
    if (value.version !== 1 || !Array.isArray(value.investigations) || value.investigations.length > 100 || !value.preferences || !["en", "ja"].includes(value.preferences.locale) || !["light", "dark"].includes(value.preferences.theme)) return undefined;
    for (const item of value.investigations) {
      if (typeof item.id !== "string" || typeof item.title !== "string" || !["sample-01", "sample-02"].includes(item.snapshotId) || !item.context || !Array.isArray(item.context.attachments) || !Array.isArray(item.context.constraints) || !Array.isArray(item.conversations) || !item.conversations.length || !Array.isArray(item.proposals)) return undefined;
      if (!validContext(item.context) || !Number.isFinite(item.updatedAt)) return undefined;
      for (const conversation of item.conversations) {
        if (typeof conversation.id !== "string" || typeof conversation.draft !== "string" || !conversation.title || typeof conversation.title.en !== "string" || typeof conversation.title.ja !== "string" || !Array.isArray(conversation.runs) || !Array.isArray(conversation.messages)) return undefined;
        for (const message of conversation.messages) {
          if (typeof message.id !== "string" || !["user", "assistant"].includes(message.role) || !validText(message.body)) return undefined;
          const receipt = message.answer?.receipt;
          if (message.answer && (!validText(message.answer.body) || !receipt || !Array.isArray(receipt.inputIds) || !validText(receipt.limitation) || !receipt.table || !validText(receipt.table.entity) || !Array.isArray(receipt.table.columns) || !Array.isArray(receipt.table.rows) || !receipt.table.columns.every((column) => typeof column.key === "string" && validText(column.title)) || !receipt.table.rows.every((row) => row && Object.values(row).every((cell) => typeof cell === "string" || typeof cell === "number" && Number.isFinite(cell))))) return undefined;
        }
        for (const run of conversation.runs) {
          if (typeof run.id !== "string" || typeof run.question !== "string" || !validContext(run.context) || !Number.isFinite(run.startedAt) || !Number.isFinite(run.elapsedMs) || !["queued", "running", "clarification", "cancelling", "cancelled", "completed", "partial", "error", "interrupted"].includes(run.status)) return undefined;
        }
      }
      for (const proposal of item.proposals) if (typeof proposal.id !== "string" || typeof proposal.code !== "string" || !validText(proposal.title) || !validText(proposal.method) || !validText(proposal.limitations) || !Array.isArray(proposal.datasetIds) || !Number.isFinite(proposal.version) || !["draft", "approved", "queued", "completed"].includes(proposal.status)) return undefined;
    }
    // Preserve first-round P00 drafts while adding the new local role/feedback UI.
    if (!["viewer", "researcher", "admin"].includes(value.preferences.role)) value.preferences.role = "researcher";
    if (!["research", "commercial", "internal"].includes(value.preferences.accountType)) value.preferences.accountType = "research";
    if (!value.feedback) value.feedback = [];
    if (!Array.isArray(value.feedback) || !value.feedback.every((entry) => typeof entry.id === "string" && typeof entry.message === "string" && Number.isFinite(entry.createdAt) && ["issue", "idea", "answer"].includes(entry.category) && ["new", "reviewing", "resolved"].includes(entry.status) && (entry.rating === undefined || ["helpful", "unhelpful"].includes(entry.rating)) && [entry.reason, entry.runId, entry.investigationId].every((item) => item === undefined || typeof item === "string"))) return undefined;
    if (!value.feedbackDraft) value.feedbackDraft = { category: "idea", message: "", reason: "" };
    if (!["issue", "idea", "answer"].includes(value.feedbackDraft.category) || typeof value.feedbackDraft.message !== "string" || typeof value.feedbackDraft.reason !== "string") return undefined;
    value.preferences.workspaceWidth = Math.max(320, Math.min(620, Number(value.preferences.workspaceWidth) || 390));
    return value;
  } catch { return undefined; }
}
function validText(value: unknown) {
  return !!value && typeof value === "object" && typeof (value as { en?: unknown }).en === "string" && typeof (value as { ja?: unknown }).ja === "string";
}
function validContext(value: ContextRevision) {
  return !!value && Number.isFinite(value.revision) && Array.isArray(value.attachments) && value.attachments.every((id) => typeof id === "string") && Array.isArray(value.constraints) && value.constraints.every((id) => typeof id === "string");
}
