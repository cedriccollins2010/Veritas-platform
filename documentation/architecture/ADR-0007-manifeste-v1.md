# ADR-0007 — Manifeste JSON v1

Date : 2026-11-13 · Statut : accepté · Issue : #8

## Contexte

Le manifeste est le document central du passeport de preuve : une description autoportante de tout ce qu'un tiers doit vérifier, sans interroger VERITAS. L'issue #8 exige un schéma publié, une empreinte qui change dès qu'un caractère change, et deux exports identiques octet pour octet.

## Décisions

1. **Format `veritas-manifest`, version `1.0`**, décrit par un schéma JSON (draft 2020-12) publié dans `documentation/api/manifest-v1.schema.json`. Le schéma est strict : aucun champ inconnu, et des formats imposés pour les UUID, les empreintes (64 caractères hexadécimaux) et les dates (UTC, microsecondes, `Z`). Il impose aussi `verified_by_server = false` quand `source = CLIENT`, et l'inverse.
2. **Contenu** : la preuve (identifiants, titre, état, date de création), ses fichiers (nom, type, taille, mode de stockage) et leurs empreintes (algorithme, encodage, version du moteur, origine, `verified_by_server`), la chaîne de possession complète (format, canonicalisation, `genesis`, nombre d'événements, tête de chaîne et événements avec leurs champs hachés), les jetons d'horodatage (vide en 1.0, phase 3) et les versions des outils.
3. **Empreinte du manifeste** : `manifest_digest = { algorithm: "SHA-256", canonicalization: "JCS-RFC8785", value }`, où `value` est le SHA-256 de la forme canonique RFC 8785 du manifeste **sans** le champ `manifest_digest`. Le code (`app/crypto/manifest.py`) ne dépend d'aucun autre module : le vérificateur le reprendra.
4. **Publication sous forme canonique.** `GET /evidence/{id}/manifest` renvoie les octets RFC 8785 du manifeste, et non un JSON indenté : ce que le tiers reçoit est exactement ce qui a été haché.
5. **Déterminisme.** Le manifeste est une fonction de l'état enregistré, et de lui seul : ni date de génération, ni valeur aléatoire, ni `created_at` des événements (non haché). Deux exports du même dossier sont donc identiques ; l'empreinte du manifeste sert d'`ETag`.
6. **Pas de manifeste pour une preuve incomplète** (`PROCESSING`, `FAILED`, `RECEIVED`) : 409. Une preuve d'une autre organisation : 404.
7. **`jsonschema`** (4.26.0, licence MIT) est une dépendance **de test** uniquement : le serveur produit le manifeste sans en avoir besoin.

## Conséquences

- L'empreinte du manifeste détecte une modification maladroite, pas un faussaire qui recalculerait tout ; la chaîne de possession, elle, reste vérifiable événement par événement depuis le manifeste (testé). La protection contre une réécriture complète viendra de l'horodatage RFC 3161 du manifeste et de la tête de chaîne (phase 3).
- Un changement de structure exige une nouvelle `format_version` et un nouveau schéma ; l'état de la preuve, lui, peut évoluer (un manifeste `CERTIFIED` diffère d'un manifeste `HASHED`).
- L'archive complète du passeport (original, jetons, certificats) viendra aux phases 3 et 4 ; le manifeste en sera le fichier `manifest.json`.
