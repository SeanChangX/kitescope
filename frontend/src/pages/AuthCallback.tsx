import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { setUserToken } from "../lib/auth";

const API = "/api";

export default function AuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    const code = searchParams.get("code");
    if (!code) {
      setStatus("error");
      setError("No authorization code.");
      return;
    }
    const redirectUri = `${window.location.origin}${window.location.pathname}`;
    fetch(`${API}/auth/line/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, redirect_uri: redirectUri }),
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
  }, [searchParams, navigate]);

  if (status === "loading") {
    return (
      <div className="min-h-screen bg-bg-primary px-4 py-12">
        <p className="text-text-muted">Signing in...</p>
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
