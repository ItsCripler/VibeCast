import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, Compass, LoaderCircle, Search, Sparkles, WandSparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { TrackCard } from "../components/TrackCard";
import { useAuth } from "../features/auth/AuthContext";
import { apiGet, apiPost } from "../lib/api";
import type { CatalogPage, Song, VibePlaylist } from "../types";

const promptExamples = ["calm music for a rainy afternoon", "bright indie for a long drive", "soft focus for late-night reading"];

export function HomePage() {
  const { user } = useAuth();
  const [prompt, setPrompt] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [catalogPage, setCatalogPage] = useState(1);
  const [catalogTag, setCatalogTag] = useState("");
  const catalog = useQuery({
    queryKey: ["catalog", searchTerm, catalogTag, catalogPage],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(catalogPage), page_size: "24" });
      if (searchTerm) params.set("q", searchTerm);
      if (catalogTag) params.set("tag", catalogTag);
      return apiGet<CatalogPage>(`/catalog/songs?${params.toString()}`);
    },
  });
  const recs = useQuery({ queryKey: ["recommendations"], queryFn: () => apiGet<{ song: Song; score: number }[]>("/users/me/recommendations?limit=8"), enabled: Boolean(user), retry: false });
  const vibe = useMutation({ mutationFn: (value: string) => apiPost<VibePlaylist>("/playlists/vibe", { prompt: value, limit: 24 }) });

  function submitVibe(event: FormEvent) {
    event.preventDefault();
    const clean = prompt.trim();
    if (clean.length >= 5) vibe.mutate(clean);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setSearchTerm(searchDraft.trim());
    setCatalogPage(1);
  }

  const catalogTracks = catalog.data?.items || [];
  const knownTags = useRef(new Set<string>());
  catalogTracks.forEach((song) => song.tags.forEach((tag) => knownTags.current.add(tag)));
  const tagOptions = Array.from(knownTags.current).sort();
  const vibeSongs = vibe.data?.results.map((result) => result.song) || [];

  return (
    <div className="home-page">
      <section className="hero-panel">
        <div className="hero-glow hero-glow-one" /><div className="hero-glow hero-glow-two" />
        <div className="hero-content">
          <div className="eyebrow"><span className="eyebrow-dot" /> A SOUNDTRACK FOR RIGHT NOW</div>
          <h1>What does this<br /><em>moment sound like?</em></h1>
          <p>Describe a feeling, a place, a time of day. We’ll find real independent tracks that meet you there.</p>
          <form className="vibe-form" onSubmit={submitVibe}>
            <WandSparkles size={19} />
            <input aria-label="Describe your vibe" value={prompt} maxLength={500} onChange={(event) => setPrompt(event.target.value)} placeholder="Try “hazy, hopeful music for the ride home”" />
            <button type="submit" disabled={vibe.isPending || prompt.trim().length < 5}>{vibe.isPending ? <LoaderCircle className="spin" size={17} /> : <>Find my vibe <ArrowRight size={16} /></>}</button>
          </form>
          <div className="prompt-examples">{promptExamples.map((example) => <button key={example} onClick={() => setPrompt(example)}>{example}</button>)}</div>
          {vibe.isError && <p className="inline-error" role="alert">{vibe.error.message}{vibe.error.message.toLowerCase().includes("sign in") || ("status" in vibe.error && vibe.error.status === 401) ? <> <Link to="/login">Sign in to save a vibe playlist.</Link></> : null}</p>}
          {vibe.data && <div className="vibe-success"><Sparkles size={15} /><span>“{vibe.data.prompt}” — {vibe.data.results.length} tracks found and saved</span><Link to="/playlists">Open playlists <ArrowRight size={13} /></Link></div>}
        </div>
        <div className="hero-art" aria-hidden="true"><div className="hero-disc"><span /><i /><b /></div><div className="hero-ribbon ribbon-a" /><div className="hero-ribbon ribbon-b" /><div className="hero-orb orb-a" /><div className="hero-orb orb-b" /></div>
        <div className="hero-index">01 <span>/</span> DISCOVER</div>
      </section>

      {vibe.data && <section className="section-block vibe-results" aria-live="polite">
        <div className="section-heading"><div><div className="section-kicker"><Sparkles size={13} /> YOUR GENERATED VIBE</div><h2>{vibe.data.name}</h2><p className="muted">Semantic matches from the synced catalog</p></div><button className="text-button" onClick={() => vibe.mutate(vibe.data!.prompt)}>Regenerate <ArrowDownRight size={15} /></button></div>
        <div className="track-grid">{vibe.data.results.map((result) => <TrackCard key={result.song.id} song={result.song} queue={vibeSongs} score={result.score} />)}</div>
      </section>}

      {user && <section className="section-block">
        <div className="section-heading"><div><div className="section-kicker"><Sparkles size={13} /> BUILT AROUND YOU</div><h2>Your next few favorites</h2><p className="muted">Content similarity and listening patterns, updated from your plays</p></div><Link className="text-button" to="/stats">Your listening <ArrowRight size={15} /></Link></div>
        {recs.isLoading ? <div className="loading-inline"><span className="spinner" />Finding your next listen…</div> : recs.data?.length ? <div className="track-grid">{recs.data.map((item) => <TrackCard key={item.song.id} song={item.song} queue={recs.data.map((entry) => entry.song)} score={item.score} />)}</div> : <div className="empty-inline"><p>Keep a few tracks playing and your recommendations will start to take shape.</p></div>}
      </section>}

      <section className="section-block catalog-section">
        <div className="section-heading catalog-heading"><div><div className="section-kicker"><Compass size={13} /> THE INDEPENDENT CATALOG</div><h2>{searchTerm ? `Results for “${searchTerm}”` : "Explore the catalog"}</h2><p className="muted">Every external track comes from Jamendo and links back to its source.</p></div>
          <form className="catalog-search" onSubmit={submitSearch}><Search size={16} /><input aria-label="Search catalog" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="Track, artist, album…" /><button type="submit">Search</button></form>
        </div>
        {catalog.data && (catalogTracks.length > 0 || catalogTag) && <div className="catalog-controls"><label>Filter by Jamendo tag<select aria-label="Filter by Jamendo tag" value={catalogTag} onChange={(event) => { setCatalogTag(event.target.value); setCatalogPage(1); }}><option value="">All tags</option>{tagOptions.map((tag) => <option key={tag} value={tag}>{tag}</option>)}</select></label><span>{catalog.data.total.toLocaleString()} matching tracks</span></div>}
        {catalog.isLoading ? <div className="loading-inline"><span className="spinner" />Loading the synced catalog…</div> : catalog.isError ? <div className="empty-state"><h3>The catalog is unavailable</h3><p>{catalog.error.message}</p><button className="text-button" onClick={() => void catalog.refetch()}>Try again <ArrowRight size={14} /></button></div> : catalogTracks.length ? <><div className="track-grid">{catalogTracks.map((song) => <TrackCard key={song.id} song={song} queue={catalogTracks} />)}</div><div className="catalog-pagination"><button className="secondary-button" disabled={catalogPage === 1} onClick={() => setCatalogPage((page) => Math.max(1, page - 1))}>Previous</button><span>Page {catalogPage} of {Math.max(1, Math.ceil((catalog.data?.total || 0) / 24))}</span><button className="secondary-button" disabled={catalogPage >= Math.ceil((catalog.data?.total || 0) / 24)} onClick={() => setCatalogPage((page) => page + 1)}>Next</button></div></> : <div className="empty-state"><div className="empty-icon"><Compass size={23} /></div><h3>{catalog.data?.total === 0 ? "No tracks match those filters" : "No tracks are synced yet"}</h3><p>{catalog.data?.total === 0 ? "Try another title or tag." : "VibeCast does not ship a sample song catalog. A platform administrator can connect Jamendo and start the first sync."}</p>{!user && catalog.data?.total !== 0 && <Link className="secondary-button" to="/login">Staff sign in <ArrowRight size={14} /></Link>}</div>}
      </section>
      <footer className="content-footnote">Jamendo artists are credited as the creators. Each Jamendo track links to its Jamendo page.</footer>
    </div>
  );
}
