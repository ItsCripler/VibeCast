import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes, Link } from "react-router-dom";
import { AuthProvider, useAuth } from "./features/auth/AuthContext";
import { PlayerProvider } from "./features/player/PlayerContext";
import { AppShell } from "./components/AppShell";
import type { User } from "./types";

const client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });
const LoginPage = lazy(() => import("./features/auth/LoginPage").then((module) => ({ default: module.LoginPage })));
const HomePage = lazy(() => import("./pages/HomePage").then((module) => ({ default: module.HomePage })));
const StatsPage = lazy(() => import("./pages/StatsPage").then((module) => ({ default: module.StatsPage })));
const PlaylistsPage = lazy(() => import("./pages/PlaylistsPage").then((module) => ({ default: module.PlaylistsPage })));
const ArtistPage = lazy(() => import("./pages/ArtistPage").then((module) => ({ default: module.ArtistPage })));
const LabelPage = lazy(() => import("./pages/LabelPage").then((module) => ({ default: module.LabelPage })));
const AdminPage = lazy(() => import("./pages/AdminPage").then((module) => ({ default: module.AdminPage })));

function RoleGate({ roles }: { roles: User["role"][] }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-view"><span className="spinner" />Loading your space…</div>;
  if (!user) return <div className="access-card"><h2>Sign in to continue</h2><p>Your private listening workspace is available after sign-in.</p><Link className="primary-button" to="/login">Sign in</Link></div>;
  if (!roles.includes(user.role)) return <div className="access-card"><h2>This page is for another role</h2><p>Your account does not have access to this dashboard.</p><Link to="/">Back to discover</Link></div>;
  return <Outlet />;
}

function AppRoutes() {
  return <Suspense fallback={<div className="loading-view"><span className="spinner" />Loading VibeCast…</div>}><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<AppShell />}>
      <Route index element={<HomePage />} />
      <Route element={<RoleGate roles={["listener", "artist", "label_admin", "platform_admin"]} />}>
        <Route path="playlists" element={<PlaylistsPage />} />
        <Route path="stats" element={<StatsPage />} />
      </Route>
      <Route element={<RoleGate roles={["artist"]} />}><Route path="artists" element={<ArtistPage />} /></Route>
      <Route element={<RoleGate roles={["label_admin", "platform_admin"]} />}><Route path="labels" element={<LabelPage />} /></Route>
      <Route element={<RoleGate roles={["platform_admin"]} />}><Route path="admin" element={<AdminPage />} /></Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>
  </Routes></Suspense>;
}

export default function App() {
  return <QueryClientProvider client={client}><BrowserRouter><AuthProvider><PlayerProvider><AppRoutes /></PlayerProvider></AuthProvider></BrowserRouter></QueryClientProvider>;
}
