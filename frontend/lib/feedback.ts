export type FeedbackRating = -1 | 1;

export const feedbackReasons: Record<
  FeedbackRating,
  Array<{ code: string; label: string }>
> = {
  1: [
    { code: "accurate", label: "Accurate" },
    { code: "relevant", label: "Relevant" },
    { code: "well_cited", label: "Well cited" },
    { code: "clear", label: "Clear" },
    { code: "helpful", label: "Helpful" },
  ],
  [-1]: [
    { code: "incorrect", label: "Incorrect" },
    { code: "missing_evidence", label: "Missing evidence" },
    { code: "incorrect_citation", label: "Incorrect citation" },
    { code: "incomplete", label: "Incomplete" },
    { code: "irrelevant", label: "Irrelevant" },
    { code: "unclear", label: "Unclear" },
    { code: "outdated", label: "Outdated" },
    { code: "other", label: "Other" },
  ],
};

export const feedbackReasonLabels = Object.fromEntries(
  Object.values(feedbackReasons)
    .flat()
    .map((reason) => [reason.code, reason.label]),
) as Record<string, string>;
