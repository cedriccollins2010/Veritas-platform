import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VERITAS",
  description: "Constitution et vérification indépendante de dossiers de preuve numérique",
};

// Pas de police Google : aucune requête vers un tiers au chargement de la page.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" className="h-full antialiased">
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
