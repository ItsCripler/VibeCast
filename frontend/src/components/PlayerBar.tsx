import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Pause, Play, SkipBack, SkipForward, Volume2 } from "lucide-react";
import { apiGet, apiPost } from "../lib/api";
import { usePlayer } from "../features/player/PlayerContext";
import type { Playback } from "../types";

export function PlayerBar() {
  const { song, playing, setPlaying, next, previous } = usePlayer();
  const audioRef = useRef<HTMLAudioElement>(null);
  const playedRef = useRef(0);
  const previousTimeRef = useRef<number | null>(null);
  const eventRef = useRef<{ songId: string; id: string } | null>(null);
  const [src, setSrc] = useState("");
  const [error, setError] = useState("");
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);

  const flushPlay = useCallback(() => {
    const event = eventRef.current;
    if (!event) return;
    const seconds = Math.floor(playedRef.current);
    eventRef.current = null;
    playedRef.current = 0;
    previousTimeRef.current = null;
    if (seconds > 0) {
      void apiPost("/plays", { client_event_id: event.id, song_id: event.songId,
        duration_played_seconds: seconds, played_at: new Date().toISOString() }).catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!song) {
      setSrc("");
      setCurrent(0);
      setDuration(0);
      return;
    }
    let active = true;
    setError("");
    setCurrent(0);
    setDuration(song.duration_seconds || 0);
    apiGet<Playback>("/catalog/songs/" + song.id + "/playback").then(async (playback) => {
      if (!active) return;
      setSrc(playback.url);
      if (audio) {
        audio.src = playback.url;
        audio.load();
        if (playing) {
          try { await audio.play(); } catch { setPlaying(false); }
        }
      }
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : "Playback is unavailable.");
    });
    return () => {
      active = false;
      flushPlay();
      audio?.pause();
      if (audio) audio.removeAttribute("src");
    };
  }, [song?.id, flushPlay]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !src) return;
    audio.volume = volume;
    if (playing && audio.paused) void audio.play().catch(() => setPlaying(false));
    if (!playing && !audio.paused) audio.pause();
  }, [playing, src, volume, setPlaying]);

  function onPlay() {
    if (song && !eventRef.current) {
      eventRef.current = { songId: song.id, id: crypto.randomUUID() };
      playedRef.current = 0;
      previousTimeRef.current = audioRef.current?.currentTime ?? 0;
    }
    setPlaying(true);
  }

  function onTimeUpdate() {
    const audio = audioRef.current;
    if (!audio) return;
    const now = audio.currentTime;
    const previousTime = previousTimeRef.current;
    if (previousTime !== null) {
      const elapsed = now - previousTime;
      if (elapsed > 0 && elapsed <= 4) playedRef.current += elapsed;
    }
    previousTimeRef.current = now;
    setCurrent(now);
  }

  function togglePlay() {
    if (!song) return;
    if (playing) {
      audioRef.current?.pause();
      setPlaying(false);
    } else {
      setPlaying(true);
    }
  }

  const shownDuration = duration || audioRef.current?.duration || 0;
  const progress = shownDuration ? (current / shownDuration) * 100 : 0;
  const formatTime = (seconds: number) => Math.floor(seconds / 60) + ":" + String(Math.floor(seconds % 60)).padStart(2, "0");

  return (
    <footer className="player-bar" aria-label="Music player">
      <audio ref={audioRef} onPlay={onPlay} onPause={flushPlay}
        onTimeUpdate={onTimeUpdate} onSeeking={() => { previousTimeRef.current = audioRef.current?.currentTime ?? null; }}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
        onEnded={() => { flushPlay(); next(); }} onError={() => { if (song && src) setError("This audio resource is unavailable right now."); }} />
      <div className="player-track">
        {song?.artwork_url ? <img src={song.artwork_url} alt="" /> : <div className="player-art"><Volume2 size={18} /></div>}
        <div className="min-w-0"><strong>{song?.title || "Choose a track"}</strong><span>{song?.artist_name || "Your next discovery is waiting"}</span></div>
      </div>
      <div className="player-center">
        <div className="player-buttons">
          <button onClick={previous} disabled={!song} aria-label="Previous track"><SkipBack size={17} fill="currentColor" /></button>
          <button className="player-toggle" onClick={togglePlay} disabled={!song || !src} aria-label={playing ? "Pause" : "Play"}>
            {playing ? <Pause size={17} fill="currentColor" /> : <Play size={17} fill="currentColor" />}
          </button>
          <button onClick={next} disabled={!song} aria-label="Next track"><SkipForward size={17} fill="currentColor" /></button>
        </div>
        <div className="progress-row">
          <span>{formatTime(current)}</span>
          <input aria-label="Seek" type="range" min={0} max={shownDuration || 1} value={Math.min(current, shownDuration || 1)}
            style={{ "--progress": progress + "%" } as React.CSSProperties}
            onChange={(event) => { const value = Number(event.target.value); if (audioRef.current) audioRef.current.currentTime = value; setCurrent(value); }} />
          <span>{formatTime(shownDuration)}</span>
        </div>
      </div>
      <div className="player-volume"><Volume2 size={16} /><input aria-label="Volume" type="range" min={0} max={1} step={0.01} value={volume}
        onChange={(event) => setVolume(Number(event.target.value))} /></div>
      {error && <div className="player-error" role="status"><AlertCircle size={14} />{error}</div>}
    </footer>
  );
}
