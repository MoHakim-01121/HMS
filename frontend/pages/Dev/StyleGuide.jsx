import { useState } from "react";
import { Button } from "@/components/shadcn/ui/button.jsx";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/shadcn/ui/card.jsx";
import { Badge } from "@/components/shadcn/ui/badge.jsx";
import { Input } from "@/components/shadcn/ui/input.jsx";

const SWATCHES = [
  { name: "background", var: "--background" },
  { name: "foreground", var: "--foreground" },
  { name: "primary", var: "--primary" },
  { name: "primary-foreground", var: "--primary-foreground" },
  { name: "secondary", var: "--secondary" },
  { name: "muted", var: "--muted" },
  { name: "muted-foreground", var: "--muted-foreground" },
  { name: "destructive", var: "--destructive" },
  { name: "border", var: "--border" },
];

function Swatch({ name, value }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ width: 40, height: 40, borderRadius: 8, background: value, border: "1px solid var(--border)", flexShrink: 0 }} />
      <div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{name}</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted-foreground)" }}>{value}</div>
      </div>
    </div>
  );
}

function Panel({ theme }) {
  const [text, setText] = useState("");
  return (
    <div data-theme={theme} style={{ background: "var(--background)", color: "var(--foreground)", padding: 32, borderRadius: 16, flex: 1, minWidth: 0 }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "var(--muted-foreground)", marginBottom: 16 }}>
        {theme} mode
      </div>

      <h2 style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 600, marginBottom: 24 }}>
        Aa — Playfair Display / IBM Plex Mono
      </h2>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 24 }}>
        {SWATCHES.map((s) => (
          <Swatch key={s.name} name={s.name} value={`var(${s.var})`} />
        ))}
      </div>

      <Card style={{ marginBottom: 16 }}>
        <CardHeader>
          <CardTitle>Sample card</CardTitle>
        </CardHeader>
        <CardContent style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="destructive">Destructive</Button>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Badge>Default</Badge>
            <Badge variant="secondary">Secondary</Badge>
            <Badge variant="destructive">Destructive</Badge>
          </div>
          <Input placeholder="Sample input…" value={text} onChange={(e) => setText(e.target.value)} />
        </CardContent>
      </Card>
    </div>
  );
}

export default function StyleGuide() {
  return (
    <div style={{ padding: 24, display: "flex", gap: 24, flexWrap: "wrap", minHeight: "100vh", background: "#111" }}>
      <Panel theme="light" />
      <Panel theme="dark" />
    </div>
  );
}

StyleGuide.layout = (page) => page;
