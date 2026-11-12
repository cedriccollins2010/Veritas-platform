# ADR-0003 — Authentification par cookie de session

Date : 2026-11-12 · Statut : accepté · Issue : #3

## Contexte

Le document de référence impose un cookie de session `HttpOnly`, `Secure`, `SameSite`, une protection CSRF, et aucun jeton stocké dans le navigateur. Il fallait choisir comment hacher les mots de passe, comment représenter la session et comment se protéger du CSRF.

## Décisions

1. **Mots de passe : Argon2id via `argon2-cffi` (25.1.0)**, avec les paramètres par défaut de la bibliothèque (profil de la RFC 9106 : 64 Mio, 3 passes, 4 fils). Argon2id est recommandé par l'OWASP ; il est coûteux en mémoire, ce qui freine les attaques sur carte graphique. Écartés : `bcrypt` (plus ancien, tronque au-delà de 72 octets) et `passlib` (n'est plus maintenu). À chaque connexion réussie, une empreinte calculée avec des paramètres dépassés est recalculée.
2. **Session côté serveur.** Le jeton est 32 octets aléatoires (`secrets.token_urlsafe`). La base ne stocke que son empreinte SHA-256 (`sessions.token_hash`) : lire la table ne permet pas de se faire passer pour quelqu'un. SHA-256 suffit ici, contrairement aux mots de passe, parce que le jeton est aléatoire sur 256 bits et ne peut pas être deviné.
3. **Cookie de session** `HttpOnly`, `SameSite=Lax`, `Path=/`, durée `SESSION_LIFETIME_HOURS` (12 h par défaut). `Secure` et préfixe `__Host-` partout sauf en développement (HTTP local). `Lax` plutôt que `Strict` : un lien vers VERITAS reçu par courriel ouvre la session de l'utilisateur.
4. **CSRF : double soumission signée.** Le jeton CSRF vaut `HMAC-SHA256(clé = jeton de session, "veritas-csrf-v1")`. Il est remis dans un second cookie lisible par JavaScript (et dans la réponse de `/auth/me`) ; le frontend le renvoie dans l'en-tête `X-CSRF-Token`. Le serveur le recalcule à partir du cookie de session. Avantages : aucun secret serveur à gérer, aucune colonne en base, et un jeton CSRF volé ne vaut que pour une session et ne révèle pas le jeton de session.
5. **La garde CSRF est posée une fois, sur le routeur `/api/v1`**, et non route par route : une route future ne peut pas l'oublier. Exceptions explicites : `/auth/register` et `/auth/login`, faites sans session ; elles exigent un corps JSON (un formulaire HTML ne peut pas en envoyer) et, si le navigateur l'indique, une origine autorisée (`CORS_ORIGINS`). Un test vérifie que toute autre route d'écriture répond 403 sans jeton.
6. **Mêmes réponses pour tous les échecs de connexion.** Courriel inconnu, mauvais mot de passe et compte désactivé donnent la même réponse 401. Pour un courriel inconnu, une vérification Argon2 factice est quand même faite, pour que le temps de réponse ne révèle pas l'existence du compte.
7. **Journal.** Inscription, connexion (réussie ou refusée) et déconnexion sont écrites dans `access_logs`, dans la même transaction que l'opération. Ni mot de passe, ni jeton, ni courriel saisi lors d'un échec n'y figure.
8. **Organisation courante** : la dépendance `CurrentOrganization` renvoie l'organisation personnelle. Quand un utilisateur pourra appartenir à plusieurs organisations, elle lira l'organisation choisie dans la requête et vérifiera l'appartenance.

## Conséquences

- Les routes protégées déclarent `CurrentUser` ou `CurrentOrganization` (`app/auth/dependencies.py`) et répondent 401 sans session valide.
- L'inscription révèle qu'un courriel a déjà un compte (409). C'est inévitable sans vérification de l'adresse par courriel (phase 5).
- Reste à faire en phase 5 : limitation du nombre d'essais de connexion, MFA, vérification de l'adresse, réinitialisation du mot de passe, purge des sessions expirées, prise en compte de l'adresse IP réelle derrière un proxy.
