import { Activity, AudioLines, Compass, LogIn, LogOut, Music2, Shield, Sparkles, Users } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../features/auth/AuthContext";
import { PlayerBar } from "./PlayerBar";

const navItems = [
  { to: "/", label: "Discover", icon: Compass, roles: ["listener", "artist", "label_admin", "platform_admin"] },
  { to: "/playlists", label: "Your playlists", icon: Music2, roles: ["listener", "artist", "label_admin", "platform_admin"] },
  { to: "/stats", label: "My listening", icon: Activity, roles: ["listener", "artist", "label_admin", "platform_admin"] },
  { to: "/artists", label: "Artist studio", icon: AudioLines, roles: ["artist"] },
  { to: "/labels", label: "Label overview", icon: Users, roles: ["label_admin"] },
  { to: "/admin", label: "Platform admin", icon: Shield, roles: ["platform_admin"] },
];

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function signOut() {
    try { await logout(); } finally { navigate("/login"); }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand-lockup"><span className="brand-mark"><AudioLines size={20} /></span><span>VibeCast</span></NavLink>
        <div className="side-caption">YOUR SPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          {navItems.filter((item) => user ? item.roles.includes(user.role) : item.to === "/").map((item) => {
            const Icon = item.icon;
            return <NavLink key={item.to} to={item.to} end={item.to === "/"} className={({ isActive }) => `side-link ${isActive ? "active" : ""}`}>
              <Icon size={17} strokeWidth={1.8} /><span>{item.label}</span>{item.to === "/" && <span className="nav-live" />}
            </NavLink>;
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note"><Sparkles size={16} /><div><strong>Follow the feeling</strong><span>Describe a mood. Find a soundtrack.</span></div></div>
          {user ? <button className="user-chip" onClick={signOut}><span className="avatar">{user.name.slice(0, 1).toUpperCase()}</span><span className="user-label"><strong>{user.name}</strong><small>{user.role.replace("_", " ")}</small></span><LogOut size={15} /></button>
            : <button className="user-chip" onClick={() => navigate("/login")}><span className="avatar guest-avatar"><LogIn size={15} /></span><span className="user-label"><strong>Sign in</strong><small>Personalize your listening</small></span></button>}
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div><span className="topbar-greeting">{greeting()}{user ? `, ${user.name.split(" ")[0]}` : ""}</span><span className="topbar-subtitle">Let the next track find you.</span></div>
          <div className="topbar-actions"><span className="online-indicator"><i /> Jamendo catalog</span>{!user && <button className="small-outline" onClick={() => navigate("/login")}>Sign in <LogIn size={14} /></button>}</div>
        </header>
        <main className="page-content"><Outlet /></main>
      </div>
      <PlayerBar />
    </div>
  );
}
