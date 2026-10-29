import "./new.css";

export const metadata = { title: "Controller observability study" };

export default function NewLayout({ children }: { children: React.ReactNode }) {
  return <div className="new-ui min-h-screen">{children}</div>;
}
