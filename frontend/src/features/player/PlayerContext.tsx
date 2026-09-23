import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Song } from "../../types";

type PlayerValue = {
  song: Song | null;
  queue: Song[];
  playing: boolean;
  setPlaying: (value: boolean) => void;
  playTrack: (song: Song, queue?: Song[]) => void;
  next: () => void;
  previous: () => void;
};

const PlayerContext = createContext<PlayerValue | null>(null);

export function PlayerProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<Song[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const song = queue[index] || null;

  const playTrack = useCallback((track: Song, list?: Song[]) => {
    const nextQueue = list?.length ? list : [track];
    let trackIndex = nextQueue.findIndex((candidate) => candidate.id === track.id);
    if (trackIndex < 0) trackIndex = 0;
    setQueue(nextQueue);
    setIndex(trackIndex);
    setPlaying(true);
  }, []);

  const next = useCallback(() => {
    setIndex((current) => (current + 1) % Math.max(1, queue.length));
    setPlaying(true);
  }, [queue.length]);
  const previous = useCallback(() => {
    setIndex((current) => (current - 1 + Math.max(1, queue.length)) % Math.max(1, queue.length));
    setPlaying(true);
  }, [queue.length]);

  const value = useMemo(() => ({ song, queue, playing, setPlaying, playTrack, next, previous }),
    [song, queue, playing, playTrack, next, previous]);
  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}

export function usePlayer() {
  const value = useContext(PlayerContext);
  if (!value) throw new Error("usePlayer must be used inside PlayerProvider");
  return value;
}
