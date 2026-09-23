import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Disc3, LockKeyhole, Plus, Sparkles, Users } from "lucide-react";
import { apiGet, apiPost } from "../lib/api";
import { TrackCard } from "../components/TrackCard";
import type { PlaylistSummary } from "../types";

export function PlaylistsPage() {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const client = useQueryClient();
  const playlists = useQuery({ queryKey: ["playlists"], queryFn: () => apiGet<PlaylistSummary[]>("/playlists") });
  const create = useMutation({ mutationFn: (title: string) => apiPost<PlaylistSummary>("/playlists", { name: title, is_public: false }),
    onSuccess: async () => { setName(""); await client.invalidateQueries({ queryKey: ["playlists"] }); },
    onError: (reason: Error) => setError(reason.message) });

  function submit(event: FormEvent) { event.preventDefault(); if (name.trim()) { setError(""); create.mutate(name.trim()); } }

  return (
    <div className="dashboard-page playlist-page">
      <div className="page-title-row"><div><div className="section-kicker"><Disc3 size={13} /> YOUR COLLECTION</div><h1>Playlists</h1><p className="muted">Keep your discoveries close. Vibe playlists are saved here automatically.</p></div></div>
      <form className="create-playlist-form" onSubmit={submit}><div className="create-playlist-icon"><Plus size={18} /></div><div className="create-playlist-copy"><strong>Make a playlist</strong><span>Start with a name; add tracks from Discover.</span></div><input aria-label="Playlist name" maxLength={180} value={name} onChange={(event) => setName(event.target.value)} placeholder="Name this playlist" /><button className="primary-button" disabled={!name.trim() || create.isPending}>Create playlist</button></form>
      {error && <p className="form-error" role="alert">{error}</p>}
      {playlists.isLoading ? <div className="loading-view"><span className="spinner" />Loading playlists…</div> : playlists.isError ? <div className="empty-state"><h3>Your playlists didn’t load</h3><p>{playlists.error.message}</p></div> : playlists.data?.length ? <div className="playlist-stack">
        {playlists.data.map((playlist) => {
          const queue = playlist.songs.map((item) => item.song);
          return <article className="playlist-panel" key={playlist.id}>
            <div className="playlist-panel-head"><div className="playlist-cover"><Disc3 size={28} /><i /></div><div className="playlist-metadata"><div className="section-kicker">{playlist.generation_type === "vibe" ? <><Sparkles size={12} /> GENERATED FROM A VIBE</> : playlist.generation_type === "weekly" ? <><Sparkles size={12} /> THIS WEEK</> : "YOUR MIX"}</div><h2>{playlist.name}</h2><p>{playlist.original_prompt || `${playlist.songs.length} tracks`}</p></div><span className="visibility-pill">{playlist.is_public ? <><Users size={12} /> Public</> : <><LockKeyhole size={12} /> Private</>}</span></div>
            {playlist.songs.length ? <div className="track-grid">{playlist.songs.map((item) => <TrackCard key={item.song.id} song={item.song} queue={queue} score={item.relevance_score ?? undefined} playlistId={playlist.id} />)}</div> : <div className="playlist-empty"><p>This playlist is ready for a few tracks.</p><a href="/">Explore the catalog</a></div>}
          </article>;
        })}
      </div> : <div className="empty-state"><div className="empty-icon"><Disc3 size={23} /></div><h3>Your first playlist is one feeling away</h3><p>Generate a vibe playlist on Discover or create a playlist above and add real catalog tracks.</p></div>}
    </div>
  );
}
