import "./new.css";
import { NewNav } from "@/components/new-ui/new-nav";

export const metadata = { title: "Controller observability study" };

export default function NewLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="new-ui min-h-screen">
      <NewNav />
      <main className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8">{children}</main>
    </div>
  );
}
