import { useState } from "react";
import { authFetch } from "../../lib/auth";

export default function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [newPass, setNewPass] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    if (newPass !== confirm) {
      setMessage({ type: "err", text: "New password and confirmation do not match." });
      return;
    }
    if (newPass.length < 8) {
      setMessage({ type: "err", text: "New password must be at least 8 characters." });
      return;
    }
    const r = await authFetch("/api/auth/admin/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: current, new_password: newPass }),
    });
    const data = await r.json().catch(() => ({}));
    if (r.ok) {
      setMessage({ type: "ok", text: "Password updated." });
      setCurrent("");
      setNewPass("");
      setConfirm("");
    } else {
      setMessage({ type: "err", text: (data.detail as string) || "Failed to change password." });
    }
  }

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">Change password</h3>
      <form onSubmit={submit} className="space-y-3 max-w-sm">
        <div>
          <label className="block text-sm text-text-muted mb-1">Current password</label>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="ks-input"
            required
          />
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">New password</label>
          <input
            type="password"
            value={newPass}
            onChange={(e) => setNewPass(e.target.value)}
            className="ks-input"
            minLength={8}
            required
          />
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">Confirm new password</label>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="ks-input"
            minLength={8}
            required
          />
        </div>
        {message && (
          <p className={message.type === "ok" ? "text-ks-success text-sm" : "text-ks-danger text-sm"}>
            {message.text}
          </p>
        )}
        <button type="submit" className="ks-btn ks-btn-primary">
          Change password
        </button>
      </form>
    </div>
  );
}
