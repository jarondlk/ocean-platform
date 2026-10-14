"use client";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Activity, ArrowRight, Check, ChevronLeft, ChevronRight, ClipboardList, Database, Download, GitBranch, LockKeyhole, MessagesSquare, RotateCcw, Settings2, ShieldCheck, UserPlus, UsersRound } from "lucide-react";
import { catalogue, snapshots } from "./fixtures";
import type { FeedbackEntry } from "./feedback-model";
import type { Locale } from "./model";
import { ADMIN_STORAGE_KEY, AdminError, adminCsv, applyAdminAction, createAdminState, databaseInventory, reconcileAdminConfigDraft, restoreAdminState, sameAdminConfig, serializeAdminState, type AccountType, type AdminAction, type AdminConfig, type AdminErrorCode, type AdminRole, type AdminSection, type AdminState } from "./admin-model";
import "./admin.css";

type Props = { locale: Locale; canAdmin: boolean; feedback: FeedbackEntry[]; onFeedbackStatus: (id: string, status: FeedbackEntry["status"]) => void };
const sectionOrder: AdminSection[] = ["overview", "users", "feedback", "database", "catalogue", "system", "audit"];
const sectionLabels: Record<AdminSection, [string, string]> = { overview: ["Overview", "概要"], users: ["Users & invitations", "アカウント・招待"], feedback: ["Feedback", "フィードバック"], database: ["Database", "データベース"], catalogue: ["Catalogue & retention", "カタログ・保持"], system: ["System & settings", "システム・設定"], audit: ["Audit & debug", "監査・診断"] };
const sectionIcons = { overview: Activity, users: UsersRound, feedback: MessagesSquare, database: Database, catalogue: GitBranch, system: Settings2, audit: ClipboardList };
const roleLabels: Record<AdminRole, [string, string]> = { viewer: ["Viewer", "閲覧者"], researcher: ["Researcher", "研究者"], admin: ["Admin", "管理者"] };
const accountLabels: Record<AccountType, [string, string]> = { research: ["Research", "研究"], commercial: ["Commercial", "商用"], internal: ["Internal", "内部"] };
const statusLabels: Record<string, [string, string]> = { active: ["Active", "有効"], suspended: ["Suspended", "停止"], pending: ["Pending", "待機"], revoked: ["Revoked", "取消済み"], expired: ["Expired", "期限切れ"], queued: ["Queued", "待機中"], running: ["Running", "実行中"], completed: ["Completed", "完了"], cancelled: ["Cancelled", "キャンセル済み"], error: ["Needs attention", "要確認"], new: ["New", "新着"], reviewing: ["Reviewing", "確認中"], resolved: ["Resolved", "対応済み"], issue: ["Issue", "問題"], idea: ["Idea", "提案"], answer: ["Answer", "回答"], helpful: ["Helpful", "役立った"], unhelpful: ["Unhelpful", "役立たなかった"] };
const errors: Record<AdminErrorCode, [string, string]> = { access: ["Choose the Admin preview role to open this area.", "管理者のプレビューロールを選択してください。"], self: ["The preview administrator stays active.", "プレビュー管理者は有効のまま維持されます。"], missing: ["This demo record is no longer available.", "このサンプル記録は利用できません。"], email: ["Use a synthetic address ending in .example or .test.", ".example または .test で終わる架空のアドレスを入力してください。"], duplicate: ["This demo account or pending invitation already exists.", "このサンプルアカウントまたは有効な招待はすでに存在します。"], paused: ["The demo queue is paused. Resume it in System & settings.", "サンプルキューは停止中です。システム・設定から再開してください。"], capacity: ["The demo running-job limit is reached. Complete or cancel a job first.", "サンプルの同時実行上限に達しました。先にジョブを完了または取り消してください。"], terminal: ["This simulation has already ended. Queue a new one.", "このシミュレーションは終了しました。新しいものを追加してください。"], config: ["Check the preview settings and allowed ranges.", "プレビュー設定と許容範囲を確認してください。"] };
const date = (time: number, locale: Locale) => new Intl.DateTimeFormat(locale === "ja" ? "ja-JP" : "en-GB", { timeZone: "Asia/Tokyo", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(time);
const translated = (pair: [string, string], locale: Locale) => pair[locale === "en" ? 0 : 1];

export function AdminView(props: Props) {
  const t = (en: string, ja: string) => props.locale === "en" ? en : ja;
  if (!props.canAdmin) return <section className="admin-unavailable"><LockKeyhole size={26} strokeWidth={1.5} /><h1>{t("Admin access", "管理者アクセス")}</h1><p>{t("This area is available to the Admin preview role.", "この画面は管理者プレビューロールで利用できます。")}</p><span className="small-badge">{t("Role simulation · no real sign-in", "ロールのシミュレーション・実際のログインではありません")}</span></section>;
  return <AdminWorkspace {...props} />;
}

function AdminWorkspace({ locale, canAdmin, feedback, onFeedbackStatus }: Props) {
  const t = (en: string, ja: string) => locale === "en" ? en : ja;
  const [section, setSection] = useState<AdminSection>("overview");
  const [state, setState] = useState(createAdminState);
  const [storageReady, setStorageReady] = useState(false);
  const [storageStatus, setStorageStatus] = useState<"loading" | "saved" | "unavailable">("loading");
  const [undo, setUndo] = useState<{ state: AdminState; feedback?: Pick<FeedbackEntry, "id" | "status"> }>();
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<AdminRole>("researcher");
  const [inviteAccount, setInviteAccount] = useState<AccountType>("research");
  const [userSearch, setUserSearch] = useState("");
  const [feedbackSearch, setFeedbackSearch] = useState("");
  const [feedbackFilter, setFeedbackFilter] = useState("");
  const [feedbackCategory, setFeedbackCategory] = useState("");
  const [feedbackRating, setFeedbackRating] = useState("");
  const [selectedFeedback, setSelectedFeedback] = useState("");
  const [tableId, setTableId] = useState("catalogue_nodes");
  const [databaseSearch, setDatabaseSearch] = useState("");
  const [databasePage, setDatabasePage] = useState(1);
  const [selectedRow, setSelectedRow] = useState("");
  const [auditSearch, setAuditSearch] = useState("");
  const [configDraft, setConfigDraft] = useState<AdminConfig>(state.config);
  const previousCommittedConfig = useRef(state.config);
  useEffect(() => {
    if (!canAdmin) return;
    try {
      const raw = localStorage.getItem(ADMIN_STORAGE_KEY);
      const restored = restoreAdminState(raw, canAdmin);
      if (restored) setState(restored);
      if (raw && !restored) setNotice(locale === "en" ? "Saved demo could not be restored. Sample values loaded." : "保存済みサンプルを復元できなかったため、初期値を読み込みました。");
    } catch { setStorageStatus("unavailable"); }
    setStorageReady(true);
  // The role guard mounts this workspace only for the Admin preview role.
  // Changing presentation language should not reload state or overwrite edits.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canAdmin]);
  useEffect(() => {
    if (!canAdmin || !storageReady) return;
    try { localStorage.setItem(ADMIN_STORAGE_KEY, serializeAdminState(state)); setStorageStatus("saved"); }
    catch { setStorageStatus("unavailable"); }
  }, [state, storageReady, canAdmin]);
  useEffect(() => {
    const previous = previousCommittedConfig.current;
    setConfigDraft((draft) => reconcileAdminConfigDraft(draft, previous, state.config));
    previousCommittedConfig.current = state.config;
  }, [state.config]);
  const configDirty = !sameAdminConfig(configDraft, state.config);
  const label = (status: string) => statusLabels[status] ? translated(statusLabels[status], locale) : status;
  const go = (value: AdminSection) => { if (document.activeElement?.getAttribute("role") !== "tab") requestAnimationFrame(() => document.getElementById("admin-panel")?.focus()); setSection(value); setError(""); setNotice(""); };
  function commit(action: AdminAction) {
    try {
      const next = applyAdminAction(state, action, canAdmin);
      const previous = action.type === "feedback" ? feedback.find((entry) => entry.id === action.id) : undefined;
      setUndo({ state, feedback: previous ? { id: previous.id, status: previous.status } : undefined });
      setState(next);
      if (action.type === "feedback") onFeedbackStatus(action.id, action.status);
      setError(""); setNotice(t("Local simulation updated.", "ローカルのシミュレーションを更新しました。"));
      return true;
    } catch (caught) {
      setNotice(""); setError(caught instanceof AdminError ? translated(errors[caught.code], locale) : t("Could not update the local preview.", "ローカルプレビューを更新できませんでした。")); return false;
    }
  }
  function undoChange() {
    if (!undo) return;
    const restored = structuredClone(undo.state);
    restored.sequence = state.sequence + 1;
    restored.audit = [{ id: `demo-audit-${restored.sequence}`, createdAt: Date.now(), action: "preview.undo", target: "last-change", detail: "Previous local values restored." }, ...state.audit];
    setState(restored);
    if (undo.feedback) onFeedbackStatus(undo.feedback.id, undo.feedback.status);
    setUndo(undefined); setError(""); setNotice(t("Previous local values restored.", "以前のローカル設定に戻しました。"));
  }
  function saveConfig() {
    if (!configDirty) { setError(""); setNotice(t("Preview settings are already saved.", "プレビュー設定は保存済みです。")); return; }
    if (commit({ type: "config", config: configDraft })) setNotice(t("Preview settings saved.", "プレビュー設定を保存しました。"));
  }
  function discardConfig() {
    setConfigDraft({ ...state.config }); setError("");
    setNotice(t("Unsaved settings edits discarded.", "設定の未保存の編集を破棄しました。"));
  }
  function exportRows(columns: string[], rows: Record<string, unknown>[], filename: string) {
    const csv = adminCsv(columns, rows, canAdmin);
    const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `ocean-p00-${filename}.csv`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(t("Local preview CSV downloaded.", "ローカルプレビューのCSVをダウンロードしました。")); setError("");
  }
  function tabKeys(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = ["ArrowRight", "ArrowDown"].includes(event.key) ? (index + 1) % sectionOrder.length : ["ArrowLeft", "ArrowUp"].includes(event.key) ? (index + sectionOrder.length - 1) % sectionOrder.length : event.key === "Home" ? 0 : event.key === "End" ? sectionOrder.length - 1 : -1;
    if (next < 0) return;
    event.preventDefault(); go(sectionOrder[next]); document.getElementById(`admin-tab-${sectionOrder[next]}`)?.focus();
  }
  const users = state.users.filter((user) => `${user.name} ${user.email} ${user.role} ${user.accountType}`.toLowerCase().includes(userSearch.toLowerCase()));
  const responses = feedback.filter((entry) => (!feedbackFilter || entry.status === feedbackFilter) && (!feedbackCategory || entry.category === feedbackCategory) && (!feedbackRating || entry.rating === feedbackRating) && `${entry.message} ${entry.reason ?? ""} ${entry.investigationId ?? ""} ${entry.runId ?? ""}`.toLowerCase().includes(feedbackSearch.toLowerCase()));
  const response = responses.find((entry) => entry.id === selectedFeedback) ?? responses[0];
  const tables = databaseInventory(state, feedback);
  const database = tables.find((table) => table.id === tableId)!;
  const records = database.rows.filter((row) => Object.values(row).join(" ").toLowerCase().includes(databaseSearch.toLowerCase()));
  const pageCount = Math.max(1, Math.ceil(records.length / 8));
  const page = Math.min(databasePage, pageCount);
  const rows = records.slice((page - 1) * 8, page * 8);
  const inspected = records.find((row) => row.id === selectedRow) ?? rows[0];
  const audit = state.audit.filter((event) => `${event.action} ${event.target} ${event.detail}`.toLowerCase().includes(auditSearch.toLowerCase()));
  const download = (onClick: () => void, disabled = false) => <button type="button" className="button secondary" onClick={onClick} disabled={disabled}><Download size={14} aria-hidden="true" />{t("Export CSV", "CSV出力")}</button>;
  const badge = (status: string) => <span className={`admin-status admin-status-${status}`}>{label(status)}</span>;
  const feedbackExport = () => exportRows(["id", "category", "rating", "reason", "status", "message", "investigationId", "runId", "createdAt"], responses.map((entry) => ({ ...entry, createdAt: new Date(entry.createdAt).toISOString() })), "feedback");

  return <section className="admin-view">
    <header className="admin-header"><div><div className="eyebrow">OCEAN / {t("ADMIN", "管理")}</div><h1>{t("Administration", "管理ダッシュボード")}</h1></div><div className="admin-header-meta"><span className="admin-simulation"><ShieldCheck size={14} aria-hidden="true" />{t("Local simulation", "ローカルのシミュレーション")}</span><span className="admin-storage" role="status">{storageStatus === "saved" ? t("Saved in this browser", "このブラウザーに保存") : storageStatus === "unavailable" ? t("Local save unavailable · session only", "ローカル保存不可・このセッションのみ") : t("Loading local demo", "ローカルサンプルを読み込み中")}</span></div></header>
    <div className="admin-layout">
      <div className="admin-navigation" role="tablist" aria-label={t("Administration areas", "管理メニュー")}>
        {sectionOrder.map((value, index) => { const Icon = sectionIcons[value]; return <button key={value} id={`admin-tab-${value}`} role="tab" aria-selected={section === value} aria-controls="admin-panel" tabIndex={section === value ? 0 : -1} onClick={() => go(value)} onKeyDown={(event) => tabKeys(event, index)}><Icon size={16} strokeWidth={1.6} aria-hidden="true" /><span>{translated(sectionLabels[value], locale)}</span>{value === "feedback" && feedback.some((entry) => entry.status === "new") && <span className="admin-count">{feedback.filter((entry) => entry.status === "new").length}</span>}</button>; })}
      </div>
      <div className="admin-content" role="tabpanel" id="admin-panel" aria-labelledby={`admin-tab-${section}`} tabIndex={0}>
        <div className="admin-section-heading"><h2>{translated(sectionLabels[section], locale)}</h2>{undo && <button className="text-button" onClick={undoChange}><RotateCcw size={13} aria-hidden="true" />{t("Undo last change", "最後の変更を戻す")}</button>}</div>
        <p className="admin-boundary">{t("Sample records. Changes stay in this preview; no email, worker or production access.", "サンプル記録。変更はこのプレビュー内のみ。メール送信・ワーカー・本番接続はありません。")}</p>
        {error && <p className="admin-notice danger" role="alert">{error}</p>}{notice && <p className="admin-notice" role="status"><Check size={14} aria-hidden="true" />{notice}</p>}

        {section === "overview" && <>
          <div className="admin-metrics">{[
            { title: t("Active accounts", "有効なアカウント"), value: state.users.filter((user) => user.status === "active").length, target: "users" as const },
            { title: t("Pending invitations", "有効な招待"), value: state.invitations.filter((invite) => invite.status === "pending").length, target: "users" as const },
            { title: t("New feedback", "新着フィードバック"), value: feedback.filter((entry) => entry.status === "new").length, target: "feedback" as const },
            { title: t("Snapshots", "スナップショット"), value: snapshots.length, target: "catalogue" as const },
          ].map((metric) => <button key={metric.title} onClick={() => go(metric.target)}><span>{metric.title}</span><strong>{metric.value}</strong><ArrowRight size={16} aria-hidden="true" /></button>)}</div>
          <div className="admin-overview-grid">{sectionOrder.slice(1).map((value) => { const Icon = sectionIcons[value]; return <button className="admin-area-card" key={value} onClick={() => go(value)}><Icon size={19} strokeWidth={1.6} aria-hidden="true" /><span>{translated(sectionLabels[value], locale)}</span><ArrowRight size={15} aria-hidden="true" /></button>; })}</div>
          <Panel title={t("Needs attention", "確認が必要な項目")}><div className="admin-attention"><button onClick={() => go("catalogue")}><span>ctd-2021</span><span className="muted">{t("Excluded from latest snapshot", "最新スナップショットから除外")}</span><ArrowRight size={14} aria-hidden="true" /></button></div></Panel>
        </>}

        {section === "users" && <>
          <Panel title={t("Create demo invitation", "サンプル招待を作成")}><form className="admin-invite-form" onSubmit={(event) => { event.preventDefault(); if (commit({ type: "invite", email, role: inviteRole, accountType: inviteAccount })) { setEmail(""); setNotice(t("Demo invitation created. No email sent.", "サンプル招待を作成しました。メールは送信されません。")); } }}><label><span>{t("Synthetic email", "架空のメールアドレス")}</span><input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="reviewer@ocean.example" aria-describedby="admin-invite-help" /></label><label><span>{t("Role", "ロール")}</span><select value={inviteRole} onChange={(event) => setInviteRole(event.target.value as AdminRole)}>{Object.entries(roleLabels).map(([value, text]) => <option key={value} value={value}>{translated(text, locale)}</option>)}</select></label><label><span>{t("Account type", "アカウント種別")}</span><select value={inviteAccount} onChange={(event) => setInviteAccount(event.target.value as AccountType)}>{Object.entries(accountLabels).map(([value, text]) => <option key={value} value={value}>{translated(text, locale)}</option>)}</select></label><button type="submit" className="button primary"><UserPlus size={15} aria-hidden="true" />{t("Create", "作成")}</button></form><p id="admin-invite-help" className="admin-help">.example / .test · {t("7-day demo expiry", "サンプルの期限は7日間")}</p></Panel>
          <Panel title={t("Accounts", "アカウント")} actions={download(() => exportRows(["id", "name", "email", "role", "accountType", "status", "lastSeen"], users, "accounts"))}><SearchField label={t("Find an account", "アカウントを検索")} value={userSearch} setValue={setUserSearch} /><div className="table-scroll" tabIndex={0}><table><caption className="sr-only">{t("Synthetic accounts", "サンプルアカウント")}</caption><thead><tr>{[t("Account", "アカウント"), t("Role", "ロール"), t("Type", "種別"), t("Status", "状態"), t("Last seen", "最終アクセス")].map((heading) => <th key={heading} scope="col">{heading}</th>)}</tr></thead><tbody>{users.map((user) => <tr key={user.id}><td><strong>{user.name}</strong><small>{user.email}</small></td><td>{user.id === "demo-admin" ? translated(roleLabels[user.role], locale) : <select aria-label={`${t("Role for", "ロール：")} ${user.name}`} value={user.role} onChange={(event) => commit({ type: "user", id: user.id, changes: { role: event.target.value as AdminRole } })}>{Object.entries(roleLabels).map(([value, text]) => <option key={value} value={value}>{translated(text, locale)}</option>)}</select>}</td><td>{user.id === "demo-admin" ? translated(accountLabels[user.accountType], locale) : <select aria-label={`${t("Account type for", "アカウント種別：")} ${user.name}`} value={user.accountType} onChange={(event) => commit({ type: "user", id: user.id, changes: { accountType: event.target.value as AccountType } })}>{Object.entries(accountLabels).map(([value, text]) => <option key={value} value={value}>{translated(text, locale)}</option>)}</select>}</td><td>{user.id === "demo-admin" ? badge(user.status) : <select aria-label={`${t("Status for", "状態：")} ${user.name}`} value={user.status} onChange={(event) => commit({ type: "user", id: user.id, changes: { status: event.target.value as "active" | "suspended" } })}><option value="active">{label("active")}</option><option value="suspended">{label("suspended")}</option></select>}</td><td>{user.lastSeen}</td></tr>)}{!users.length && <tr><td colSpan={5}>{t("No matching accounts.", "一致するアカウントはありません。")}</td></tr>}</tbody></table></div><p className="admin-help">{t("Role sets permissions. Account type describes usage. The preview administrator stays active.", "ロールは権限、アカウント種別は用途を表します。プレビュー管理者は有効のままです。")}</p></Panel>
          <Panel title={t("Invitations", "招待")}><div className="table-scroll" tabIndex={0}><table><thead><tr>{[t("Email", "メール"), t("Role / type", "ロール・種別"), t("Status", "状態"), t("Expires · JST", "期限・日本時間"), t("Action", "操作")].map((heading) => <th key={heading} scope="col">{heading}</th>)}</tr></thead><tbody>{state.invitations.map((invite) => <tr key={invite.id}><td>{invite.email}</td><td>{translated(roleLabels[invite.role], locale)}<small>{translated(accountLabels[invite.accountType], locale)}</small></td><td>{badge(invite.status === "pending" && invite.expiresAt < Date.now() ? "expired" : invite.status)}</td><td>{date(invite.expiresAt, locale)}</td><td>{invite.status === "pending" && invite.expiresAt > Date.now() ? <button className="text-button" aria-label={`${t("Revoke invitation for", "招待を取消：")} ${invite.email}`} onClick={() => commit({ type: "invitation", id: invite.id, status: "revoked" })}>{t("Revoke", "取消")}</button> : "—"}</td></tr>)}</tbody></table></div></Panel>
        </>}

        {section === "feedback" && <>
          <div className="admin-filters"><SearchField label={t("Find feedback", "フィードバックを検索")} value={feedbackSearch} setValue={setFeedbackSearch} /><label><span>{t("Status", "状態")}</span><select value={feedbackFilter} onChange={(event) => setFeedbackFilter(event.target.value)}><option value="">{t("All statuses", "すべての状態")}</option>{["new", "reviewing", "resolved"].map((value) => <option value={value} key={value}>{label(value)}</option>)}</select></label><label><span>{t("Category", "分類")}</span><select value={feedbackCategory} onChange={(event) => setFeedbackCategory(event.target.value)}><option value="">{t("All categories", "すべての分類")}</option>{["issue", "idea", "answer"].map((value) => <option value={value} key={value}>{label(value)}</option>)}</select></label><label><span>{t("Rating", "評価")}</span><select value={feedbackRating} onChange={(event) => setFeedbackRating(event.target.value)}><option value="">{t("All ratings", "すべての評価")}</option>{["helpful", "unhelpful"].map((value) => <option value={value} key={value}>{label(value)}</option>)}</select></label></div>
          <div className="admin-split"><Panel title={`${t("Responses", "投稿")} · ${responses.length}`} actions={download(feedbackExport, !responses.length)}><div className="admin-feedback-list">{responses.map((entry) => <button key={entry.id} aria-pressed={response?.id === entry.id} onClick={() => setSelectedFeedback(entry.id)}><div>{badge(entry.category)}{badge(entry.status)}</div><strong>{entry.message || label(entry.rating ?? entry.category)}</strong><small>{date(entry.createdAt, locale)} · JST</small></button>)}{!responses.length && <p className="admin-empty">{t("No feedback in this view. Use Feedback in the app to add a local response.", "該当する投稿はありません。アプリのフィードバックからローカル投稿を追加できます。")}</p>}</div></Panel><Panel title={t("Review detail", "投稿の詳細")}>{response ? <><div className="admin-detail-meta">{badge(response.category)}{response.rating && badge(response.rating)}</div><p className="admin-feedback-message">{response.message || t("Rating only", "評価のみ")}</p><dl className="admin-definition">{response.reason && <><dt>{t("Reason", "理由")}</dt><dd>{response.reason}</dd></>}<dt>{t("Submitted · JST", "投稿・日本時間")}</dt><dd>{date(response.createdAt, locale)}</dd>{response.investigationId && <><dt>{t("Investigation", "調査")}</dt><dd>{response.investigationId}</dd></>}{response.runId && <><dt>{t("Run", "実行")}</dt><dd>{response.runId}</dd></>}</dl><label className="admin-field"><span>{t("Review status", "対応状況")}</span><select value={response.status} onChange={(event) => commit({ type: "feedback", id: response.id, status: event.target.value as FeedbackEntry["status"] })}>{["new", "reviewing", "resolved"].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label><p className="admin-help">{t("Triage does not change the answer or its scientific authority.", "対応状況は回答や科学的権威を変更しません。")}</p></> : <p className="admin-empty">{t("Select a response.", "投稿を選択してください。")}</p>}</Panel></div>
        </>}

        {section === "database" && <>
          <p className="admin-help">{t("Local fixture collections. Record counts are not physical sample counts.", "ローカルのサンプルコレクション。記録件数は物理的な試料数ではありません。")}</p>
          <div className="admin-database-layout"><div className="admin-table-menu">{tables.map((table) => <button key={table.id} aria-pressed={table.id === tableId} onClick={() => { setTableId(table.id); setDatabaseSearch(""); setDatabasePage(1); setSelectedRow(""); }}><Database size={14} aria-hidden="true" /><span>{table.id}</span><small>{table.rows.length}</small></button>)}</div><Panel title={database.id} actions={download(() => exportRows(database.columns, records, tableId), !records.length)}><SearchField label={t("Find a record", "記録を検索")} value={databaseSearch} setValue={(value) => { setDatabaseSearch(value); setDatabasePage(1); }} /><div className="table-scroll" tabIndex={0}><table><thead><tr>{database.columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={String(row.id)} className={inspected?.id === row.id ? "admin-selected-row" : ""}>{database.columns.map((column, index) => <td key={column}>{index === 0 ? <button className="text-button" aria-pressed={inspected?.id === row.id} onClick={() => setSelectedRow(String(row.id))}>{String(row[column])}</button> : String(row[column])}</td>)}</tr>)}{!rows.length && <tr><td colSpan={database.columns.length}>{t("No matching records.", "一致する記録はありません。")}</td></tr>}</tbody></table></div><div className="admin-pagination"><button className="icon-button" aria-label={t("Previous page", "前のページ")} disabled={page <= 1} onClick={() => setDatabasePage(page - 1)}><ChevronLeft size={18} /></button><span>{records.length ? `${(page - 1) * 8 + 1}–${Math.min(page * 8, records.length)}` : "0"} / {records.length}</span><button className="icon-button" aria-label={t("Next page", "次のページ")} disabled={page >= pageCount} onClick={() => setDatabasePage(page + 1)}><ChevronRight size={18} /></button></div><details className="admin-diagnostics"><summary>{t("Selected record", "選択された記録")}</summary><pre>{JSON.stringify(inspected ?? {}, null, 2)}</pre></details><details className="admin-diagnostics"><summary>{t("Provisional fields", "暫定フィールド")}</summary><pre>{JSON.stringify(database.columns, null, 2)}</pre></details></Panel></div>
        </>}

        {section === "catalogue" && <>
          <Panel title={t("Snapshot inventory", "スナップショットの一覧")} actions={download(() => exportRows(["id", "date", "datasets", "excluded"], snapshots.map((snapshot) => ({ id: snapshot.id, date: snapshot.date, datasets: catalogue.filter((node) => node.kind === "dataset" && !snapshot.excludedIds.includes(node.id)).length, excluded: snapshot.excludedIds.join("; ") })), "snapshots"))}><div className="table-scroll" tabIndex={0}><table><thead><tr>{[t("Snapshot", "スナップショット"), t("Date", "日付"), t("Dataset records", "データセット記録"), t("Excluded records", "除外された記録")].map((heading) => <th key={heading} scope="col">{heading}</th>)}</tr></thead><tbody>{snapshots.map((snapshot) => <tr key={snapshot.id}><td><strong>{snapshot.id}</strong>{snapshot.id === "sample-02" && <small>{t("Latest demo", "最新サンプル")}</small>}</td><td>{snapshot.date}</td><td>{catalogue.filter((node) => node.kind === "dataset" && !snapshot.excludedIds.includes(node.id)).length}</td><td>{snapshot.excludedIds.join(", ")}</td></tr>)}</tbody></table></div></Panel>
          <div className="admin-split"><Panel title={t("Scientific authority", "科学的な権威")}> <dl className="admin-definition"><dt>{t("Inventory", "一覧")}</dt><dd>{t("Descriptive counts", "記述的な件数")}</dd><dt>{t("Published references", "公開資料")}</dt><dd>{t("Publication does not imply scientific approval", "公開は科学的承認を意味しません")}</dd><dt>{t("Experimental results", "実験結果")}</dt><dd>{t("Remain experimental", "実験的な状態を維持")}</dd><dt>{t("Matching links", "対応付けリンク")}</dt><dd>{t("Candidates until verified", "検証までは候補")}</dd></dl></Panel><Panel title={t("Retention preview", "保持ルールのプレビュー")}><dl className="admin-definition"><dt>{t("Demo policy", "サンプル方針")}</dt><dd>{state.config.retentionDays} {t("days", "日")}</dd><dt>{t("Referenced evidence", "参照された証拠")}</dt><dd>{t("Protected while retained", "保持中は保護")}</dd><dt>ctd-2021</dt><dd>{t("Retained in sample-01; absent from sample-02", "sample-01に保持。sample-02には含まれません")}</dd><dt>{t("Withdrawal", "撤回")}</dt><dd>{t("Access revalidation required", "アクセスの再検証が必要")}</dd></dl><button className="text-button" onClick={() => go("system")}>{t("Edit demo policy", "サンプル方針を編集")}<ArrowRight size={13} /></button><p className="admin-help">{t("Informational preview. No records are deleted or permissions changed.", "説明用のプレビュー。記録の削除や権限の変更は行われません。")}</p></Panel></div>
        </>}

        {section === "system" && <>
          <Panel title={t("Connection status", "接続状態")} actions={<button className="button secondary" onClick={() => commit({ type: "check" })}><Activity size={14} aria-hidden="true" />{t("Record demo check", "サンプル確認を記録")}</button>}><div className="admin-health">{[[t("Fixture adapter", "サンプルアダプター"), t("Local", "ローカル")], [t("Backend / database", "バックエンド・DB"), t("Disconnected", "未接続")], [t("Model runtime", "モデル実行環境"), t("Disabled", "無効")], [t("Authentication", "認証"), t("Role simulation", "ロールのシミュレーション")], [t("Cloud services", "クラウドサービス"), t("Disconnected", "未接続")]].map(([title, value]) => <div key={title}><span>{title}</span><strong>{value}</strong></div>)}</div></Panel>
          <Panel title={t("Preview settings", "プレビュー設定")} actions={<span className={`admin-draft-status${configDirty ? " dirty" : ""}`} role="status">{configDirty ? t("Unsaved changes", "未保存の変更") : t("Saved values", "保存済みの設定")}</span>}><form onSubmit={(event) => { event.preventDefault(); saveConfig(); }}><div className="admin-config-grid">{[
            { key: "retentionDays" as const, title: t("Retention preview", "保持ルールのプレビュー"), min: 7, max: 365, unit: t("7–365 days · no deletion", "7〜365日・削除なし") },
            { key: "timeoutSeconds" as const, title: t("Run time budget", "実行時間の上限"), min: 30, max: 180, unit: t("30–180 seconds · illustrative", "30〜180秒・説明用") },
            { key: "maxActions" as const, title: t("Run action budget", "実行アクション上限"), min: 1, max: 12, unit: t("1–12 actions · illustrative", "1〜12回・説明用") },
          ].map((field) => <label key={field.key}><span>{field.title}</span><input type="number" min={field.min} max={field.max} step={1} required value={configDraft[field.key]} onChange={(event) => setConfigDraft({ ...configDraft, [field.key]: Number(event.target.value) })} /><small>{field.unit}</small></label>)}</div><div className="admin-form-actions"><button className="button secondary" type="button" onClick={discardConfig}>{t("Discard edits", "編集を破棄")}</button><button className="button primary" type="submit">{t("Save preview settings", "プレビュー設定を保存")}</button></div><p className="admin-help">{t("These values preview future controls; no records are deleted or execution limits enforced.", "将来の制御を示すプレビューです。記録の削除や実行制限の適用は行いません。")}</p></form></Panel>
        </>}

        {section === "audit" && <>
          <Panel title={t("Local audit events", "ローカルの監査イベント")} actions={download(() => exportRows(["id", "createdAt", "action", "target", "detail"], audit.map((event) => ({ ...event, createdAt: new Date(event.createdAt).toISOString() })), "audit"))}><SearchField label={t("Find an event", "イベントを検索")} value={auditSearch} setValue={setAuditSearch} /><div className="table-scroll" tabIndex={0}><table><thead><tr>{[t("Time · JST", "時間・日本時間"), t("Action", "操作"), t("Target", "対象"), t("Detail", "詳細")].map((heading) => <th key={heading} scope="col">{heading}</th>)}</tr></thead><tbody>{audit.map((event) => <tr key={event.id}><td>{date(event.createdAt, locale)}</td><td><code>{event.action}</code></td><td>{event.target}</td><td>{event.detail}</td></tr>)}{!audit.length && <tr><td colSpan={4}>{t("No matching events.", "一致するイベントはありません。")}</td></tr>}</tbody></table></div></Panel>
          <Panel title={t("Preview diagnostics", "プレビューの診断")}><details className="admin-diagnostics"><summary>{t("Adapter & execution boundary", "アダプターと実行境界")}</summary><pre>{JSON.stringify({ mode: "P00-local-synthetic", transport: "fixture-only", realAuth: false, backendConnected: false, modelCalls: false, workerExecution: false, publicationWrites: false, snapshot: "sample-02", config: state.config }, null, 2)}</pre></details><p className="admin-help">{t("Demo audit is saved in this browser. It is not a security audit log.", "サンプル監査はこのブラウザーに保存。セキュリティ監査ログではありません。")}</p></Panel>
        </>}
      </div>
    </div>
  </section>;
}

function Panel({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return <article className="admin-panel"><header><h3>{title}</h3>{actions}</header>{children}</article>;
}
function SearchField({ label, value, setValue }: { label: string; value: string; setValue: (value: string) => void }) {
  return <label className="admin-search"><span className="sr-only">{label}</span><input type="search" placeholder={label} value={value} onChange={(event) => setValue(event.target.value)} /></label>;
}
