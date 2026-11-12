import { connection } from "next/server";

import { checkBackend } from "@/services/api";

type Row = { label: string; ok: boolean; detail: string };

function StatusRow({ label, ok, detail }: Row) {
  return (
    <li className="flex items-center justify-between gap-4 py-3">
      <span className="font-medium">{label}</span>
      <span className="flex items-center gap-2 text-sm">
        <span
          aria-hidden="true"
          className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`}
        />
        <span>{detail}</span>
      </span>
    </li>
  );
}

/** Vérifie à chaque requête que le frontend joint l'API et que l'API joint PostgreSQL. */
export default async function SystemStatus() {
  await connection(); // rendu à la requête, jamais figé au build

  const check = await checkBackend();
  const rows: Row[] = check.reachable
    ? [
        { label: "Frontend → API", ok: true, detail: `VERITAS API ${check.readiness.version}` },
        {
          label: "API → PostgreSQL",
          ok: check.readiness.database === "up",
          detail: check.readiness.database === "up" ? "Connectée" : "Indisponible",
        },
      ]
    : [
        { label: "Frontend → API", ok: false, detail: check.error },
        { label: "API → PostgreSQL", ok: false, detail: "Non vérifiable" },
      ];

  return (
    <ul className="divide-y divide-black/10 dark:divide-white/15" aria-label="État du système">
      {rows.map((row) => (
        <StatusRow key={row.label} {...row} />
      ))}
    </ul>
  );
}
