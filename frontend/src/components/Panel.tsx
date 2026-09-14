import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  kicker?: string;
  children: ReactNode;
  className?: string;
}

export default function Panel({ title, kicker, children, className = "" }: PanelProps) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        {kicker && <p className="panel-kicker">{kicker}</p>}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}
