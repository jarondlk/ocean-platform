export type FeedbackEntry = {
  id: string;
  category: "issue" | "idea" | "answer";
  message: string;
  createdAt: number;
  status: "new" | "reviewing" | "resolved";
  investigationId?: string;
  runId?: string;
  rating?: "helpful" | "unhelpful";
  reason?: string;
};
export type FeedbackDraft = { category: FeedbackEntry["category"]; message: string; reason: string };
export function saveLocalFeedback(entries: FeedbackEntry[], next: FeedbackEntry): FeedbackEntry[] {
  if (next.rating === "unhelpful" && !next.message.trim() && !next.reason?.trim()) throw new Error("Choose a reason or add a comment.");
  if (!next.rating && !next.message.trim()) throw new Error("Add a comment.");
  return [next, ...entries.filter((entry) => entry.id !== next.id && !(next.runId && entry.runId === next.runId && entry.category === "answer"))];
}
export function triageLocalFeedback(entries: FeedbackEntry[], id: string, status: FeedbackEntry["status"]): FeedbackEntry[] {
  return entries.map((entry) => entry.id === id ? { ...entry, status } : entry);
}
