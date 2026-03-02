import { Outlet } from "react-router-dom";
import AppHeader from "../components/AppHeader";

export default function UserLayout() {
  return (
    <div className="flex h-screen flex-col bg-bg-primary">
      <AppHeader />
      <main className="min-h-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
