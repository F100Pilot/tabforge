import { AccountPanel } from "@/components/account-panel";

export const metadata = { title: "Conta · TabForge" };

export default function AccountPage() {
  return (
    <div className="page narrow">
      <h1>Conta</h1>
      <AccountPanel />
    </div>
  );
}
