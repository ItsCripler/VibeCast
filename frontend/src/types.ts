export type User = {
  id: string;
  name: string;
  email: string;
  role: "listener" | "artist" | "label_admin" | "platform_admin";
  created_at: string;
};

export type Song = {
  id: string;
  source: "jamendo" | "artist_upload";
  jamendo_track_id: string | null;
  title: string;
  artist_name: string;
  duration_seconds: number | null;
  released_at: string | null;
  tags: string[];
  artwork_url: string | null;
  source_url: string | null;
  license_url: string | null;
  audiodownload_allowed: boolean;
};

export type CatalogPage = { items: Song[]; page: number; page_size: number; total: number };
export type PlaylistSummary = {
  id: string;
  owner_id: string;
  name: string;
  is_public: boolean;
  generation_type: "manual" | "vibe" | "weekly";
  original_prompt: string | null;
  generated_at: string | null;
  created_at: string;
  songs: { song: Song; position: number; relevance_score: number | null }[];
};

export type VibeResult = {
  song: Song;
  score: number;
  semantic_score: number;
  tag_score: number;
  feature_score: number | null;
};
export type VibePlaylist = {
  playlist_id: string;
  name: string;
  prompt: string;
  generated_at: string;
  results: VibeResult[];
};

export type Playback = {
  song_id: string;
  url: string;
  source: string;
  source_url: string | null;
  license_url: string | null;
  audiodownload_allowed: boolean;
};

export type Analytics = {
  total_listening_seconds: number;
  qualified_plays: number;
  distinct_songs: number;
  distinct_artists: number;
  top_songs: { song_id: string; title: string; artist_name: string; artwork_url: string | null; qualified_plays: number; listening_seconds: number }[];
  top_artists: { name: string; qualified_plays: number; listening_seconds: number }[];
  top_genres_and_tags: { name: string; qualified_plays: number }[];
  mood_distribution: { name: string; qualified_plays: number }[];
  trend: { date: string; qualified_plays: number; listening_seconds: number }[];
  personality_summary: string;
};
