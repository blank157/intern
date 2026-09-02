/**
 * STYLE: Reference-led soft glass shell — the entire product sits within a large, frosted central workspace panel.
 */
import { ReactNode, useState } from "react";
import { useLocation } from "wouter";
import { AppHeader } from "./AppHeader";
import { Sidebar } from "./Sidebar";

interface AppShellProps { children: ReactNode; onClearComparison: () => void; }

export function AppShell({ children, onClearComparison }: AppShellProps) {
  const [location] = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const activePage = location === "/configure" ? "configure" : location === "/compare" ? "compare" : location.startsWith("/results") ? "results" : location.startsWith("/analytics") ? "analytics" : location === "/evaluation" ? "evaluation" : location === "/computers" ? "computers" : location === "/settings" ? "settings" : "home";

  return (
    <div className="relative min-h-dvh bg-[linear-gradient(145deg,#dfe3fb_0%,#eef0ff_37%,#f7f8ff_68%,#dfe2fb_100%)] px-0 py-0 text-[#171827] dark:bg-[#0e101b] dark:text-[#f7f7fb] sm:px-5 sm:py-5 lg:px-8 lg:py-7">
      <div className="pointer-events-none fixed inset-0 opacity-80 [background-image:radial-gradient(circle_at_7%_11%,rgba(255,255,255,0.92),transparent_26%),radial-gradient(circle_at_84%_8%,rgba(255,252,233,0.72),transparent_25%),radial-gradient(circle_at_70%_94%,rgba(196,207,255,0.45),transparent_30%),linear-gradient(116deg,transparent_11%,rgba(119,136,255,0.12)_11.1%,transparent_11.3%)] dark:opacity-20" />
      {mobileOpen && <button type="button" aria-label="Close navigation" className="fixed inset-0 z-30 bg-[#101329]/35 backdrop-blur-[2px] md:hidden" onClick={() => setMobileOpen(false)} />}
      <div className="relative mx-auto flex min-h-dvh max-w-[1460px] overflow-clip border border-white/60 bg-white/[0.14] shadow-[0_30px_85px_rgba(55,65,126,0.15)] backdrop-blur-[18px] dark:border-white/10 dark:bg-[#171927]/28 sm:min-h-[calc(100dvh-40px)] sm:rounded-[32px] lg:min-h-[calc(100dvh-56px)]">
        <Sidebar mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />
        <div className="flex min-w-0 flex-1 flex-col border-l border-black/[0.18] dark:border-white/[0.08]">
          <AppHeader activePage={activePage} onOpenNavigation={() => setMobileOpen(true)} onClearComparison={onClearComparison} />
          <main className={`min-w-0 flex-1 p-3 sm:p-5 lg:p-6 ${activePage === "configure" || activePage === "evaluation" ? "lg:flex lg:flex-col lg:pb-0" : ""}`}>{children}</main>
        </div>
      </div>
    </div>
  );
}
