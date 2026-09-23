import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Database, Play, RefreshCw, Shield, Users } from "lucide-react";
import { apiGet, apiPatch, apiPost } from "../lib/api";
import type { User } from "../types";

type ConfigStatus = { jamendo_configured: boolean; google_oauth_configured: boolean; embedding_model: string; max_sync_tracks: number; page_size: number };
type SyncStatus = { runs: { id: string; status: string; tracks_seen: number; tracks_upserted: number; pages_fetched: number; error_summary: string | null; started_at: string; finished_at: string | null }[]; jobs: { id: string; status: string; attempts: number; last_error: string | null }[] };
type AdminJob = { id: string; kind: string; status: string; attempts: number; payload: Record<string, unknown>; last_error: string | null; created_at: string };
type Label = { id: string; name: string };

export function AdminPage() {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"artist" | "label_admin" | "platform_admin">("artist");
  const [labelId, setLabelId] = useState("");
  const [labelName, setLabelName] = useState("");
  const [message, setMessage] = useState("");

  const config = useQuery({ queryKey: ["admin-config"], queryFn: () => apiGet<ConfigStatus>("/admin/config/status") });
  const syncStatus = useQuery({ queryKey: ["sync-status"], queryFn: () => apiGet<SyncStatus>("/admin/catalog/sync/status"), refetchInterval: 5_000 });
  const jobs = useQuery({ queryKey: ["admin-jobs"], queryFn: () => apiGet<AdminJob[]>("/admin/jobs?limit=100"), refetchInterval: 5_000 });
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => apiGet<User[]>("/admin/users?limit=100") });
  const labels = useQuery({ queryKey: ["my-labels"], queryFn: () => apiGet<Label[]>("/labels/me") });

  const sync = useMutation({ mutationFn: () => apiPost("/admin/catalog/sync?max_tracks=1000&page_size=100"),
    onSuccess: async () => { setMessage("Catalog sync queued."); await client.invalidateQueries({ queryKey: ["sync-status"] }); },
    onError: (error: Error) => setMessage(error.message) });
  const rebuildEmbeddings = useMutation({ mutationFn: () => apiPost<{ queued: number }>("/admin/catalog/embeddings/rebuild?limit=10000"),
    onSuccess: async (result) => { setMessage(`Queued ${result.queued} embedding jobs.`); await client.invalidateQueries({ queryKey: ["admin-jobs"] }); },
    onError: (error: Error) => setMessage(error.message) });
  const rebuildRecommender = useMutation({ mutationFn: () => apiPost("/admin/recommendations/rebuild"),
    onSuccess: async () => { setMessage("Recommendation model rebuild queued."); await client.invalidateQueries({ queryKey: ["admin-jobs"] }); },
    onError: (error: Error) => setMessage(error.message) });
  const retry = useMutation({ mutationFn: (id: string) => apiPost(`/admin/jobs/${id}/retry`), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["admin-jobs"] }); await client.invalidateQueries({ queryKey: ["sync-status"] }); } });
  const createUser = useMutation({ mutationFn: (body: object) => apiPost("/admin/users", body), onSuccess: async () => { setName(""); setEmail(""); setPassword(""); setMessage("Staff account created."); await client.invalidateQueries({ queryKey: ["admin-users"] }); }, onError: (error: Error) => setMessage(error.message) });
  const changeRole = useMutation({ mutationFn: ({ id, value }: { id: string; value: User["role"] }) => apiPatch(`/admin/users/${id}/role`, { role: value }), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["admin-users"] }); } });
  const createLabel = useMutation({ mutationFn: () => apiPost("/admin/labels", { name: labelName }), onSuccess: async () => { setLabelName(""); setMessage("Label created."); await client.invalidateQueries({ queryKey: ["my-labels"] }); }, onError: (error: Error) => setMessage(error.message) });

  function submitUser(event: FormEvent) {
    event.preventDefault();
    const body: Record<string, unknown> = { name, email, password, role };
    if (role === "artist" && labelId) body.label_id = labelId;
    if (role === "label_admin" && labelId) body.label_id = labelId;
    createUser.mutate(body);
  }

  const latestRun = syncStatus.data?.runs[0];

  return (
    <div className="dashboard-page admin-page">
      <div className="page-title-row"><div><div className="section-kicker"><Shield size={13} /> PLATFORM CONTROL</div><h1>Admin console</h1><p className="muted">Safe catalog, account, and background-job controls.</p></div><span className="period-pill admin-pill">PRIVILEGED ACCESS</span></div>
      <section className="panel admin-catalog-panel"><div className="panel-heading"><div><span className="section-kicker">EXTERNAL CATALOG</span><h2>Jamendo synchronization</h2></div><span className="upload-mark"><Database size={18} /></span></div>
        <div className="admin-config-grid"><div className="config-row"><span>Jamendo client ID</span><strong className={config.data?.jamendo_configured ? "state-ready" : "state-missing"}>{config.data?.jamendo_configured ? <><CheckCircle2 size={14} /> Configured</> : <><AlertTriangle size={14} /> Missing</>}</strong></div><div className="config-row"><span>Google OAuth</span><strong className={config.data?.google_oauth_configured ? "state-ready" : "state-optional"}>{config.data?.google_oauth_configured ? "Configured" : "Optional · not configured"}</strong></div><div className="config-row"><span>Embedding model</span><strong className="config-value">{config.data?.embedding_model || "Loading…"}</strong></div></div>
        <div className="sync-actions"><div><strong>{latestRun ? `Last sync ${latestRun.status}` : "No synchronization run yet"}</strong><small>{latestRun ? `${latestRun.tracks_upserted} tracks upserted · ${latestRun.pages_fetched} pages · ${new Date(latestRun.started_at).toLocaleString()}` : "Syncing inserts provider records only; no fallback songs are bundled."}</small></div><button className="primary-button" disabled={sync.isPending || !config.data?.jamendo_configured} onClick={() => { setMessage(""); sync.mutate(); }}>{sync.isPending ? <RefreshCw className="spin" size={15} /> : <Play size={15} fill="currentColor" />} Start sync</button></div>
        {!config.data?.jamendo_configured && <p className="setup-hint">Set <code>VIBECAST_JAMENDO_CLIENT_ID</code> in your local environment and restart the stack. Track limits and page size can be changed in `.env`.</p>}
        {latestRun?.error_summary && <p className="form-error">{latestRun.error_summary}</p>}{message && <p className="form-success" role="status">{message}</p>}
      </section>

      <div className="admin-grid">
        <section className="panel"><div className="panel-heading"><div><span className="section-kicker">ACCOUNT ACCESS</span><h2>Create staff account</h2></div></div>
          <form className="admin-form" onSubmit={submitUser}><label>Name<input value={name} onChange={(event) => setName(event.target.value)} required /></label><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>Temporary password<input type="password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} required /></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value as typeof role)}><option value="artist">Artist</option><option value="label_admin">Label admin</option><option value="platform_admin">Platform admin</option></select></label>
            {labels.data?.length ? <label>Label assignment (optional)<select value={labelId} onChange={(event) => setLabelId(event.target.value)}><option value="">No label</option>{labels.data.map((label) => <option key={label.id} value={label.id}>{label.name}</option>)}</select></label> : null}
            <button className="secondary-button" disabled={createUser.isPending}>Create staff account <Users size={15} /></button></form>
          <form className="inline-create-label" onSubmit={(event) => { event.preventDefault(); if (labelName.trim()) createLabel.mutate(); }}><input value={labelName} onChange={(event) => setLabelName(event.target.value)} placeholder="New label name" aria-label="New label name" /><button aria-label="Create label" disabled={!labelName.trim()}>+</button></form>
        </section>
        <section className="panel jobs-panel"><div className="panel-heading"><div><span className="section-kicker">BACKGROUND WORK</span><h2>Recent jobs</h2></div><span className="job-refresh"><RefreshCw size={14} /></span></div>
          <div className="admin-maintenance-actions"><button className="secondary-button" disabled={rebuildEmbeddings.isPending} onClick={() => rebuildEmbeddings.mutate()}>Rebuild embeddings</button><button className="secondary-button" disabled={rebuildRecommender.isPending} onClick={() => rebuildRecommender.mutate()}>Retrain recommendations</button></div>
          {jobs.data?.length ? <div className="job-list">{jobs.data.slice(0, 12).map((job) => <article className="job-row" key={job.id}><span className={`job-dot job-${job.status}`} /><div><strong>{job.kind.replaceAll("_", " ")}</strong><small>{new Date(job.created_at).toLocaleString()} · {job.attempts} attempts</small>{job.last_error && <small className="job-error">{job.last_error}</small>}</div><span className={`job-status job-${job.status}`}>{job.status}</span>{["failed", "retry"].includes(job.status) && <button className="retry-button" onClick={() => retry.mutate(job.id)}>Retry</button>}</article>)}</div> : <p className="panel-empty">No background jobs have run yet.</p>}
        </section>
      </div>

      <section className="panel users-panel"><div className="panel-heading"><div><span className="section-kicker">ROLE-BASED ACCESS</span><h2>Users</h2></div><span className="user-count">{users.data?.length ?? 0} shown</span></div>
        {users.data?.length ? <div className="users-table"><div className="users-header"><span>ACCOUNT</span><span>CREATED</span><span>ROLE</span></div>{users.data.map((account) => <div className="users-row" key={account.id}><span className="admin-user-cell"><i>{account.name.slice(0, 1).toUpperCase()}</i><span><strong>{account.name}</strong><small>{account.email}</small></span></span><span>{new Date(account.created_at).toLocaleDateString()}</span><select aria-label={`Role for ${account.name}`} value={account.role} onChange={(event) => changeRole.mutate({ id: account.id, value: event.target.value as User["role"] })}><option value="listener">Listener</option><option value="artist">Artist</option><option value="label_admin">Label admin</option><option value="platform_admin">Platform admin</option></select></div>)}</div> : <p className="panel-empty">No users are registered.</p>}
      </section>
      <p className="admin-footnote">Catalog rows are Jamendo-sourced or first-party artist uploads. Sync failures and analysis retries are visible above; no arbitrary database console is exposed.</p>
    </div>
  );
}
