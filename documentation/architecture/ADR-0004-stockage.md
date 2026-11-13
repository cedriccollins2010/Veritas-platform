# ADR-0004 — Stockage des fichiers originaux

Date : 2026-11-13 · Statut : accepté · Issue : #4

## Contexte

Les originaux doivent être conservés hors de la base de données, derrière une interface qui permet de passer du disque local à un stockage compatible S3. L'issue #4 prévoyait MinIO dans Docker Compose. Or MinIO a cessé de publier ses images Docker gratuites en octobre 2025, son dépôt a été archivé en avril 2026 et ses images ont été retirées de Docker Hub en septembre 2026.

## Décisions

1. **Interface `Storage`** (`save_stream`, `open`, `exists`, `size`) dans `app/storage/`. Le reste du code ne connaît qu'elle ; l'implémentation est choisie par `STORAGE_BACKEND` (`local` ou `s3`).
2. **Clés générées par le serveur** (`originals/<uuid4>`), jamais dérivées du nom de fichier fourni. Toute clé est validée : alphabet restreint, aucun `..`, aucun segment commençant par un point. Le stockage local vérifie en plus que le chemin final reste dans son dossier.
3. **Rien n'est jamais réécrit.**
   - Local : écriture dans `.incoming/`, `fsync`, puis publication par lien physique (`os.link`), qui échoue de façon atomique si la clé existe. Le fichier publié passe en lecture seule. Une écriture interrompue ne laisse aucun fichier visible.
   - S3 : écriture conditionnelle `If-None-Match: *`, refusée par le service (412) si la clé existe.
4. **`boto3`** (SDK officiel AWS) pour S3 : il fonctionne avec AWS et avec les services compatibles. Les identifiants viennent des variables standard `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, jamais de la configuration de VERITAS.
5. **Pas de serveur S3 dans Docker Compose pour l'instant.** Le développement et Docker utilisent le disque local (volume `evidence_data`). `S3Storage` est testé contre un faux S3 en mémoire (`moto`, dépendance de développement seulement), qui respecte l'écriture conditionnelle. Le vrai S3 arrivera au pilote, sur un service géré hébergé au Québec (par exemple AWS `ca-central-1`, Montréal), cohérent avec la décision d'hébergement du document de référence. Écartés pour l'instant : RustFS (prometteur mais jeune) et SeaweedFS (prise en charge de l'écriture conditionnelle non confirmée).
6. **Une seule suite de tests** (`tests/test_storage.py`) s'exécute sur toutes les implémentations. Un nouveau service s'y ajoute et doit la passer, en particulier le test qui refuse d'écraser un fichier.

## Conséquences

- Avant de choisir le service S3 du pilote, lancer `tests/test_storage.py` contre lui : un service qui ignore `If-None-Match` laisserait écraser une preuve.
- `S3Storage.save_stream` exige un flux relisable (fichier temporaire, `BytesIO`) : c'est le cas du téléversement de l'issue #5, qui passe par un fichier temporaire.
- Reste à faire en phase 5 : rétention immuable (Object Lock), chiffrement au repos du stockage local, sauvegardes testées.
