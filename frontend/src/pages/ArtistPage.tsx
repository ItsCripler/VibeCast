import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AudioLines, CheckCircle2, Clock3, FileAudio2, UploadCloud } from "lucide-react";
import { api, apiGet } from "../lib/api";
import type { Song } from "../types";

type ArtistSong = Song & { analysis_status: "pending" | "completed" | "failed" | "unavailable"; is_public: boolean };
type Performance = { song_id: string; title: string; qualified_plays: number; listening_seconds: number; last_played_at: string | null };

export function ArtistPage() {
  const client = useQueryClient();
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [license, setLicense] = useState("");
  const [audio, setAudio] = useState<File | null>(null);
  const [rights, setRights] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const profile = useQuery({ queryKey: ["artist-profile"], queryFn: () => apiGet<{ id: string; stage_name: string; label_id: string | null }>("/artists/me") });
  const songs = useQuery({ queryKey: ["artist-songs"], queryFn: () => apiGet<ArtistSong[]>("/artists/me/songs"), refetchInterval: 10_000 });
  const performance = useQuery({ queryKey: ["artist-performance"], queryFn: () => apiGet<Performance[]>("/artists/me/performance") });
  const upload = useMutation({
    mutationFn: (form: FormData) => api<{ song_id: string; status: string }>("/artists/me/songs", { method: "POST", body: form }),
    onSuccess: async () => { setMessage("Upload received. The track will appear when its embedding is ready."); setTitle(""); setTags(""); setLicense(""); setAudio(null); setRights(false); await client.invalidateQueries({ queryKey: ["artist-songs"] }); },
    onError: (reason: Error) => setError(reason.message),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setMessage(""); setError("");
    if (!audio) { setError("Choose an audio file first."); return; }
    const form = new FormData();
    form.set("title", title.trim()); form.set("tags", tags); form.set("license_url", license.trim());
    form.set("rights_confirmed", String(rights)); form.set("audio", audio);
    upload.mutate(form);
  }

  return (
    <div className="dashboard-page">
      <div className="page-title-row"><div><div className="section-kicker"><AudioLines size={13} /> ARTIST WORKSPACE</div><h1>{profile.data?.stage_name || "Artist studio"}</h1><p className="muted">Manage your first-party uploads and see how listeners respond.</p></div><span className="period-pill">ARTIST UPLOADS</span></div>
      {profile.isLoading ? <div className="loading-inline"><span className="spinner" />Loading artist profile…</div> : profile.isError ? <div className="empty-state"><h3>Artist profile unavailable</h3><p>{profile.error.message}</p></div> : null}
      <div className="artist-layout">
        <section className="panel upload-panel"><div className="panel-heading"><div><span className="section-kicker">ADD A RECORDING</span><h2>Upload a track</h2></div><span className="upload-mark"><UploadCloud size={19} /></span></div>
          <p className="muted">MP3, WAV, FLAC, or OGG up to 40 MB. Files stay on VibeCast storage. Your track is published after metadata embedding.</p>
          <form className="upload-form" onSubmit={submit}>
            <label>Track title<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={240} required placeholder="Give this track a name" /></label>
            <label>Tags, separated by commas<input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="ambient, guitar, reflective" /></label>
            <label>License or rights-information URL<input value={license} onChange={(event) => setLicense(event.target.value)} type="url" required placeholder="https://…" /></label>
            <label className="file-drop"><FileAudio2 size={20} /><span>{audio ? audio.name : "Choose an audio file"}<small>MP3 · WAV · FLAC · OGG</small></span><input type="file" accept="audio/mpeg,audio/wav,audio/flac,audio/ogg,.mp3,.wav,.flac,.ogg" onChange={(event) => setAudio(event.target.files?.[0] || null)} required /></label>
            <label className="rights-check"><input type="checkbox" checked={rights} onChange={(event) => setRights(event.target.checked)} required /><span>I own or have permission to upload and stream this recording, and I’ve provided its license or rights information.</span></label>
            {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="form-success" role="status">{message}</p>}
            <button className="primary-button upload-submit" disabled={upload.isPending || !title.trim() || !audio || !rights}>{upload.isPending ? "Uploading…" : "Upload track"}<UploadCloud size={16} /></button>
          </form>
        </section>
        <section className="panel artist-song-panel"><div className="panel-heading"><div><span className="section-kicker">YOUR RELEASES</span><h2>Uploaded tracks</h2></div></div>
          {songs.isLoading ? <div className="loading-inline"><span className="spinner" />Loading tracks…</div> : songs.data?.length ? <div className="artist-track-list">{songs.data.map((song) => <article className="artist-track-row" key={song.id}><span className="artist-track-icon"><FileAudio2 size={17} /></span><div className="artist-track-info"><strong>{song.title}</strong><span>{song.tags.slice(0, 3).join(" · ") || "No tags"}</span></div><span className={`processing-status status-${song.analysis_status}`}>{song.analysis_status === "completed" ? <CheckCircle2 size={13} /> : <Clock3 size={13} />}{song.is_public ? "Published" : song.analysis_status}</span></article>)}</div> : <div className="panel-empty">Your uploads will appear here once received.</div>}
        </section>
      </div>
      <section className="panel performance-panel"><div className="panel-heading"><div><span className="section-kicker">LISTENER RESPONSE</span><h2>Track performance</h2></div></div>
        {performance.isLoading ? <div className="loading-inline"><span className="spinner" />Loading performance…</div> : performance.data?.length ? <div className="performance-table"><div className="performance-header"><span>TRACK</span><span>QUALIFIED PLAYS</span><span>LISTENING TIME</span><span>LAST PLAYED</span></div>{performance.data.map((row) => <div className="performance-row" key={row.song_id}><strong>{row.title}</strong><span>{row.qualified_plays.toLocaleString()}</span><span>{Math.floor(row.listening_seconds / 60)} min</span><span>{row.last_played_at ? new Date(row.last_played_at).toLocaleDateString() : "—"}</span></div>)}</div> : <p className="panel-empty">Performance appears after listeners play published tracks for at least 30 seconds or 80% of a short track.</p>}
      </section>
    </div>
  );
}
