import { DesktopLogin } from "@/components/desktop-login";

export const metadata = { title: "TabForge" };

/** Opened by the desktop launcher with `#token=<per-start token>` (ADR-0008). */
export default function DesktopPage() {
  return (
    <div className="page narrow">
      <DesktopLogin />
    </div>
  );
}
