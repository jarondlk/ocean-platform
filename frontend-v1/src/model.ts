import type { FeedbackDraft, FeedbackEntry } from "./feedback-model";
export type Locale = "en" | "ja";
export type Role = "viewer" | "researcher" | "admin";
export type AccountType = "research" | "commercial" | "internal";
export type Text = { en: string; ja: string };
export type Source = "CTD" | "SST" | "Metagenome" | "eDNA";
export type Root = "data" | "analyses" | "statistics" | "metadata" | "relationships";
export type Scenario = "normal" | "loading" | "empty" | "zero" | "unknown" | "error" | "unavailable" | "revoked" | "partial" | "clarification" | "interrupted";
export type WorkspaceTab = "context" | "results" | "experiments" | "evidence";
export type InspectorTab = "overview" | "tables" | "coverage" | "methods" | "provenance" | "related";
export type Cell = string | number;
export type Table = { columns: { key: string; title: Text; unit?: string }[]; rows: Record<string, Cell>[]; entity: Text };
export type CatalogueNode = {
  id: string; parentId: string | null; title: Text; kind: "directory" | "dataset" | "reference" | "analysis" | "workflow";
  root: Root; source?: Source; year?: number; purpose: Text; limitation: Text; relatedIds: string[];
};
export type Snapshot = { id: string; title: Text; date: string; excludedIds: string[] };
export type ContextRevision = { revision: number; attachments: string[]; constraints: string[] };
export type RunStatus = "queued" | "running" | "clarification" | "cancelling" | "cancelled" | "completed" | "partial" | "error" | "interrupted";
export type Run = {
  id: string; question: string; snapshotId: string; context: ContextRevision; scenario: Scenario;
  status: RunStatus; startedAt: number; elapsedMs: number; cancellationAt?: number; continuationOf?: string; clarified?: boolean;
};
export type Receipt = {
  id: string; operation: "inventory" | "summary"; authority: "descriptive" | "published" | "experimental";
  snapshotId: string; contextRevision: number; inputIds: string[]; parameters: Record<string, string>;
  totalRows: number; complete: boolean; contentIdentity: string; table: Table; limitation: Text;
};
export type Answer = { body: Text; receipt: Receipt; series?: { label: string; value: number }[] };
export type Message = { id: string; role: "user" | "assistant"; body: Text; runId?: string; answer?: Answer };
export type Conversation = { id: string; title: Text; draft: string; messages: Message[]; runs: Run[] };
export type Proposal = {
  id: string; title: Text; code: string; method: Text; limitations: Text; datasetIds: string[]; snapshotId: string;
  version: number; approvedVersion?: number; status: "draft" | "approved" | "queued" | "completed";
  submittedAt?: number;
};
export type Investigation = {
  id: string; title: string; snapshotId: string; context: ContextRevision; conversations: Conversation[];
  proposals: Proposal[]; updatedAt: number; branchOf?: string; removedContextIds?: string[];
};
export type PreviewState = {
  version: 1; investigations: Investigation[]; feedback: FeedbackEntry[]; feedbackDraft: FeedbackDraft;
  preferences: { locale: Locale; theme: "light" | "dark"; workspaceWidth: number; workspaceOpen: boolean; role: Role; accountType: AccountType };
};
export type Location = {
  view: "research" | "catalogue" | "tools" | "about" | "feedback" | "admin"; investigationId?: string; conversationId?: string;
  nodeId: string; snapshotId: string; inspectorTab: InspectorTab; workspaceTab: WorkspaceTab; receiptId?: string; search: string; page: number;
};
export const text = (en: string, ja: string): Text => ({ en, ja });
