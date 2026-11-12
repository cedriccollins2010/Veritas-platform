<!--
Export Markdown du Document de référence unifié (doc Claude, révision 19, exporté le 2026-11-12).
Ne pas modifier ce fichier à la main : modifier le doc, puis l'exporter de nouveau (Exporter → Markdown).
Le schéma d'architecture intégré au doc n'est pas exportable ; il est remplacé par une mention.
-->

# VERITAS — Document de référence unifié

Nov 11, 2026

Ce document remplace le cahier des charges, le TDD v1.0, le blueprint d'implémentation et la note de stratégie : VERITAS démarre comme outil de preuve numérique pour la criminalistique informatique, construit par une seule personne, et son MVP doit permettre à un tiers de vérifier un dossier sans le serveur VERITAS.

## Arbitrages

Les quatre documents se contredisaient sur sept points. La note de stratégie, la plus récente, l'emporte sauf mention contraire. Chaque ligne est une proposition à confirmer ou à renverser.

| Sujet | Ce que disaient les documents | Décision retenue |
| --- | --- | --- |
| Prochaine étape | Blueprint : lancer le Sprint 1. Stratégie : ne pas coder, écrire le PRD. | Les deux en parallèle. Le socle technique (Sprint 1) ne dépend d'aucune décision produit ; les entretiens utilisateurs et le PRD doivent être terminés avant la phase 2. |
| Utilisateurs cibles | Cahier des charges : particuliers, juristes, assureurs, entreprises. Stratégie : forensic d'abord. | Analystes forensic, consultants en réponse aux incidents et experts indépendants. Les autres segments sont reportés. |
| Durée du MVP | 5 à 8 semaines (blueprint), 6 à 10 (cahier des charges), 11 à 20 (stratégie). | 11 à 20 semaines à temps plein. Les estimations courtes omettent la validation RFC 3161 complète et le vérificateur autonome. |
| Vérification | Blueprint : `POST /verify` côté serveur, résultat écrit en base. Principe affiché : vérification sans VERITAS. | Le vérificateur en ligne de commande est le composant de référence et fait partie du MVP. Le portail web appelle la même bibliothèque. |
| Authentification | TDD : jeton `Bearer`. Frontend : cookies. | Cookie de session `HttpOnly`, `Secure`, `SameSite`, avec protection CSRF. Aucun jeton stocké dans le navigateur. |
| Format du dossier | Deux arborescences différentes (TDD et stratégie). | L'arborescence de la stratégie, versionnée (voir Moteur de preuve). |
| Organisations | Schéma : `organization_id` nullable. Stratégie : isolation stricte dès les fondations. | `organization_id` obligatoire. Une organisation personnelle est créée à l'inscription. |

Deux écarts mineurs sont aussi corrigés : la table `certificates` annoncée dans le cahier des charges n'existait pas dans le schéma, et l'endpoint `POST /evidence/{id}/timestamp` avait disparu du TDD alors qu'il sert à relancer un horodatage échoué.

## Vision, promesse et limites

VERITAS permet de démontrer, de manière indépendante et vérifiable, trois propriétés d'un élément numérique : son intégrité, son existence à une date donnée et la traçabilité des opérations qu'il a subies.

Ce que le produit ne prétend pas prouver, et que l'interface et les rapports doivent rappeler :

- **La véracité du contenu.** Une empreinte valide dit que le fichier n'a pas changé, pas que ce qu'il affirme est vrai.
- **L'identité de l'auteur.** SHA-256 détecte une modification, il ne dit pas qui a créé le fichier.
- **La date de création.** Un jeton RFC 3161 établit que l'empreinte existait au plus tard à l'instant attesté par la TSA.
- **La recevabilité juridique.** Elle dépend du tribunal et de la juridiction ; un avis juridique est requis avant toute promesse commerciale sur ce point.

Six principes guident toutes les décisions :

1. La preuve avant l'IA : la certification reste déterministe et reproductible, sans modèle d'IA dans son cœur.
2. La vérification doit survivre à VERITAS : un dossier exporté se vérifie sans interroger le serveur.
3. La simplicité architecturale : monolithe modulaire, pas de microservices, de Kubernetes ni de blockchain dans le MVP.
4. La sécurité dès la conception.
5. L'interopérabilité : format de dossier documenté et versionné, API versionnée.
6. La transparence des limites.

## Positionnement et marché

L'ambition est mondiale, mais le produit se déploie en trois phases et ne vend d'abord qu'à un seul segment.

| Phase | Produit | Utilisateurs | Horizon indicatif |
| --- | --- | --- | --- |
| 1 | VERITAS Forensic : constitution, conservation et vérification de dossiers de preuve | Analystes forensic, consultants en réponse aux incidents, experts indépendants | Année 1 |
| 2 | VERITAS Enterprise : collaboration, gouvernance, audit, API, intégrations | Entreprises, assureurs, cabinets juridiques, équipes de conformité | Année 2 |
| 3 | VERITAS Trust Network : protocoles et outils pour produire et vérifier des preuves entre organisations | Institutions, gouvernements, éditeurs, développeurs | Année 3 |

La différenciation ne vient pas de SHA-256, que n'importe quel outil calcule. Elle repose sur quatre piliers : le passeport de preuve (un dossier structuré et transportable), la vérification indépendante, un format documenté que d'autres plateformes peuvent lire, et une chronologie dont les modifications sont détectables.

### Modèle économique

Le modèle est un SaaS professionnel complété par une offre API. Les prix ne sont pas fixés tant que le coût réel des horodatages, du stockage et du soutien n'est pas mesuré.

| Offre | Clientèle | Revenus |
| --- | --- | --- |
| Starter | Expert indépendant | Gratuit ou limité |
| Professional | Consultant, petite équipe | Abonnement mensuel |
| Enterprise | Organisation | Contrat annuel |
| API | Éditeur logiciel, plateforme | Paiement à l'usage |
| Private deployment | Grande institution | Licence et services d'intégration |

Les variables tarifaires envisagées sont le nombre de dossiers actifs, le volume de stockage, le nombre d'utilisateurs et d'horodatages, la durée de conservation et le niveau de service.

## Périmètre du MVP

Le MVP fait une seule chose de bout en bout : transformer un fichier en dossier de preuve qu'un tiers vérifie seul.

| Dans le MVP | Après validation du MVP | Vision à long terme |
| --- | --- | --- |
| Compte, authentification, organisation personnelle | Organisations à plusieurs membres, rôles et permissions | Vérification interorganisationnelle |
| Téléversement de tout type de fichier (500 Mo, configurable), ou empreinte seule calculée en local | Téléversement reprenable pour les très gros fichiers | Certification de lots, arbres de Merkle |
| Empreinte SHA-256 calculée en flux | Plusieurs fichiers par dossier | Plusieurs algorithmes |
| Horodatage RFC 3161 auprès d'une TSA externe, vérifié | Plusieurs fournisseurs TSA | Passeport de preuve publié comme spécification ouverte |
| Journal d'événements chaîné | Rétention immuable, ancrage externe périodique, MFA | Connecteurs SIEM, EDR, gestion documentaire |
| Manifeste JSON versionné et export du dossier | API publique, partage sécurisé | Déploiement privé par juridiction |
| Vérificateur autonome en ligne de commande, et portail web sans compte | Rapport PDF, tableau de bord avancé | Assistance IA au classement, hors certification |

Exclus du MVP sans exception : blockchain, modèle d'IA, microservices, Kubernetes, autorité d'horodatage propriétaire, détection de deepfakes.

Le rapport PDF et le tableau de bord passent en priorité P2 : le manifeste JSON et le vérificateur suffisent à démontrer la valeur, et un rapport lisible peut être généré par le vérificateur lui-même.

## Architecture

VERITAS est un monolithe modulaire : une seule application FastAPI, dont les modules sont des packages Python aux responsabilités séparées.

[Schéma d'architecture intégré au doc · serveur à gauche, vérification indépendante à droite]

Le serveur crée, conserve et exporte les dossiers ; le vérificateur ne lit que le passeport exporté. Le module `verification` du serveur et le vérificateur autonome partagent la même bibliothèque.

| Composant | Technologie |
| --- | --- |
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Base de données | PostgreSQL 16 |
| Stockage | Compatible S3, privé, chiffré au repos |
| Cryptographie | Bibliothèque `cryptography`, SHA-256 |
| Horodatage | RFC 3161 via TSA externe (DigiCert au pilote), bibliothèque rfc3161-client |
| Tests | Pytest, tests frontend |
| Environnement | Docker Compose en local ; GitHub Actions pour la CI |

| Module | Responsabilité |
| --- | --- |
| `auth` | Connexion, sessions, MFA plus tard |
| `organizations` | Organisations, membres, rôles |
| `evidence` | Création et gestion des dossiers |
| `storage` | Conservation des fichiers |
| `crypto` | Empreintes et validation cryptographique |
| `timestamp` | Communication avec les TSA |
| `custody` | Journal et chaîne de possession |
| `verification` | Vérification des dossiers |
| `reports` | Manifeste, export, rapports |
| `audit` | Journaux d'accès et opérations sensibles |

Les routes API ne contiennent pas la logique métier, elles appellent ces services. Un module n'empiète pas sur un autre : `evidence` n'implémente aucun algorithme cryptographique, `timestamp` ne gère aucun utilisateur.

Quatre décisions préparent l'international sans coût aujourd'hui : dates stockées en UTC, interface en français et en anglais, algorithme et version enregistrés dans chaque dossier, API et format d'export versionnés. Une application accessible depuis plusieurs pays n'est pas pour autant conforme à leurs lois ; chaque juridiction devra être examinée.

## Moteur de preuve

Le moteur enchaîne quatre mécanismes, et chacun produit un artefact que le vérificateur recontrôle sans le serveur.

### Empreinte

SHA-256 est calculé en flux, par blocs de 1 Mo, sur le fichier original non modifié. Chaque empreinte enregistre son algorithme, son encodage et la version du moteur. Une nouvelle empreinte n'écrase jamais une empreinte historique.

### Horodatage RFC 3161

L'empreinte est envoyée à une TSA externe derrière l'interface `TimestampProvider`, qui permet de changer de fournisseur sans toucher au reste. La requête et la réponse originales sont conservées. La validation contrôle le statut, l'empreinte incluse, le nonce, la signature, l'identité de la TSA, le policy OID, la chaîne de certificats et les informations de révocation disponibles.

Une panne de la TSA ne fait perdre ni le fichier ni l'empreinte : la preuve reste à l'état `TIMESTAMP_PENDING` et l'horodatage est relancé. Un jeton non vérifiable n'est jamais présenté comme une certification.

### Chaîne de possession

Chaque événement porte l'empreinte du précédent : H(n) = SHA-256(H(n-1) || C(E(n))), où C est la représentation canonique de l'événement. Trois règles complètent le code du blueprint :

- La sérialisation canonique suit RFC 8785 (JCS), et non `json.dumps` avec tri des clés, qui ne normalise ni les nombres ni Unicode.
- La liste exacte des champs hachés est figée dans la spécification : identifiants, type, acteur, date UTC, numéro de séquence, données.
- L'insertion verrouille la preuve dans la transaction, pour que deux événements simultanés ne reçoivent pas le même numéro de séquence.

Une chaîne conservée dans la seule base de données ne résiste pas à un administrateur malveillant, qui peut la réécrire en entier. Le MVP ancre donc la tête de chaîne de chaque dossier par un horodatage RFC 3161 au moment de l'export. L'ancrage périodique par lots et la rétention immuable viennent ensuite.

### Passeport de preuve

Le dossier exporté est une archive autonome dont le manifeste décrit tout le contenu.

```text
VERITAS-EVIDENCE/
├── manifest.json
├── original/
│   └── document.pdf
├── cryptographic/
│   ├── sha256.txt
│   └── hash-metadata.json
├── timestamp/
│   ├── timestamp-request.tsq
│   ├── timestamp-response.tsr
│   └── tsa-certificates/
├── custody/
│   └── custody-events.json
└── report/
    └── report.pdf        (optionnel, P2)
```

Le manifeste porte un numéro de version de format, les identifiants, les empreintes, les algorithmes, les dates, les références aux jetons et la tête de chaîne. Son empreinte est calculée en excluant son propre champ de checksum. Le dossier `validation/` des versions précédentes est retiré : un résultat de vérification produit par le serveur n'a pas sa place dans un dossier que le destinataire doit vérifier lui-même.

### Vérificateur autonome

Le vérificateur est une bibliothèque Python avec une commande en ligne, `veritas verify <dossier>`, sans accès réseau au serveur VERITAS. Le portail web appelle la même bibliothèque. Il rend un résultat par contrôle, jamais un verdict global qui masquerait un doute.

| Contrôle | Résultats possibles |
| --- | --- |
| Format et intégrité du manifeste | PASS / FAIL |
| Intégrité du fichier | PASS / FAIL |
| Jeton d'horodatage | PASS / FAIL / UNKNOWN |
| Chaîne de certificats | PASS / FAIL / UNKNOWN |
| Chaîne de possession | PASS / FAIL |
| Complétude du dossier | COMPLETE / INCOMPLETE |

`UNKNOWN` s'applique quand l'information manque pour conclure, par exemple une révocation non consultable hors ligne. Le statut global n'est `VALID` que si tous les contrôles obligatoires sont `PASS`.

## Modèle de données et API

Le script SQL du blueprint (section 3.2) reste la base de la première migration, avec les neuf corrections ci-dessous. Les identifiants sont des UUID et les dates des `TIMESTAMPTZ` en UTC.

| Table | Rôle |
| --- | --- |
| `users` | Comptes |
| `organizations`, `organization_members` | Organisations, appartenance et rôle |
| `sessions` | Sessions serveur (nouvelle table) |
| `evidence` | Dossier de preuve et son état |
| `evidence_files` | Fichier original et métadonnées |
| `hash_records` | Empreintes |
| `timestamp_records` | Jetons d'horodatage |
| `custody_events` | Chaîne de possession |
| `verification_records` | Résultats de vérification |
| `access_logs` | Journal des accès |

### Corrections au schéma

1. `evidence.organization_id` devient `NOT NULL`, avec un index, et chaque requête filtre sur l'organisation.
2. `hash_records` reçoit une contrainte `UNIQUE (file_id, algorithm)` : la contrainte actuelle, qui inclut `digest`, autorise deux empreintes différentes pour le même fichier et le même algorithme. Une colonne `engine_version` est ajoutée.
3. `timestamp_records` reçoit `request_storage_key`, `policy_oid`, `serial_number` et `purpose` (`FILE` ou `CHAIN_HEAD`).
4. `custody_events` reçoit `occurred_at`, la date incluse dans l'empreinte. `created_at`, rempli par la base, n'est pas haché.
5. Le rôle PostgreSQL de l'application n'a ni `UPDATE` ni `DELETE` sur `custody_events`, et un déclencheur refuse ces opérations.
6. Les colonnes `status`, `role`, `validation_status` et les résultats de vérification reçoivent des contraintes `CHECK` sur leurs valeurs.
7. `access_logs` reçoit `organization_id`, l'adresse IP et le résultat de l'action.
8. La table `certificates` du cahier des charges est abandonnée : les certificats TSA sont conservés avec le jeton dans le stockage objet.
9. Aucune suppression en cascade sur les dossiers certifiés.

### États d'une preuve

Une preuve passe par `RECEIVED`, `PROCESSING`, `HASHED`, `TIMESTAMP_PENDING` puis `CERTIFIED`, avec `FAILED` et `ARCHIVED` comme états de sortie. `CERTIFIED` n'est attribué qu'après validation complète du jeton.

### API REST

Toutes les routes sont préfixées par `/api/v1` et documentées par OpenAPI.

| Méthode | Endpoint | Fonction |
| --- | --- | --- |
| POST | `/auth/register`, `/auth/login`, `/auth/logout` | Inscription, connexion, déconnexion |
| GET | `/auth/me` | Profil courant |
| POST | `/evidence` | Créer une preuve (fichier ou empreinte seule, en `multipart/form-data`) |
| GET | `/evidence`, `/evidence/{id}` | Lister, consulter |
| POST | `/evidence/{id}/timestamp` | Relancer un horodatage en attente ou échoué |
| GET | `/evidence/{id}/events` | Historique |
| GET | `/evidence/{id}/manifest` | Manifeste JSON |
| GET | `/evidence/{id}/export` | Passeport de preuve complet |
| POST | `/verify` | Vérifier un dossier déposé, sans compte |

`POST /evidence` répond 201, ou 400, 401, 413, 415 selon l'erreur. Une preuve inexistante et une preuve d'une autre organisation renvoient toutes deux 404, pour ne pas révéler l'existence d'un identifiant. `POST /verify` ne conserve pas les fichiers déposés et ne donne accès à aucun document privé.

## Sécurité

La sécurité distingue les mesures qui détectent une altération de celles qui l'empêchent ; le MVP garantit la détection, la prévention se renforce ensuite.

| Menace | Mesure | Dans le MVP |
| --- | --- | --- |
| Modification ou remplacement d'un fichier | Recalcul de l'empreinte SHA-256 | Oui |
| Falsification d'un horodatage | Validation complète du jeton TSA | Oui |
| Modification de l'historique | Journal chaîné, tête de chaîne horodatée à l'export | Oui |
| Réécriture par un administrateur | Séparation des privilèges, ancrage périodique hors de son contrôle | Partiel |
| Accès non autorisé | Sessions protégées, isolation par organisation, puis RBAC et MFA | Partiel |
| Fichier malveillant | Contrôle du type réel, limite de taille, quarantaine, aucun fichier exécuté | Oui |
| Fuite de données | Stockage privé, chiffrement au repos, téléchargements temporaires | Oui |
| Suppression malveillante ou perte | Sauvegardes testées, puis rétention immuable | Partiel |

Règles non négociables :

- Aucun secret dans le dépôt ; le fichier `.env` n'est jamais versionné.
- Aucune preuve certifiée n'est modifiée directement.
- Aucun résultat cryptographique non vérifié n'est affiché comme valide.
- Les mécanismes cryptographiques viennent de bibliothèques éprouvées, jamais d'une implémentation maison.
- Les fichiers sont servis en téléchargement, sans interprétation dans le navigateur.
- Les environnements de développement, de staging et de production ont des secrets et des données séparés.

Les référentiels pris en compte sont RFC 3161, RFC 5280, RFC 8785, ISO/IEC 27037, ISO/IEC 27001, OWASP ASVS et WCAG, ainsi que la LPRPDE et la Loi 25 au Québec pour les renseignements personnels, et eIDAS pour un futur marché européen. Les prendre en compte n'est pas une certification.

## Plan de réalisation

Le MVP représente 11 à 20 semaines de travail à temps plein pour une personne, réparties sur cinq phases de développement ; à temps partiel, la durée s'allonge en proportion. Ce sont des estimations de planification, pas des engagements.

| Phase | Objectif | Durée | Livrable |
| --- | --- | --- | --- |
| 0. Validation du problème | Interroger des analystes forensic, écrire le PRD et les critères d'acceptation | En parallèle de la phase 1 | Spécification produit validée par quelques utilisateurs potentiels |
| 1. Socle technique | Dépôt `veritas-platform`, FastAPI, Next.js, PostgreSQL, Docker Compose, Alembic, `/health`, premiers tests | 1 à 2 semaines | Frontend, backend et base qui communiquent en local |
| 2. Moteur de preuve | Téléversement, validation, stockage, SHA-256, premier événement, manifeste | 2 à 4 semaines | Dossier dont l'empreinte se recalcule et se compare |
| 3. Horodatage et chaîne | Intégration TSA, vérification du jeton, sérialisation canonique, insertions concurrentes, ancrage de la tête de chaîne | 3 à 5 semaines | Dossier avec empreinte, jeton et historique vérifiable |
| 4. Vérificateur autonome | Spécification du passeport, vérificateur local, tests sur dossiers valides, altérés, incomplets | 2 à 4 semaines | Vérificateur qui fonctionne sur un dossier exporté, sans le serveur |
| 5. MVP professionnel | Authentification robuste, organisations, journal d'audit, reprise sur erreur, sauvegardes, tests de sécurité, documentation | 3 à 5 semaines | Version pilote présentable |
| 6. Pilote | Trois à cinq utilisateurs professionnels, données autorisées, mesures et corrections | Après le MVP | Produit validé, premières offres définies |
| 7. Expansion | Spécification publique, API, plusieurs TSA, intégrations, déploiement privé | Années 2 et 3 | Plateforme interopérable |

L'authentification minimale (compte, session, isolation par organisation) est faite dès la phase 2, car le téléversement en dépend. La phase 5 la durcit.

### Conventions de développement

Le code suit PEP 8 côté Python, ESLint et Prettier côté TypeScript. Chaque fonctionnalité a sa branche (`feature/...`), ses tests Pytest écrits en même temps que le code, et ses migrations Alembic. Les versions des dépendances sont figées. GitHub Actions exécute les tests, puis l'analyse de sécurité, avant tout déploiement en staging.

### Critères d'acceptation du MVP

Le MVP est terminé quand les treize tests suivants passent tous.

| ID | Test | Résultat attendu |
| --- | --- | --- |
| T01 | Déposer un fichier, ou enregistrer une empreinte seule | Dépôt réussi, original conservé |
| T02 | Calculer SHA-256 | Empreinte enregistrée |
| T03 | Modifier un octet du fichier | Intégrité FAIL |
| T04 | Obtenir un horodatage | Jeton RFC 3161 reçu |
| T05 | Vérifier le jeton ; falsifier le jeton | Signature et chaîne validées ; jeton falsifié FAIL |
| T06 | Consulter l'historique | Événements affichés |
| T07 | Modifier, supprimer ou réordonner un événement | Chaîne de possession FAIL |
| T08 | Exporter le dossier | Passeport complet généré |
| T09 | Vérifier sans compte et sans connexion au serveur VERITAS | Vérification possible |
| T10 | Accéder à la preuve d'une autre organisation | 404 |
| T11 | Déposer un fichier trop volumineux | Rejet (413), aucun fichier exécuté ni interprété |
| T12 | Couper la TSA pendant un dépôt | Fichier et empreinte conservés, horodatage relançable |
| T13 | Restaurer une sauvegarde | Dossiers restaurés et vérifiables |

Pour le pilote, les objectifs proposés sont 20 dossiers de test complets, 100 % des altérations volontaires détectées et 100 % des jetons valides correctement vérifiés. Les indicateurs suivis ensuite sont le temps de création d'un dossier, le temps de vérification par un tiers, le taux de dossiers incomplets et le nombre d'utilisateurs actifs récurrents.

## Risques et questions ouvertes

Le risque principal n'est pas technique : c'est de construire un produit trop large, ou dont personne n'a besoin.

| Risque | Conséquence | Réponse |
| --- | --- | --- |
| Vouloir servir tous les marchés tout de suite | Produit trop complexe, jamais terminé | Forensic d'abord, périmètre MVP strict |
| Besoin non confirmé par les utilisateurs | Produit sans client | Phase 0 : entretiens avant la phase 2 |
| Dépendance à une seule TSA | Indisponibilité, confiance fragile | Interface `TimestampProvider`, second fournisseur après le MVP |
| Dépendance au serveur VERITAS | Vérification non indépendante | Vérificateur autonome dans le MVP |
| Perte de fichiers ou compromission du serveur | Perte ou altération de preuves | Sauvegardes testées, contrôles d'accès, ancrage externe |
| Mauvaise gestion des clés et certificats | Perte de confiance cryptographique | Gestionnaire de secrets, cycle de vie documenté |
| Conservation et résidence des données | Risque juridique | Politiques de rétention configurables, examen par juridiction |
| Promesse juridique excessive | Responsabilité commerciale | Limites affichées, avis juridique |
| Difficulté à convaincre les institutions | Adoption lente | Pilotes, audits, documentation technique |

### Réponses aux questions ouvertes

Cinq questions sur six sont tranchées par le raisonnement ; la première et la dernière restent à confirmer par les entretiens et par ton agenda.

**1. Formats et taille : tout type de fichier, plus un mode « empreinte seule ».** SHA-256 ne dépend pas du format, donc limiter le MVP au PDF n'économise presque rien et exclut les pièces réelles d'un analyste : images disque, journaux, captures réseau. Le MVP accepte tout fichier jusqu'à 500 Mo (configurable), servi uniquement en téléchargement. Pour les fichiers plus gros ou qui ne doivent pas quitter la garde de l'analyste, la commande `veritas hash` calcule l'empreinte en local et n'envoie que celle-ci au serveur. Ce mode réutilise le code du vérificateur, évite d'héberger des pièces sensibles et réduit le coût de stockage. À valider en entretien.

**2. TSA : DigiCert pour le développement et le pilote, FreeTSA pour les tests seulement.** Le serveur public de DigiCert ([timestamp.digicert.com](https://knowledge.digicert.com/general-information/rfc3161-compliant-time-stamp-authority-server)) répond en RFC 3161 et ses jetons remontent à une racine présente dans les magasins de confiance courants, ce qui simplifie la vérification par un tiers. [FreeTSA](https://freetsa.org/) repose sur sa propre racine : pratique pour les tests automatisés, insuffisant pour convaincre un tiers. Ces serveurs gratuits n'offrent ni contrat ni niveau de service ; avant toute vente, il faudra un fournisseur sous contrat, par exemple un service qualifié eIDAS comme celui de [Sectigo](https://sectigo.com/resource-library/time-stamping-server). DigiCert a remplacé trois certificats d'horodatage le 3 septembre 2026 : c'est la raison pour laquelle chaque dossier embarque sa chaîne de certificats.

**3. Bibliothèque RFC 3161 : `rfc3161-client` de Trail of Bits, version 1.0.3 au minimum.** Elle construit les requêtes et vérifie les réponses contre des certificats racines, et sa dernière version (1.0.6) date d'avril 2026 ([PyPI](https://pypi.org/project/rfc3161-client)). Les versions 1.0.2 et antérieures ne vérifiaient pas correctement la signature du jeton ([CVE-2025-52556](https://nvd.nist.gov/vuln/detail/CVE-2025-52556)). Elle ne fait aucun appel réseau : l'envoi à la TSA passe par `httpx`, déjà prévu. Les tests comparent ses verdicts à ceux de `openssl ts -verify`, pour ne pas dépendre d'une seule implémentation.

**4. Code ouvert : oui pour le vérificateur et la spécification du passeport, dès le MVP ; non pour le serveur.** Un vérificateur fermé oblige le tiers à faire confiance à VERITAS, ce qui contredit la promesse centrale. La valeur commerciale est dans le service (conservation, organisation, horodatage, audit), pas dans le contrôle d'une empreinte. Licence proposée : Apache 2.0.

**5. Hébergement du pilote : une région infonuagique située au Québec.** L'article 17 de la loi québécoise sur le secteur privé impose une évaluation des facteurs relatifs à la vie privée avant toute communication de renseignements personnels hors Québec ([BLG](https://www.blg.com/fr/insights/2022/12/cross-border-transfers-of-personal-information-outside-quebec)). Ce n'est pas une interdiction, mais héberger au Québec évite cette démarche pendant le pilote. La requête à la TSA ne transmet qu'une empreinte, pas le document. Une évaluation légère du système lui-même reste à prévoir avant d'accueillir de vraies données, et ce point doit être confirmé par un juriste.

**6. Temps disponible : hypothèse de 10 heures par semaine, à corriger.** Le MVP représente 440 à 800 heures. À 10 heures par semaine, cela donne 44 à 80 semaines, trop long pour garder l'élan. La cible raisonnable est donc le noyau démontrable, soit les phases 1 à 4 : 320 à 600 heures, ou 32 à 60 semaines à ce rythme. La phase 5 n'est lancée que si les entretiens confirment le besoin.

### Prochaines étapes

1. Confirmer ou corriger les sept arbitrages en tête de document.
2. Lancer le Sprint 1 (phase 1) : critère de sortie, l'application démarre en local et ses trois composants communiquent.
3. Mener en parallèle trois à cinq entretiens avec des analystes forensic et rédiger le PRD v1.0.
