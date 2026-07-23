"use client";

import { useState } from "react";
import { Check, ThumbsDown, ThumbsUp } from "lucide-react";
import { putChatFeedback } from "@/lib/api";
import {
  feedbackReasons,
  type FeedbackRating,
} from "@/lib/feedback";

export function ChatFeedback({
  interactionId,
}: {
  interactionId: string;
}) {
  const [rating, setRating] = useState<FeedbackRating | null>(null);
  const [selectedReasons, setSelectedReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  function selectRating(nextRating: FeedbackRating) {
    if (nextRating !== rating) {
      setSelectedReasons([]);
      setComment("");
    }
    setRating(nextRating);
    setSaved(false);
    setError("");
  }

  function toggleReason(code: string) {
    setSelectedReasons((current) =>
      current.includes(code)
        ? current.filter((reason) => reason !== code)
        : [...current, code],
    );
    setSaved(false);
  }

  async function saveFeedback() {
    if (rating === null || (rating === -1 && selectedReasons.length === 0)) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      await putChatFeedback(interactionId, {
        rating,
        reason_codes: selectedReasons,
        comment: comment.trim() || undefined,
      });
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save feedback");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="chat-feedback" aria-label="Answer feedback">
      <div className="chat-feedback-heading">
        <span>Was this answer useful?</span>
        <div className="chat-feedback-rating">
          <button
            aria-label="Give positive feedback"
            aria-pressed={rating === 1}
            className={`feedback-icon-button${rating === 1 ? " selected" : ""}`}
            onClick={() => selectRating(1)}
            title="Useful answer"
            type="button"
          >
            <ThumbsUp size={17} aria-hidden="true" />
          </button>
          <button
            aria-label="Give negative feedback"
            aria-pressed={rating === -1}
            className={`feedback-icon-button${rating === -1 ? " selected" : ""}`}
            onClick={() => selectRating(-1)}
            title="Answer needs improvement"
            type="button"
          >
            <ThumbsDown size={17} aria-hidden="true" />
          </button>
        </div>
      </div>

      {rating !== null ? (
        <div className="chat-feedback-details">
          <span className="feedback-prompt">
            {rating === -1
              ? "What should be improved? Select at least one."
              : "What worked well? Optional."}
          </span>
          <div className="feedback-reasons">
            {feedbackReasons[rating].map((reason) => (
              <button
                aria-pressed={selectedReasons.includes(reason.code)}
                className={`feedback-reason${
                  selectedReasons.includes(reason.code) ? " selected" : ""
                }`}
                key={reason.code}
                onClick={() => toggleReason(reason.code)}
                type="button"
              >
                {reason.label}
              </button>
            ))}
          </div>
          <label className="feedback-comment">
            <span>Additional detail (optional)</span>
            <textarea
              className="textarea"
              maxLength={1000}
              onChange={(event) => {
                setComment(event.target.value);
                setSaved(false);
              }}
              placeholder="Tell us what made this answer useful or how it could improve."
              rows={3}
              value={comment}
            />
          </label>
          <div className="feedback-actions">
            <button
              className="button secondary-button"
              disabled={
                saving ||
                (rating === -1 && selectedReasons.length === 0)
              }
              onClick={() => void saveFeedback()}
              type="button"
            >
              {saving ? "Saving" : saved ? "Update feedback" : "Save feedback"}
            </button>
            {saved ? (
              <span className="feedback-saved" role="status">
                <Check size={15} aria-hidden="true" />
                Feedback recorded
              </span>
            ) : null}
          </div>
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
