"use client";
import { Check, Download, MessageSquare, Send, ThumbsDown, ThumbsUp } from "lucide-react";
import type { FeedbackDraft, FeedbackEntry } from "./feedback-model";
import type { Locale } from "./model";
import { downloadJson } from "./exports";
import "./support-views.css";

export function FeedbackForm({ locale, draft, onChange, onSubmit, rating, compact = false }: { locale: Locale; draft: FeedbackDraft; onChange: (draft: FeedbackDraft) => void; onSubmit: () => void; rating?: FeedbackEntry["rating"]; compact?: boolean }) {
  const en = locale === "en";
  const reasons = [
    ["scope", "Scope", "範囲"], ["coverage", "Coverage", "カバレッジ"], ["evidence", "Evidence", "根拠"], ["accuracy", "Scientific qualification", "科学的な条件"], ["clarity", "Clarity", "わかりやすさ"], ["other", "Other", "その他"],
  ];
  return <form className={`feedback-form ${compact ? "compact" : ""}`} onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
    {!rating && <label>{en ? "Category" : "種別"}<select value={draft.category} onChange={(event) => onChange({ ...draft, category: event.target.value as FeedbackEntry["category"] })}><option value="issue">{en ? "Issue" : "問題"}</option><option value="idea">{en ? "Suggestion" : "提案"}</option><option value="answer">{en ? "Answer" : "回答"}</option></select></label>}
    {rating === "unhelpful" && <fieldset><legend>{en ? "What needs improvement?" : "改善してほしい点は？"}</legend><div className="feedback-reasons">{reasons.map(([id, english, japanese]) => <button type="button" key={id} aria-pressed={draft.reason === id} onClick={() => onChange({ ...draft, reason: id })}>{en ? english : japanese}</button>)}</div></fieldset>}
    <label>{en ? "Comment" : "コメント"}<textarea required={!rating || (rating === "unhelpful" && !draft.reason)} value={draft.message} onChange={(event) => onChange({ ...draft, message: event.target.value })} rows={compact ? 3 : 5} maxLength={2000} placeholder={en ? "What could work better?" : "改善点を教えてください"} /></label>
    <div className="feedback-submit"><span>{en ? "Saved locally · no message sent" : "ローカル保存・外部送信なし"}</span><button className="button primary" type="submit" disabled={rating === "unhelpful" ? !draft.reason && !draft.message.trim() : !draft.message.trim()}><Send size={15} />{en ? "Save feedback" : "フィードバックを保存"}</button></div>
  </form>;
}
export function FeedbackView({ locale, entries, draft, onChange, onSubmit }: { locale: Locale; entries: FeedbackEntry[]; draft: FeedbackDraft; onChange: (draft: FeedbackDraft) => void; onSubmit: () => void }) {
  const en = locale === "en";
  return <section className="support-view"><header className="page-header"><div><div className="eyebrow">OCEAN / {en ? "Feedback" : "フィードバック"}</div><h1>{en ? "Feedback" : "フィードバック"}</h1></div><span className="small-badge">{en ? "Local preview" : "ローカルプレビュー"}</span></header><div className="feedback-layout"><article className="feedback-compose"><h2>{en ? "Share a note" : "ご意見を共有"}</h2><FeedbackForm locale={locale} draft={draft} onChange={onChange} onSubmit={onSubmit} /></article><aside className="feedback-history"><div className="workspace-section-title"><h2>{en ? "Your feedback" : "保存したフィードバック"}</h2>{!!entries.length && <button className="text-button" onClick={() => downloadJson({ label: "P00 local sample feedback", entries }, "sample-feedback.json")}><Download size={14} />{en ? "Export" : "エクスポート"}</button>}</div>{entries.length ? entries.map((entry) => <article key={entry.id} className="feedback-entry"><div>{entry.rating === "helpful" ? <ThumbsUp size={14} /> : entry.rating === "unhelpful" ? <ThumbsDown size={14} /> : <MessageSquare size={14} />}<strong>{en ? entry.category === "answer" ? "Answer feedback" : entry.category === "idea" ? "Suggestion" : "Issue" : entry.category === "answer" ? "回答のフィードバック" : entry.category === "idea" ? "提案" : "問題"}</strong><span className="small-badge">{en ? entry.status === "new" ? "New" : entry.status === "reviewing" ? "Reviewing" : "Resolved" : entry.status === "new" ? "新規" : entry.status === "reviewing" ? "確認中" : "解決済み"}</span></div><p>{entry.message || (entry.rating === "helpful" ? en ? "Helpful sample answer" : "役立つサンプル回答" : entry.reason)}</p><span className="muted small"><Check size={11} /> {en ? "Saved locally" : "ローカル保存"}</span></article>) : <div className="empty-workspace"><MessageSquare size={25} /><p>{en ? "No feedback yet" : "フィードバックはまだありません"}</p></div>}</aside></div></section>;
}
