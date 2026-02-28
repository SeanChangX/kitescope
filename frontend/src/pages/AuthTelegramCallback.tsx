import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

const API = "/api";

export default function AuthTelegramCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    // Telegram redirects to auth_url with params in query string (?id=...&hash=...)
    // Only include params that are actually in the URL so the backend's data-check-string matches what Telegram signed.
    const hash = searchParams.get("hash");
    const id = searchParams.get("id");
    if (!hash || !id) {
      setStatus("error");
      setError("Invalid Telegram callback data.");
      return;
    }
    const body: Record<string, string | number> = { hash };
    searchParams.forEach((value, key) => {
      if (key === "hash") return;
      if (key === "id" || key === "auth_date") {
        const n = parseInt(value, 10);
        if (!isNaN(n)) body[key] = n;
      } else {
        body[key] = value;
      }
    });
    if (typeof body.id !== "number" || body.id === undefined) {
      setStatus("error");
      setError("Invalid user id.");
      return;
    }
    fetch(`${API}/auth/telegram/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "include",
    })
      .then((r) =>
        r.json().catch(() => ({})).then((data) => ({ ok: r.ok, data }))
      )
      .then(({ ok, data }) => {
        if (ok && data?.token_type === "bearer") {
          setStatus("ok");
          navigate("/", { replace: true });
        } else {
          setStatus("error");
          setError((data?.detail as string) || "Login failed.");
        }
      })
      .catch(() => {
        setStatus("error");
        setError("Network error.");
      });
  }, [navigate, searchParams]);

  if (status === "loading") {
    return (
      <div className="min-h-screen bg-bg-primary px-4 py-12">
        <p className="text-text-muted">Signing in with Telegram...</p>
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="min-h-screen bg-bg-primary px-4 py-12">
        <div className="ks-card max-w-md">
          <p className="text-ks-danger">{error}</p>
          <a href="/" className="mt-4 inline-block text-sm text-primary hover:underline">
            Back to home
          </a>
        </div>
      </div>
    );
  }
  return null;
}
