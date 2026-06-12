import { Outlet } from "react-router-dom";
import AppHeader from "../components/AppHeader";

export default function UserLayout() {
  return (
    <div className="flex h-screen flex-col bg-bg-primary">
      <AppHeader />
      {/* pb-24 reserves space so the fixed bottom-right action buttons (GitHub / Buy Me a Coffee) never cover page content. */}
      <main className="min-h-0 flex-1 overflow-y-auto pb-24">
        <Outlet />
      </main>
    </div>
  );
}
