import { Routes, Route } from "react-router-dom";
import GuestView from "./pages/GuestView";
import UserLayout from "./pages/UserLayout";
import AdminLayout from "./pages/admin/AdminLayout";
import LoginPage from "./pages/LoginPage";
import AuthCallback from "./pages/AuthCallback";
import AuthTelegramCallback from "./pages/AuthTelegramCallback";
import NotificationSettings from "./pages/NotificationSettings";
import { useI18n } from "./lib/i18n";

const GITHUB_REPO = "https://github.com/SeanChangX/KiteScope";
const BUYMEACOFFEE_URL = "https://buymeacoffee.com/SeanChangX";

function App() {
  const { t } = useI18n();
  const floatBtnClass =
    "flex h-12 w-12 items-center justify-center rounded-full bg-bg-secondary border border-border text-text-muted hover:text-primary hover:border-primary transition-colors shadow-lg";
  return (
    <>
      <Routes>
        <Route path="/" element={<UserLayout />}>
          <Route index element={<GuestView />} />
          <Route path="notifications" element={<NotificationSettings />} />
        </Route>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/auth/telegram-callback" element={<AuthTelegramCallback />} />
        <Route path="/admin/*" element={<AdminLayout />} />
      </Routes>
      <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2">
        <a
          href={BUYMEACOFFEE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className={floatBtnClass}
          aria-label={t("aria.buyMeACoffee")}
        >
          <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
            <path d="M6.898 0L5.682 2.799H3.877v2.523h.695L5.277 9.8H4.172l1.46 8.23.938-.01L7.512 24h8.918l.062-.4.88-5.58.888.01 1.46-8.231h-1.056l.705-4.477h.756V2.8h-1.918L16.99 0H6.898zm.528.805h9.043l.771 1.78H6.652l.774-1.78zm-2.75 2.797H19.32v.92H4.676v-.92zm.453 6.998h13.635l-1.176 6.62-5.649-.06-5.636.06-1.174-6.62z" />
          </svg>
        </a>
        <a
          href={GITHUB_REPO}
          target="_blank"
          rel="noopener noreferrer"
          className={floatBtnClass}
          aria-label={t("aria.github")}
        >
          <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
          </svg>
        </a>
      </div>
    </>
  );
}

export default App;
