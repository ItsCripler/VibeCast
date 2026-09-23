import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Building2, Music2, Users } from "lucide-react";
import { apiGet } from "../lib/api";

type Label = { id: string; name: string };
type LabelArtist = { artist_profile_id: string; stage_name: string; user_id: string; name: string; email: string };
type Performance = { artist_profile_id: string; artist_name: string; song_id: string; title: string; qualified_plays: number; listening_seconds: number };

export function LabelPage() {
  const [labelId, setLabelId] = useState("");
  const labels = useQuery({ queryKey: ["my-labels"], queryFn: () => apiGet<Label[]>("/labels/me") });
  useEffect(() => { if (!labelId && labels.data?.length) setLabelId(labels.data[0].id); }, [labelId, labels.data]);
  const artists = useQuery({ queryKey: ["label-artists", labelId], queryFn: () => apiGet<LabelArtist[]>(`/labels/${labelId}/artists`), enabled: Boolean(labelId) });
  const performance = useQuery({ queryKey: ["label-performance", labelId], queryFn: () => apiGet<Performance[]>(`/labels/${labelId}/performance?days=30`), enabled: Boolean(labelId) });
  const totalPlays = performance.data?.reduce((sum, row) => sum + row.qualified_plays, 0) || 0;
  const totalSeconds = performance.data?.reduce((sum, row) => sum + row.listening_seconds, 0) || 0;

  return (
    <div className="dashboard-page">
      <div className="page-title-row"><div><div className="section-kicker"><Building2 size={13} /> LABEL WORKSPACE</div><h1>Label overview</h1><p className="muted">Aggregate response for artists and tracks assigned to your label.</p></div>
        {labels.data && labels.data.length > 1 && <select aria-label="Choose label" value={labelId} onChange={(event) => setLabelId(event.target.value)}>{labels.data.map((label) => <option key={label.id} value={label.id}>{label.name}</option>)}</select>}
      </div>
      {labels.isLoading ? <div className="loading-view"><span className="spinner" />Loading label access…</div> : labels.isError ? <div className="empty-state"><h3>Label data unavailable</h3><p>{labels.error.message}</p></div> : !labels.data?.length ? <div className="empty-state"><div className="empty-icon"><Building2 size={23} /></div><h3>No label is assigned</h3><p>A platform administrator can create a label and attach your account.</p></div> : <>
        <div className="metric-grid label-metrics"><article className="metric-card"><span className="metric-icon violet"><Users size={18} /></span><span className="metric-label">AUTHORIZED ARTISTS</span><strong>{artists.data?.length ?? 0}</strong><small>Assigned to this label</small></article><article className="metric-card"><span className="metric-icon mint"><BarChart3 size={18} /></span><span className="metric-label">QUALIFIED PLAYS</span><strong>{totalPlays.toLocaleString()}</strong><small>Aggregated, no listener identities</small></article><article className="metric-card"><span className="metric-icon blue"><Music2 size={18} /></span><span className="metric-label">LISTENING TIME</span><strong>{Math.floor(totalSeconds / 3600)}h {Math.floor((totalSeconds % 3600) / 60)}m</strong><small>Across assigned artist uploads</small></article></div>
        <section className="panel"><div className="panel-heading"><div><span className="section-kicker">AUTHORIZED ROSTER</span><h2>Artists</h2></div></div>
          {artists.isLoading ? <div className="loading-inline"><span className="spinner" />Loading artists…</div> : artists.data?.length ? <div className="label-roster">{artists.data.map((artist) => <article key={artist.artist_profile_id}><span className="avatar">{artist.stage_name.slice(0, 1).toUpperCase()}</span><span><strong>{artist.stage_name}</strong><small>{artist.email}</small></span><span className="roster-role">Artist</span></article>)}</div> : <p className="panel-empty">No artist profiles are assigned yet.</p>}
        </section>
        <section className="panel performance-panel"><div className="panel-heading"><div><span className="section-kicker">PAST 30 DAYS</span><h2>Track performance</h2></div></div>
          {performance.isLoading ? <div className="loading-inline"><span className="spinner" />Loading performance…</div> : performance.data?.length ? <div className="performance-table"><div className="performance-header"><span>ARTIST / TRACK</span><span>QUALIFIED PLAYS</span><span>LISTENING TIME</span><span>RESPONSE</span></div>{performance.data.map((row) => <div className="performance-row" key={row.song_id}><strong><small>{row.artist_name}</small>{row.title}</strong><span>{row.qualified_plays.toLocaleString()}</span><span>{Math.floor(row.listening_seconds / 60)} min</span><span className="response-bar"><i style={{ width: `${Math.max(5, Math.min(100, (row.qualified_plays / Math.max(1, ...performance.data!.map((item) => item.qualified_plays))) * 100))}%` }} /></span></div>)}</div> : <p className="panel-empty">No qualified plays from this roster in the selected window.</p>}
        </section>
      </>}
    </div>
  );
}
