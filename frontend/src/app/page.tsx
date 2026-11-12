import { Suspense } from "react";

import SystemStatus from "@/components/common/SystemStatus";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-10 px-6 py-16">
      <header className="flex flex-col gap-3">
        <p className="text-sm font-semibold uppercase tracking-widest opacity-60">
          Sprint 1 · Socle technique
        </p>
        <h1 className="text-4xl font-semibold tracking-tight">VERITAS</h1>
        <p className="text-lg opacity-80">
          Constitution et vérification indépendante de dossiers de preuve numérique.
        </p>
      </header>

      <section className="flex flex-col gap-2">
        <h2 className="text-xl font-semibold">État du système</h2>
        <Suspense fallback={<p className="py-3 opacity-60">Vérification en cours…</p>}>
          <SystemStatus />
        </Suspense>
      </section>
    </main>
  );
}
