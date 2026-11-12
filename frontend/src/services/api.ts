/**
 * Accès à l'API VERITAS.
 *
 * Deux adresses distinctes :
 * - côté serveur (composants serveur Next.js) : API_INTERNAL_URL, lue à l'exécution.
 *   En Docker Compose, c'est le nom du service (http://backend:8000).
 * - côté navigateur : NEXT_PUBLIC_API_URL, figée au moment du build.
 */

export type ReadinessStatus = {
  status: "ready" | "degraded";
  application: string;
  version: string;
  database: "up" | "down";
};

export type BackendCheck =
  | { reachable: true; readiness: ReadinessStatus }
  | { reachable: false; error: string };

export function serverApiUrl(): string {
  return process.env.API_INTERNAL_URL ?? "http://localhost:8000";
}

/** Interroge /api/v1/health/ready. Ne lève jamais d'exception : l'échec est une donnée. */
export async function checkBackend(): Promise<BackendCheck> {
  try {
    const response = await fetch(`${serverApiUrl()}/api/v1/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    // 503 est une réponse attendue quand la base est indisponible : le corps reste lisible.
    if (!response.ok && response.status !== 503) {
      return { reachable: false, error: `Réponse HTTP ${response.status}` };
    }
    return { reachable: true, readiness: (await response.json()) as ReadinessStatus };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Erreur inconnue";
    return { reachable: false, error: message };
  }
}
