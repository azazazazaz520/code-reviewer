import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";

interface SectionCardProps {
  title: string;
  description: string;
  children: ReactNode;
}

export default function SectionCard({ title, description, children }: SectionCardProps) {
  return (
    <Card className="border-border/80 shadow-sm">
      <CardHeader className="border-b border-border/70 pb-4">
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription className="leading-6">{description}</CardDescription>
      </CardHeader>
      <CardContent className="pt-1">{children}</CardContent>
    </Card>
  );
}
