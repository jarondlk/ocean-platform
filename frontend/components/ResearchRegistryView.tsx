"use client";

import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import type { CurrentUser } from "@/types";

type Review = { review_id: string; registry_key: string; kind: "sampling" | "sst_product"; state: "draft" | "approved" | "rejected" | "applied"; version: number; content_sha256: string; definition?: Record<string, unknown>; events?: Record<string, unknown>[] };
type Preview = { status: string; stale_count?: number; limitations?: string[]; [key: string]: unknown };
const base = "/research-registry-reviews";

export function ResearchRegistryView() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Review | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [kind, setKind] = useState<Review["kind"]>("sampling");
  const [definition, setDefinition] = useState("");
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.all([request<CurrentUser>("/me"), request<{ items: Review[]; total: number }>(`${base}?limit=50&offset=${offset}`)])
      .then(([actor, catalog]) => { if (active) { setUser(actor); setReviews(catalog.items); setTotal(catalog.total); } })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [offset, refresh]);
  async function load(identity: string) {
    setSelected(null); setPreview(null); setRationale(""); setError("");
    if (!identity) return;
    setBusy(true);
    try { setSelected(await request<Review>(`${base}/${identity}`)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function action(path: string, body: unknown) {
    setBusy(true); setError("");
    try {
      const result = await request<Review & { preview?: Preview }>(path, { method: "POST", body: JSON.stringify(body) });
      if (result.preview) { setPreview(result.preview); }
      else { setSelected(await request<Review>(`${base}/${result.review_id}`)); setPreview(null); setRationale(""); setRefresh(v => v+1); }
    } catch (e) { setError((e as Error).message); setPreview(null); }
    finally { setBusy(false); }
  }
  const scientist = user?.role === "researcher" && user.permissions.includes("classification:decide");
  const administrator = user?.role === "admin" && user.permissions.includes("classification:apply");
  return <section aria-label="Research registry review" className="data-section">
    <h3>Sampling and SST reviews</h3>
    <p>Review sampling units, representative assays, area footprints and SST definitions against their cited evidence. Classification is a separate review. A researcher approves the science; an administrator applies the approved record.</p>
    {error ? <p role="alert" className="error-text">{error}</p> : null}
    <label className="control-label">Review
      <select className="field" value={selected?.review_id || ""} disabled={busy} onChange={e => void load(e.target.value)}>
        <option value="">Select a review</option>
        {selected && !reviews.some(r => r.review_id === selected.review_id) ? <option value={selected.review_id}>{selected.registry_key} · {selected.state}</option> : null}
        {reviews.map(r => <option key={r.review_id} value={r.review_id}>{r.registry_key} · {r.state} · v{r.version}</option>)}
      </select>
    </label>
    <p>{total} reviews</p>
    <div className="button-row">
      <button className="button secondary-button" type="button" disabled={busy || offset === 0} onClick={() => setOffset(v => Math.max(0, v-50))}>Previous</button>
      <button className="button secondary-button" type="button" disabled={busy || offset+50 >= total} onClick={() => setOffset(v => v+50)}>Next</button>
    </div>
    {selected ? <>
      <p>{selected.registry_key} · {selected.state} · v{selected.version}</p>
      <details open><summary>Definition and cited evidence</summary><pre className="json-view">{JSON.stringify(selected.definition, null, 2)}</pre></details>
      <button className="button secondary-button" type="button" disabled={busy} onClick={() => void action(`${base}/${selected.review_id}/preview`, {})}>Check current evidence</button>
      {preview ? <><p role="status">{preview.status.replaceAll("_", " ")}</p><pre className="json-view">{JSON.stringify(preview, null, 2)}</pre></> : null}
      {scientist && selected.state === "draft" ? <>
        <label className="control-label">Review rationale<textarea className="field" maxLength={4000} value={rationale} onChange={e => setRationale(e.target.value)} /></label>
        <div className="button-row">
          <button className="button" type="button" disabled={busy || !rationale.trim() || !preview || (preview.stale_count || 0) > 0} onClick={() => void action(`${base}/${selected.review_id}/decision`, { approve: true, version: selected.version, content_sha256: selected.content_sha256, rationale })}>Approve scientific definition</button>
          <button className="button secondary-button" type="button" disabled={busy || !rationale.trim()} onClick={() => void action(`${base}/${selected.review_id}/decision`, { approve: false, version: selected.version, content_sha256: selected.content_sha256, rationale })}>Reject definition</button>
        </div>
      </> : null}
      {administrator && selected.state === "approved" ? <button className="button" type="button" disabled={busy || !preview || (preview.stale_count || 0) > 0} onClick={() => void action(`${base}/${selected.review_id}/apply`, { version: selected.version, content_sha256: selected.content_sha256 })}>Apply approved registry</button> : null}
      <details><summary>Review history</summary><pre className="json-view">{JSON.stringify(selected.events, null, 2)}</pre></details>
    </> : null}
    {scientist ? <details><summary>Prepare a new review</summary>
      <label className="control-label">Definition type<select className="field" value={kind} onChange={e => setKind(e.target.value as Review["kind"])}><option value="sampling">Sampling identities and areas</option><option value="sst_product">SST product and quality rules</option></select></label>
      <p>Paste an evidence packet containing exact source bindings and cited decisions. Saving creates a draft for review. Browser requests are limited to 1 MiB, including the JSON envelope.</p>
      <label className="control-label">Definition JSON<textarea className="field" rows={12} maxLength={1048576} value={definition} onChange={e => setDefinition(e.target.value)} /></label>
      <button className="button secondary-button" type="button" disabled={busy || !definition.trim()} onClick={() => { try { const body = { kind, definition: JSON.parse(definition) }; if (new TextEncoder().encode(JSON.stringify(body)).length > 1048576) { setError("The review packet exceeds the 1 MiB browser request limit."); return; } void action(base, body); } catch { setError("Enter a valid JSON definition."); } }}>Save review draft</button>
    </details> : null}
    {busy ? <p role="status">Loading review…</p> : null}
  </section>;
}
