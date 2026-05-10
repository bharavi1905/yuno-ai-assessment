import { useEffect, useState } from "react";
import { Outlet, NavLink, useLocation } from "react-router-dom";

const NAV = [
  {
    path: "/dashboard",
    label: "Dashboard",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
        <path d="M3 3h6v6H3V3zm8 0h6v6h-6V3zM3 11h6v6H3v-6zm8 0h6v6h-6v-6z" />
      </svg>
    ),
  },
  {
    path: "/agents",
    label: "Agents",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
        <path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" />
      </svg>
    ),
  },
  {
    path: "/workflows",
    label: "Workflows",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
        <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zm0 8a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zm8-8a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2h-2zm-2 8a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
      </svg>
    ),
  },
  {
    path: "/runs",
    label: "Runs",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
  {
    path: "/monitor",
    label: "Monitor",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
        <path
          fillRule="evenodd"
          d="M3.707 2.293a1 1 0 00-1.414 1.414l14 14a1 1 0 001.414-1.414l-1.473-1.473A10.014 10.014 0 0019.542 10C18.268 5.943 14.478 3 10 3a9.958 9.958 0 00-4.512 1.074l-1.78-1.781zm4.261 4.26l1.514 1.515a2.003 2.003 0 012.45 2.45l1.514 1.514a4 4 0 00-5.478-5.478z"
          clipRule="evenodd"
        />
        <path d="M12.454 16.697L9.75 13.992a4 4 0 01-3.742-3.741L2.335 6.578A9.98 9.98 0 00.458 10c1.274 4.057 5.065 7 9.542 7 .847 0 1.669-.105 2.454-.303z" />
      </svg>
    ),
  },
];

function PageTitle() {
  const { pathname } = useLocation();
  const titles: Record<string, string> = {
    "/dashboard": "Dashboard",
    "/agents": "Agents",
    "/workflows": "Workflows",
    "/runs": "Runs",
    "/monitor": "Monitor",
  };
  const key = Object.keys(titles).find((k) => pathname.startsWith(k));
  return <span>{key ? titles[key] : "Agent Platform"}</span>;
}

export default function Layout() {
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const { pathname } = useLocation();

  useEffect(() => {
    const base = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
    fetch(`${base}/health`)
      .then((r) => setApiOk(r.ok))
      .catch(() => setApiOk(false));
  }, []);

  return (
    <div className="flex h-screen bg-[#0f1117] overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 flex flex-col border-r border-[#2e3149] bg-[#1a1d27]">
        {/* Logo */}
        <div className="flex items-center gap-2 px-5 py-5 border-b border-[#2e3149]">
          <div className="w-7 h-7 rounded-lg bg-[#6c63ff] flex items-center justify-center">
            <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
              <path d="M13 6a3 3 0 11-6 0 3 3 0 016 0zM18 8a2 2 0 11-4 0 2 2 0 014 0zM14 15a4 4 0 00-8 0v1h8v-1zM6 8a2 2 0 11-4 0 2 2 0 014 0zM16 18v-1a5.972 5.972 0 00-.75-2.906A3.005 3.005 0 0119 15v1h-3zM4.75 14.094A5.973 5.973 0 004 17v1H1v-1a3 3 0 013.75-2.906z" />
            </svg>
          </div>
          <span className="font-semibold text-[#e8eaf0] text-sm tracking-wide">Agent Platform</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5">
          {NAV.map((item) => {
            const active = pathname.startsWith(item.path);
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={`relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150
                  ${active
                    ? "bg-[#6c63ff]/20 text-white border border-[#6c63ff]/30"
                    : "text-[#6b7280] hover:bg-[#252836] hover:text-[#c4c8e0] border border-transparent"
                  }`}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-[#6c63ff] rounded-r" />
                )}
                <span className={active ? "text-[#a5b4fc]" : ""}>{item.icon}</span>
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        {/* API status */}
        <div className="px-4 py-4 border-t border-[#2e3149]">
          <div className="flex items-center gap-2 text-xs text-[#7b7f9e]">
            <span
              className={`w-2 h-2 rounded-full ${
                apiOk === null ? "bg-[#7b7f9e]" : apiOk ? "bg-[#22c55e]" : "bg-[#ef4444]"
              }`}
            />
            {apiOk === null ? "Checking..." : apiOk ? "API Connected" : "API Offline"}
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="h-16 flex items-center px-6 border-b border-[#2e3149] bg-[#1a1d27] flex-shrink-0">
          <h1 className="text-white font-bold text-lg tracking-tight">
            <PageTitle />
          </h1>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
