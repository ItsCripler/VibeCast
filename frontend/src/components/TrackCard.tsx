import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Disc3, ExternalLink, Play, X } from "lucide-react";
import { useAuth } from "../features/auth/AuthContext";
import { usePlayer } from "../features/player/PlayerContext";
import { apiGet, apiPost, apiDelete } from "../lib/api";
import type { PlaylistSummary, Song } from "../types";

export function TrackCard({ song, queue, score, playlistId }: { song: Song; queue?: Song[]; score?: number; playlistId?: string }) {
  const { playTrack } = usePlayer();
  const { user } = useAuth();
  const [playlistChoice, setPlaylistChoice] = useState("");
  const client = useQueryClient();
  const playlists = useQuery({ queryKey: ["playlists"], queryFn: () => apiGet<PlaylistSummary[]>("/playlists"), enabled: Boolean(user) });
  const add = useMutation({
    mutationFn: (targetId: string) => apiPost<PlaylistSummary>(`/playlists/${targetId}/songs?song_id=${encodeURIComponent(song.id)}`),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ["playlists"] }); setPlaylistChoice(""); },
  });
  const remove = useMutation({
    mutationFn: () => apiDelete<PlaylistSummary>(`/playlists/${playlistId}/songs/${song.id}`),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ["playlists"] }); },
  });
  const duration = song.duration_seconds == null ? "—" : `${Math.floor(song.duration_seconds / 60)}:${String(song.duration_seconds % 60).padStart(2, "0")}`;
  return (
    <article className="track-card">
      <button className="artwork-button" onClick={() => playTrack(song, queue)} aria-label={`Play ${song.title}`}>
        {song.artwork_url ? <img src={song.artwork_url} alt="" loading="lazy" /> : <div className="artwork-fallback"><Disc3 size={34} /></div>}
        <span className="artwork-play"><Play size={18} fill="currentColor" /></span>
      </button>
      <div className="track-card-body">
        <div className="track-heading">
          <div className="min-w-0">
            <h3 title={song.title}>{song.title}</h3>
            <p title={song.artist_name}>{song.artist_name}</p>
          </div>
          <span className="track-duration">{duration}</span>
        </div>
        {song.tags.length > 0 && <div className="tag-row">{song.tags.slice(0, 3).map((tag) => <span key={tag}>{tag}</span>)}</div>}
        <div className="track-foot">
          <span className="source-label">{song.source === "jamendo" ? "Jamendo" : "VibeCast artist"}</span>
          {typeof score === "number" && <span className="match-label">{Math.round(score * 100)}% match</span>}
          {playlistId && <button className="track-action" aria-label={`Remove ${song.title} from playlist`} title="Remove from playlist" disabled={remove.isPending} onClick={() => remove.mutate()}><X size={13} /></button>}
          {!playlistId && user && <>
            {playlists.data?.some((playlist) => playlist.generation_type === "manual") && <select className="track-playlist-select" aria-label={`Choose playlist for ${song.title}`} value={playlistChoice} onChange={(event) => { const id = event.target.value; setPlaylistChoice(id); if (id) add.mutate(id); }} disabled={add.isPending}>
              <option value="">Add to playlist…</option>{playlists.data.filter((playlist) => playlist.generation_type === "manual").map((playlist) => <option value={playlist.id} key={playlist.id}>{playlist.name}</option>)}
            </select>}
            {playlists.isLoading && <span className="track-action-note">Loading playlists</span>}
            {playlists.data && !playlists.data.some((playlist) => playlist.generation_type === "manual") && <a className="track-action-note" href="/playlists">Create a playlist</a>}
          </>}
          {song.source_url && <a href={song.source_url} target="_blank" rel="noreferrer" aria-label="Open track source page"><ExternalLink size={13} /></a>}
          {song.license_url && <a className="license-link" href={song.license_url} target="_blank" rel="noreferrer">License</a>}
        </div>
        {(add.error || remove.error) && <span className="track-error" role="alert">{(add.error || remove.error)?.message}</span>}
        {add.isSuccess && <span className="track-success" role="status">Added to playlist</span>}
      </div>
    </article>
  );
}
