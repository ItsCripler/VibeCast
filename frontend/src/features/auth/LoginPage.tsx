import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Disc3, ShieldCheck } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { apiGet, apiPost } from "../../lib/api";
import { useAuth } from "./AuthContext";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const google = useQuery({ queryKey: ["google-status"], queryFn: () => apiGet<{ configured: boolean }>("/auth/google/status") });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiPost("/auth/staff/login", { email, password });
      await refresh();
      navigate("/");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-orbit orbit-one" /><div className="login-orbit orbit-two" />
      <nav className="login-nav"><Link className="brand-lockup" to="/"><span className="brand-mark"><Disc3 size={21} /></span>VibeCast</Link><Link className="quiet-link" to="/">Explore catalog <ArrowRight size={15} /></Link></nav>
      <section className="login-card">
        <div className="eyebrow"><span className="eyebrow-dot" /> MUSIC, MEET MOMENT</div>
        <h1>Find your<br /><em>frequency.</em></h1>
        <p className="login-intro">Sign in to make every listen feel a little more like you.</p>
        {google.data?.configured ? (
          <a className="google-button" href="/api/v1/auth/google"><span className="google-g">G</span>Continue with Google</a>
        ) : (
          <div className="google-disabled" title="Configure Google OAuth credentials to enable listener sign-in">
            <span className="google-g">G</span><span>Google sign-in not configured</span><span className="setup-dot" />
          </div>
        )}
        <div className="form-divider"><span>or staff sign in</span></div>
        <form onSubmit={submit} className="login-form">
          <label>Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required placeholder="you@vibecast.app" /></label>
          <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required placeholder="Enter your password" /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button login-submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}<ArrowRight size={17} /></button>
        </form>
        <div className="login-footnote"><ShieldCheck size={15} /><span>Secure sessions. Your listening data stays yours.</span></div>
      </section>
      <footer className="login-footer"><span>MADE FOR THE WAY YOU FEEL</span><span>Jamendo tracks are credited to their artists and source.</span></footer>
    </main>
  );
}
