import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { setUserToken } from "../lib/auth";

const API = "/api";

export default function AuthTelegramCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    // Telegram redirects to auth_url with params in query string (?id=...&hash=...)
    const hash = searchParams.get("hash");
    const id = searchParams.get("id");
    if (!hash || !id) {
      setStatus("error");
      setError("Invalid Telegram callback data.");
      return;
    }
    const body = {
      id: parseInt(id, 10),
      first_name: searchParams.get("first_name") || "",
      last_name: searchParams.get("last_name") || "",
      username: searchParams.get("username") || "",
      photo_url: searchParams.get("photo_url") || "",
      auth_date: parseInt(searchParams.get("auth_date") || "0", 10),
      hash,
    };
    if (isNaN(body.id)) {
      setStatus("error");
      setError("Invalid user id.");
      return;
    }
    fetch(`${API}/auth/telegram/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json().catch(() => ({})))
      .then((data) => {
        if (data.access_token) {
          setUserToken(data.access_token);
          setStatus("ok");
          navigate("/", { replace: true });
        } else {
          setStatus("error");
          setError((data.detail as string) || "Login failed.");
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
