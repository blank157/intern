/** STYLE: Integrated dark dashboard column — the charcoal navigation is a continuous material of the main EvalAI shell, with compact Inter labels and subtle selected rows. */
import { Activity, ChartNoAxesCombined, ClipboardCheck, Home, Monitor, SlidersHorizontal, X } from "lucide-react";
import { useLocation } from "wouter";

const markUrl = "/manus-storage/ocr-mark_cbb7933a.png";
const navigation = [
  { label: "Dashboard", href: "/", icon: Home },
  { label: "Configure", href: "/configure", icon: SlidersHorizontal },
  { label: "Evaluation", href: "/evaluation", icon: Activity },
  { label: "Results", href: "/results", icon: ClipboardCheck },
  { label: "Analytics", href: "/analytics", icon: ChartNoAxesCombined },
  { label: "Computers", href: "/computers", icon: Monitor },
];

interface SidebarProps { mobileOpen: boolean; onCloseMobile: () => void; }

export function Sidebar({ mobileOpen, onCloseMobile }: SidebarProps) {
  const [location, setLocation] = useLocation();
  const navigate = (item: (typeof navigation)[number]) => { setLocation(item.href); onCloseMobile(); };
  const isActive = (href: string) => href === location || (href !== "/" && location.startsWith(`${href}/`));

  return <aside aria-label="Dashboard navigation" className={`fixed inset-y-0 left-0 z-40 w-[232px] bg-[#11100f] p-3 text-white shadow-[18px_0_46px_rgba(13,12,12,0.35)] transition-transform duration-200 dark:bg-[#0b0b0b] md:sticky md:top-0 md:h-dvh md:w-[228px] md:translate-x-0 md:self-start md:p-0 md:shadow-none ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden rounded-[27px] border border-white/[0.06] bg-[radial-gradient(circle_at_10%_-10%,rgba(255,255,255,0.15),transparent_30%),linear-gradient(145deg,#2c2827_0%,#211d1c_46%,#282220_100%)] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.09),0_14px_30px_rgba(0,0,0,0.28)] md:rounded-none md:border-0 md:shadow-none">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-[linear-gradient(125deg,rgba(255,255,255,0.08),transparent_54%)]" />
      <div className="relative flex items-center justify-between gap-2">
        <button type="button" onClick={() => { setLocation("/"); onCloseMobile(); }} aria-label="Go to EvalAI dashboard" className="flex items-center gap-2.5 rounded-xl text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white shadow-[0_2px_8px_rgba(0,0,0,0.28)]"><img src={markUrl} alt="EvalAI" className="h-6 w-6 object-contain" /></span>
          <span className="text-[15px] font-semibold tracking-[-0.04em] text-white">EvalAI</span>
        </button>
        <button type="button" onClick={onCloseMobile} aria-label="Close navigation" className="rounded-lg p-1.5 text-white/75 hover:bg-white/[0.08] md:hidden"><X className="h-3.5 w-3.5" /></button>
      </div>

      <nav className="relative mt-6 flex flex-col gap-1.5" aria-label="Workspace sections">
        {navigation.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          return <button key={item.label} type="button" onClick={() => navigate(item)} aria-current={active ? "page" : undefined} className={`group flex h-10 w-full items-center gap-3 rounded-xl px-3 text-left transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white ${active ? "bg-[linear-gradient(100deg,rgba(255,255,255,0.19),rgba(255,255,255,0.055))] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_6px_14px_rgba(0,0,0,0.18)]" : "text-white/58 hover:bg-white/[0.07] hover:text-white/92"}`}><span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full border ${active ? "border-white/[0.16] bg-white/[0.14] text-white" : "border-white/[0.08] bg-black/[0.12] text-white/68 group-hover:border-white/[0.14] group-hover:text-white"}`}><Icon className="h-[13px] w-[13px]" strokeWidth={active ? 2.1 : 1.7} /></span><span className="text-[13px] font-semibold tracking-[-0.02em]">{item.label}</span></button>;
        })}
      </nav>

    </div>
  </aside>;
}
