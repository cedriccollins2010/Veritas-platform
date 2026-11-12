# ADR-0001 — Choix du Sprint 1

Date : 2026-11-11 · Statut : accepté

## Contexte

Le Sprint 1 met en place le socle : API, interface, base de données et environnement local. Plusieurs choix de détail n'étaient pas tranchés par les documents de conception.

## Décisions

1. **Deux points de santé.** `GET /health` répond dès que le processus tourne (utilisé par Docker). `GET /api/v1/health/ready` vérifie aussi PostgreSQL et répond 503 si la base est absente. Séparer les deux évite qu'une base momentanément indisponible fasse redémarrer l'API en boucle.
2. **Moteur SQLAlchemy créé à la demande.** L'application démarre même sans base ; seules les routes qui en ont besoin échouent.
3. **Migration 0001 écrite en SQL.** Le schéma complet du document de référence est créé d'un coup, y compris les contraintes `CHECK` et le déclencheur append-only. Les modèles ORM viendront en phase 2 ; d'ici là, l'autogénération Alembic est désactivée.
4. **Le journal de possession est protégé par la base.** Un déclencheur refuse toute modification ou suppression de `custody_events`. Une erreur dans le code applicatif ne peut donc pas réécrire l'historique. Cela ne protège pas contre un administrateur de la base : c'est le rôle de l'ancrage externe (phase 3).
5. **Le frontend lit l'API côté serveur.** La page d'accueil interroge l'API depuis le serveur Next.js (`API_INTERNAL_URL`), ce qui fonctionne dans Docker sans exposer l'API au navigateur. Le CORS est néanmoins configuré, avec `allow_credentials`, pour les futurs appels authentifiés par cookie.
6. **Aucune ressource tierce dans l'interface.** Les polices Google générées par défaut ont été retirées.
7. **Conteneurs sans root, ports liés à 127.0.0.1.** L'environnement local n'est pas joignable depuis le réseau.

## Conséquences

- Toute migration future doit passer `upgrade → downgrade → upgrade` (vérifié en CI).
- Les tests d'intégration sont ignorés sans PostgreSQL ; la CI les exécute toujours.
