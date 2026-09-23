import { useQuery } from "@tanstack/react-query";
import { Activity, Clock3, Disc3, Headphones, Music2, Sparkles } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiGet } from "../lib/api";
import type { Analytics } from "../types";

function listeningTime(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function StatsPage() {
  const stats = useQuery({ queryKey: ["my-stats"], queryFn: () => apiGet<Analytics>("/users/me/stats?days=30") });
  if (stats.isLoading) return <div className="loading-view"><span className="spinner" />Gathering your listening history…</div>;
  if (stats.isError) return <div className="empty-state"><h2>We couldn’t load your listening stats</h2><p>{stats.error.message}</p><button className="secondary-button" onClick={() => void stats.refetch()}>Try again</button></div>;
  const data = stats.data!;
  const hasActivity = data.qualified_plays > 0;

  return (
    <div className="dashboard-page">
      <div className="page-title-row"><div><div className="section-kicker"><Activity size={13} /> YOUR LISTENING</div><h1>My listening</h1><p className="muted">A picture of what you’ve played, generated from your own listening history.</p></div><span className="period-pill">PAST 30 DAYS</span></div>
      <div className="metric-grid">
        <article className="metric-card"><span className="metric-icon mint"><Clock3 size={18} /></span><span className="metric-label">LISTENING TIME</span><strong>{listeningTime(data.total_listening_seconds)}</strong><small>Qualified plays only</small></article>
        <article className="metric-card"><span className="metric-icon violet"><Headphones size={18} /></span><span className="metric-label">QUALIFIED PLAYS</span><strong>{data.qualified_plays.toLocaleString()}</strong><small>30 sec or 80% of a short track</small></article>
        <article className="metric-card"><span className="metric-icon peach"><Music2 size={18} /></span><span className="metric-label">ARTISTS PLAYED</span><strong>{data.distinct_artists}</strong><small>In the past 30 days</small></article>
        <article className="metric-card"><span className="metric-icon blue"><Disc3 size={18} /></span><span className="metric-label">TRACKS DISCOVERED</span><strong>{data.distinct_songs}</strong><small>Distinct tracks in the past 30 days</small></article>
      </div>

      <div className="analytics-grid">
        <section className="panel chart-panel">
          <div className="panel-heading"><div><span className="section-kicker">LISTENING RHYTHM</span><h2>Your month, in sound</h2></div><span className="chart-legend"><i /> Qualified plays</span></div>
          {hasActivity ? <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.trend} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
            <defs><linearGradient id="playsFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a99cff" stopOpacity={0.32} /><stop offset="95%" stopColor="#a99cff" stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid stroke="#272c38" vertical={false} strokeDasharray="3 5" />
            <XAxis dataKey="date" tickFormatter={(value: string) => value.slice(5)} stroke="#777d8c" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
            <YAxis allowDecimals={false} stroke="#777d8c" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
            <Tooltip contentStyle={{ background: "#171b25", border: "1px solid #303646", borderRadius: 12, color: "#f5f4fb" }} labelStyle={{ color: "#aaa5c9" }} />
            <Area type="monotone" dataKey="qualified_plays" name="Plays" stroke="#a99cff" strokeWidth={2.5} fill="url(#playsFill)" activeDot={{ r: 5, fill: "#c5baff" }} />
          </AreaChart></ResponsiveContainer></div> : <div className="chart-empty"><span className="empty-icon"><Headphones size={22} /></span><strong>Your rhythm will show up here</strong><p>Play tracks for a little while. Your listening history will fill in the chart.</p></div>}
        </section>
        <section className="panel personality-panel"><div className="personality-mark"><Sparkles size={18} /></div><span className="section-kicker">A NOTE ABOUT YOUR TASTE</span><h2>Music personality</h2><p>{data.personality_summary}</p><div className="personality-rule" /><small>Based on Jamendo tags from your qualified plays. This summary changes as your listening does.</small></section>
      </div>

      <div className="analytics-grid lower-grid">
        <section className="panel list-panel"><div className="panel-heading"><div><span className="section-kicker">REPLAYED MOST</span><h2>Top tracks</h2></div></div>
          {data.top_songs.length ? <ol className="rank-list">{data.top_songs.slice(0, 6).map((song, index) => <li key={song.song_id}><span className="rank-number">{String(index + 1).padStart(2, "0")}</span>{song.artwork_url ? <img src={song.artwork_url} alt="" /> : <span className="rank-art"><Disc3 size={15} /></span>}<span className="rank-name"><strong>{song.title}</strong><small>{song.artist_name}</small></span><span className="rank-value">{song.qualified_plays} plays</span></li>)}</ol> : <p className="panel-empty">No qualified plays yet.</p>}
        </section>
        <section className="panel list-panel"><div className="panel-heading"><div><span className="section-kicker">SOUNDING LIKE</span><h2>Top tags</h2></div></div>
          {data.top_genres_and_tags.length ? <div className="taste-list">{data.top_genres_and_tags.slice(0, 8).map((tag) => <div className="taste-row" key={tag.name}><span>{tag.name}</span><div className="taste-track"><i style={{ width: `${Math.max(8, Math.min(100, (tag.qualified_plays / data.top_genres_and_tags[0].qualified_plays) * 100))}%` }} /></div><small>{tag.qualified_plays}</small></div>)}</div> : <p className="panel-empty">Jamendo tags from your qualified plays will appear here.</p>}
        </section>
      </div>
      <div className="analytics-grid last-grid">
        <section className="panel list-panel"><div className="panel-heading"><div><span className="section-kicker">ON REPEAT</span><h2>Favorite artists</h2></div></div>
          {data.top_artists.length ? <ol className="rank-list artist-ranks">{data.top_artists.slice(0, 6).map((artist, index) => <li key={artist.name}><span className="rank-number">{String(index + 1).padStart(2, "0")}</span><span className="artist-disc"><Disc3 size={15} /></span><span className="rank-name"><strong>{artist.name}</strong><small>{listeningTime(artist.listening_seconds)} listened</small></span><span className="rank-value">{artist.qualified_plays}</span></li>)}</ol> : <p className="panel-empty">Your most-played artists will appear here.</p>}
        </section>
        <section className="panel list-panel"><div className="panel-heading"><div><span className="section-kicker">MOOD & FEELING</span><h2>Mood tags</h2></div></div>
          {data.mood_distribution.length ? <div className="tag-cloud">{data.mood_distribution.map((item) => <span key={item.name}>{item.name}<small>{item.qualified_plays}</small></span>)}</div> : <p className="panel-empty">No mood tags are available in your played-track metadata yet.</p>}
        </section>
      </div>
    </div>
  );
}
