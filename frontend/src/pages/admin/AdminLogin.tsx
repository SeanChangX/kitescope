import { useState, useEffect } from "react";
import { Link } from "react-router-dom";

const API = "/api";

type Props = { onLogin: () => void };

export default function AdminLogin({ onLogin }: Props) {
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/auth/admin/setup-status`)
      .then((r) => r.json())
      .then((d) => setSetupRequired(d.setup_required))
      .catch(() => setSetupRequired(false));
  }, []);

  async function doSetup(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password || password.length < 8) {
      setError("Username and password (min 8 chars) required.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${API}/auth/admin/setup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
        credentials: "include",
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        onLogin();
      } else {
        setError(data.detail || "Setup failed.");
      }
    } catch {
      setError("Network error.");
    } finally {
      setLoading(false);
    }
  }

  async function doLogin(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setLoading(true);
    setError("");
    const form = new FormData();
    form.set("username", username.trim());
    form.set("password", password);
    try {
      const r = await fetch(`${API}/auth/admin/login`, {
        method: "POST",
        body: form,
        credentials: "include",
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        onLogin();
      } else {
        setError(data.detail || "Login failed.");
      }
    } catch {
      setError("Network error.");
    } finally {
      setLoading(false);
    }
  }

  if (setupRequired === null) return <p className="text-text-muted">Loading...</p>;

  return (
    <div className="mx-auto max-w-sm ks-card">
      <h2 className="font-gaming text-lg font-semibold text-text-primary">
        {setupRequired ? "Create admin account" : "Admin login"}
      </h2>
      <form onSubmit={setupRequired ? doSetup : doLogin} className="mt-4 space-y-3">
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="ks-input"
          autoComplete="username"
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="ks-input"
          autoComplete={setupRequired ? "new-password" : "current-password"}
        />
        {setupRequired && (
          <p className="text-xs text-text-muted">Password must be at least 8 characters.</p>
        )}
        {error && <p className="text-sm text-ks-danger">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="ks-btn ks-btn-primary w-full disabled:opacity-50"
        >
          {loading ? "..." : setupRequired ? "Create" : "Login"}
        </button>
      </form>
      <p className="mt-4 text-center">
        <Link to="/" className="text-sm text-text-secondary hover:text-primary">
          Back to app
        </Link>
      </p>
    </div>
  );
}
