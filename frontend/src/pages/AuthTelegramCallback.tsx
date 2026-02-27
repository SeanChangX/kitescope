import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { setUserToken } from "../lib/auth";

const API = "/api";

function parseHashFragment(hash: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!hash || hash[0] !== "#") return out;
  const params = new URLSearchParams(hash.slice(1));
  params.forEach((v, k) => {
    out[k] = v;
  });
  return out;
}

export default function AuthTelegramCallback() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    const params = parseHashFragment(window.location.hash);
    const hash = params.hash;
    if (!hash || !params.id) {
      setStatus("error");
      setError("Invalid Telegram callback data.");
      return;
    }
    const body = {
      id: parseInt(params.id, 10),
      first_name: params.first_name || "",
      last_name: params.last_name || "",
      username: params.username || "",
      photo_url: params.photo_url || "",
      auth_date: parseInt(params.auth_date || "0", 10),
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
  }, [navigate]);

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
