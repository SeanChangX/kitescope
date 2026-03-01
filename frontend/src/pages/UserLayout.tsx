import { Outlet } from "react-router-dom";
import AppHeader from "../components/AppHeader";

export default function UserLayout() {
  return (
    <div className="min-h-screen bg-bg-primary">
      <AppHeader />
      <Outlet />
    </div>
  );
}
