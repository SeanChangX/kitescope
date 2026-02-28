import { useState } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

export default function ChangePassword() {
  const { t } = useI18n();
  const [current, setCurrent] = useState("");
  const [newPass, setNewPass] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    if (newPass !== confirm) {
      setMessage({ type: "err", text: t("admin.passwordMismatch") });
      return;
    }
    if (newPass.length < 8) {
      setMessage({ type: "err", text: t("admin.passwordMinLength") });
      return;
    }
    const r = await authFetch("/api/auth/admin/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: current, new_password: newPass }),
    });
    const data = await r.json().catch(() => ({}));
    if (r.ok) {
      setMessage({ type: "ok", text: t("admin.passwordUpdated") });
      setCurrent("");
      setNewPass("");
      setConfirm("");
    } else {
      setMessage({ type: "err", text: (data.detail as string) || t("admin.passwordChangeFailed") });
    }
  }

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">{t("admin.changePassword")}</h3>
      <form onSubmit={submit} className="space-y-3 max-w-sm">
        <div>
          <label className="block text-sm text-text-muted mb-1">{t("admin.currentPassword")}</label>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="ks-input"
            required
          />
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">{t("admin.newPassword")}</label>
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
          <label className="block text-sm text-text-muted mb-1">{t("admin.confirmNewPassword")}</label>
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
          {t("admin.changePassword")}
        </button>
      </form>
    </div>
  );
}
