"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Download,
  RefreshCw,
  Search,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { MarkdownAnswer } from "@/components/MarkdownAnswer";
import {
  downloadAdminFeedbackCsv,
  getAdminFeedback,
  getAdminFeedbackDetail,
  type AdminFeedbackFilters,
} from "@/lib/api";
import {
  feedbackReasonLabels,
  feedbackReasons,
} from "@/lib/feedback";
import type {
  AdminFeedbackDetail,
  AdminFeedbackListItem,
  AdminFeedbackListResponse,
} from "@/types";
import { useAppPreferences } from "@/lib/preferences";


type FilterDraft = {
  rating: "" | "1" | "-1";
  reasonCode: string;
  dateFrom: string;
  dateTo: string;
  model: string;
  role: string;
  accountType: string;
  search: string;
};

const emptyFilters: FilterDraft = {
  rating: "",
  reasonCode: "",
  dateFrom: "",
  dateTo: "",
  model: "",
  role: "",
  accountType: "",
  search: "",
};

const pageSize = 25;

export default function AdminFeedbackPage() {
  const { ui } = useAppPreferences();
  const [draft, setDraft] = useState<FilterDraft>(emptyFilters);
  const [activeFilters, setActiveFilters] =
    useState<AdminFeedbackFilters>({});
  const [result, setResult] = useState<AdminFeedbackListResponse | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<AdminFeedbackDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  async function load(
    filters: AdminFeedbackFilters,
    nextOffset: number,
  ) {
    setLoading(true);
    setError("");
    try {
      const payload = await getAdminFeedback({
        ...filters,
        limit: pageSize,
        offset: nextOffset,
      });
      setResult(payload);
      setSelectedId((current) => {
        if (payload.items.some((item) => item.feedback_id === current)) {
          return current;
        }
        return payload.items[0]?.feedback_id || "";
      });
      if (payload.items.length === 0) {
        setDetail(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load feedback");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load({}, 0);
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let active = true;
    setDetailLoading(true);
    getAdminFeedbackDetail(selectedId)
      .then((payload) => {
        if (active) setDetail(payload);
      })
      .catch((err) => {
        if (active) {
          setError(
            err instanceof Error ? err.message : "Could not load feedback detail",
          );
        }
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedId]);

  const reasonEntries = useMemo(
    () => Object.entries(result?.metrics.reason_counts || {}),
    [result],
  );

  function updateDraft<K extends keyof FilterDraft>(
    key: K,
    value: FilterDraft[K],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function requestFilters(values: FilterDraft): AdminFeedbackFilters {
    return {
      rating: values.rating
        ? (Number(values.rating) as -1 | 1)
        : undefined,
      reason_code: values.reasonCode || undefined,
      date_from: values.dateFrom || undefined,
      date_to: values.dateTo || undefined,
      model: values.model.trim() || undefined,
      role: values.role
        ? (values.role as AdminFeedbackFilters["role"])
        : undefined,
      account_type: values.accountType
        ? (values.accountType as AdminFeedbackFilters["account_type"])
        : undefined,
      search: values.search.trim() || undefined,
    };
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const filters = requestFilters(draft);
    setActiveFilters(filters);
    void load(filters, 0);
  }

  function resetFilters() {
    setDraft(emptyFilters);
    setActiveFilters({});
    void load({}, 0);
  }

  async function exportCsv() {
    setExporting(true);
    setError("");
    try {
      const { blob, filename } = await downloadAdminFeedbackCsv(activeFilters);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const offset = result?.offset || 0;
  const canGoBack = offset > 0;
  const canGoForward = Boolean(
    result && offset + result.items.length < result.total,
  );

  return (
    <section>
      <header className="page-header">
        <h2>{ui("Feedback review")}</h2>
      </header>

      <article className="card">
        <form
          className="admin-feedback-filters"
          onSubmit={applyFilters}
        >
          <label className="settings-field feedback-search-field">
            <span>{ui("Search")}</span>
            <div className="field-with-icon">
              <Search size={15} aria-hidden="true" />
              <input
                className="field"
                onChange={(event) => updateDraft("search", event.target.value)}
                placeholder={ui("Question, answer, comment, or user")}
                value={draft.search}
              />
            </div>
          </label>
          <label className="settings-field">
            <span>{ui("Rating")}</span>
            <select
              className="field"
              onChange={(event) =>
                updateDraft(
                  "rating",
                  event.target.value as FilterDraft["rating"],
                )
              }
              value={draft.rating}
            >
              <option value="">{ui("All ratings")}</option>
              <option value="1">{ui("Positive")}</option>
              <option value="-1">{ui("Negative")}</option>
            </select>
          </label>
          <label className="settings-field">
            <span>{ui("Reason")}</span>
            <select
              className="field"
              onChange={(event) =>
                updateDraft("reasonCode", event.target.value)
              }
              value={draft.reasonCode}
            >
              <option value="">{ui("All reasons")}</option>
              <optgroup label={ui("Positive")}>
                {feedbackReasons[1].map((reason) => (
                  <option key={reason.code} value={reason.code}>
                    {reason.label}
                  </option>
                ))}
              </optgroup>
              <optgroup label={ui("Negative")}>
                {feedbackReasons[-1].map((reason) => (
                  <option key={reason.code} value={reason.code}>
                    {reason.label}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
          <label className="settings-field">
            <span>{ui("Role")}</span>
            <select
              className="field"
              onChange={(event) => updateDraft("role", event.target.value)}
              value={draft.role}
            >
              <option value="">{ui("All roles")}</option>
              <option value="viewer">Viewer</option>
              <option value="researcher">Researcher</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <label className="settings-field">
            <span>{ui("Account type")}</span>
            <select
              className="field"
              onChange={(event) =>
                updateDraft("accountType", event.target.value)
              }
              value={draft.accountType}
            >
              <option value="">{ui("All account types")}</option>
              <option value="research">Research</option>
              <option value="commercial">Commercial</option>
              <option value="internal">Internal</option>
            </select>
          </label>
          <label className="settings-field">
            <span>{ui("Model")}</span>
            <input
              className="field"
              onChange={(event) => updateDraft("model", event.target.value)}
              placeholder="Exact model name"
              value={draft.model}
            />
          </label>
          <label className="settings-field">
            <span>{ui("From")}</span>
            <input
              className="field"
              onChange={(event) => updateDraft("dateFrom", event.target.value)}
              type="date"
              value={draft.dateFrom}
            />
          </label>
          <label className="settings-field">
            <span>{ui("To")}</span>
            <input
              className="field"
              onChange={(event) => updateDraft("dateTo", event.target.value)}
              type="date"
              value={draft.dateTo}
            />
          </label>
          <div className="feedback-filter-actions">
            <button className="button" disabled={loading} type="submit">
              {ui("Apply filters")}
            </button>
            <button
              className="button secondary-button"
              disabled={loading}
              onClick={resetFilters}
              type="button"
            >
              <RefreshCw size={15} aria-hidden="true" />
              {ui("Reset")}
            </button>
            <button
              className="button secondary-button"
              disabled={exporting}
              onClick={() => void exportCsv()}
              type="button"
            >
              <Download size={15} aria-hidden="true" />
              {exporting ? ui("Exporting") : ui("Export CSV")}
            </button>
          </div>
        </form>
        {error ? <p className="error-text">{error}</p> : null}
      </article>

      <article className="card">
        <div className="summary-strip admin-feedback-metrics">
          <SummaryCell label="Responses" value={result?.metrics.total ?? 0} />
          <SummaryCell label="Positive" value={result?.metrics.positive ?? 0} />
          <SummaryCell label="Negative" value={result?.metrics.negative ?? 0} />
          <SummaryCell
            label="Positive rate"
            value={formatRate(result?.metrics.positive_rate)}
          />
        </div>
        <div className="feedback-reason-summary">
          <span>{ui("Common reasons")}</span>
          {reasonEntries.length ? (
            reasonEntries.slice(0, 8).map(([reason, count]) => (
              <span className="feedback-reason-count" key={reason}>
                {feedbackReasonLabels[reason] || reason} · {count}
              </span>
            ))
          ) : (
            <span className="empty-state">No reasons in this view.</span>
          )}
        </div>
      </article>

      <div className="feedback-review-layout">
        <article className="card feedback-review-list">
          <div className="section-toolbar">
            <h3 className="section-title">{ui("Responses")}</h3>
            <span className="empty-state">
              {result
                ? `${result.total.toLocaleString()} matching`
                : "Loading"}
            </span>
          </div>
          <div className="table-scroll">
            <table className="feedback-list-table">
              <thead>
                <tr>
                  <th>{ui("Rating")}</th>
                  <th>{ui("Question")}</th>
                  <th>{ui("User")}</th>
                  <th>{ui("Submitted")}</th>
                </tr>
              </thead>
              <tbody>
                {(result?.items || []).map((item) => (
                  <FeedbackRow
                    item={item}
                    key={item.feedback_id}
                    onSelect={setSelectedId}
                    selected={item.feedback_id === selectedId}
                  />
                ))}
                {!loading && result?.items.length === 0 ? (
                  <tr>
                    <td colSpan={4}>No feedback matches these filters.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="feedback-pagination">
            <button
              className="button secondary-button"
              disabled={loading || !canGoBack}
              onClick={() =>
                void load(activeFilters, Math.max(0, offset - pageSize))
              }
              type="button"
            >
              {ui("Previous")}
            </button>
            <span className="empty-state">
              {result?.total
                ? `${offset + 1}–${Math.min(
                    offset + result.items.length,
                    result.total,
                  )} of ${result.total}`
                : "0 results"}
            </span>
            <button
              className="button secondary-button"
              disabled={loading || !canGoForward}
              onClick={() => void load(activeFilters, offset + pageSize)}
              type="button"
            >
              {ui("Next")}
            </button>
          </div>
        </article>

        <FeedbackDetail detail={detail} loading={detailLoading} />
      </div>
    </section>
  );
}

function FeedbackRow({
  item,
  onSelect,
  selected,
}: {
  item: AdminFeedbackListItem;
  onSelect: (feedbackId: string) => void;
  selected: boolean;
}) {
  return (
    <tr
      aria-selected={selected}
      className="selectable-row"
      onClick={() => onSelect(item.feedback_id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(item.feedback_id);
        }
      }}
      tabIndex={0}
    >
      <td>
        <RatingBadge rating={item.rating} />
      </td>
      <td>
        <strong>{truncate(item.query, 92)}</strong>
        <small>
          {item.reason_codes
            .map((reason) => feedbackReasonLabels[reason] || reason)
            .join(", ") || "No reason supplied"}
        </small>
      </td>
      <td>
        {item.user_display_name || item.user_email}
        <small>
          {item.user_role} · {item.user_account_type}
        </small>
      </td>
      <td>{formatDate(item.feedback_created_at)}</td>
    </tr>
  );
}

function FeedbackDetail({
  detail,
  loading,
}: {
  detail: AdminFeedbackDetail | null;
  loading: boolean;
}) {
  const { ui } = useAppPreferences();
  const evidenceCount = detail
    ? ["sources", "linked_sources", "analysis_context", "reliability_context"]
        .map((key) => detail.evidence_snapshot[key])
        .reduce<number>(
          (count, value) => count + (Array.isArray(value) ? value.length : 0),
          0,
        )
    : 0;

  return (
    <article className="card feedback-detail-card">
      <div className="section-toolbar">
        <h3 className="section-title">{ui("Review detail")}</h3>
        {detail ? <RatingBadge rating={detail.rating} /> : null}
      </div>
      {loading ? <p className="empty-state">{ui("Loading detail…")}</p> : null}
      {!loading && !detail ? (
        <p className="empty-state">{ui("Select a response to review it.")}</p>
      ) : null}
      {!loading && detail ? (
        <>
          <div className="feedback-detail-meta">
            <SummaryCell
              label="User"
              value={detail.user_display_name || detail.user_email}
            />
            <SummaryCell label="Role" value={detail.user_role} />
            <SummaryCell label="Account" value={detail.user_account_type} />
            <SummaryCell label="Model" value={detail.model || "Unknown"} />
            <SummaryCell
              label="Latency"
              value={
                detail.latency_ms === null ||
                detail.latency_ms === undefined
                  ? "NA"
                  : `${detail.latency_ms.toLocaleString()} ms`
              }
            />
            <SummaryCell
              label="Submitted"
              value={formatDate(detail.feedback_created_at)}
            />
          </div>

          <section className="feedback-detail-section">
            <h4 className="subsection-title">{ui("Feedback")}</h4>
            <div className="feedback-detail-reasons">
              {detail.reason_codes.length
                ? detail.reason_codes.map((reason) => (
                    <span className="feedback-reason-count" key={reason}>
                      {feedbackReasonLabels[reason] || reason}
                    </span>
                  ))
                : <span className="empty-state">{ui("No reason supplied.")}</span>}
            </div>
            <p className="feedback-comment-text">
              {detail.comment || ui("No additional comment.")}
            </p>
          </section>

          <section className="feedback-detail-section">
            <h4 className="subsection-title">{ui("Question")}</h4>
            <p>{detail.query}</p>
          </section>

          <section className="feedback-detail-section">
            <h4 className="subsection-title">{ui("Answer")}</h4>
            <MarkdownAnswer text={detail.answer || ""} />
          </section>

          <details className="debug-block feedback-debug-block">
            <summary>{ui("Evidence snapshot")} ({evidenceCount})</summary>
            <pre>{JSON.stringify(detail.evidence_snapshot, null, 2)}</pre>
          </details>
          <details className="debug-block feedback-debug-block">
            <summary>{ui("Trust report")}</summary>
            <pre>
              {JSON.stringify(
                detail.answer_audit_snapshot || {
                  status: ui("No trust report was recorded."),
                },
                null,
                2,
              )}
            </pre>
          </details>
          <details className="debug-block feedback-debug-block">
            <summary>{ui("Request and prompt metadata")}</summary>
            <pre>
              {JSON.stringify(
                {
                  request_options: detail.request_options,
                  corpus_fingerprint: detail.corpus_fingerprint,
                  prompt_version: detail.prompt_version,
                  prompt_sha256: detail.prompt_sha256,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      ) : null}
    </article>
  );
}

function RatingBadge({ rating }: { rating: -1 | 1 }) {
  const { ui } = useAppPreferences();
  return (
    <span
      className={`feedback-rating-badge ${
        rating === 1 ? "positive" : "negative"
      }`}
    >
      {rating === 1 ? (
        <ThumbsUp size={14} aria-hidden="true" />
      ) : (
        <ThumbsDown size={14} aria-hidden="true" />
      )}
      {ui(rating === 1 ? "Positive" : "Negative")}
    </span>
  );
}

function SummaryCell({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  const { ui } = useAppPreferences();
  return (
    <div>
      <span>{ui(label)}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatRate(value?: number | null): string {
  return value === null || value === undefined
    ? "NA"
    : `${Math.round(value * 100)}%`;
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString();
}

function truncate(value: string, limit: number): string {
  return value.length <= limit ? value : `${value.slice(0, limit - 1)}…`;
}
