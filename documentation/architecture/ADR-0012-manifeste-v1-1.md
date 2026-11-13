# ADR-0012 — Manifeste 1.1 : jetons d'horodatage et ancrage

Date : 2026-11-13 · Statut : accepté · Issue : #27

## Contexte

Le manifeste 1.0 (ADR-0007) décrivait la preuve, ses fichiers, ses empreintes et sa chaîne de possession, mais pas l'horodatage, qui n'existait pas encore. La phase 3 a ajouté les jetons RFC 3161 des fichiers (ADR-0010) et l'ancrage de la tête de chaîne (ADR-0011) : un tiers doit pouvoir les vérifier seul, à partir du manifeste.

## Décisions

1. **Nouvelle version de format `1.1`**, avec son schéma `documentation/api/manifest-v1.1.schema.json`. Le schéma 1.0 reste publié tel quel : un manifeste 1.0 déjà remis reste vérifiable contre son schéma. `GET /evidence/{id}/manifest` produit désormais du 1.1.
2. **Section `timestamps`** : uniquement les jetons vérifiés `VALID` (ceux qu'un tiers peut vérifier ; les tentatives en échec restent tracées dans la base et le journal). Pour chacun : objet (`FILE` ou `CHAIN_HEAD`), empreinte horodatée, numéro ancré (`CHAIN_HEAD` seulement), TSA, policy OID, numéro de série, date de génération, et pour le jeton (`.tsr`) et la requête (`.tsq`) le chemin prévu dans l'archive du passeport (`timestamp/<id>.tsr|.tsq`) avec l'empreinte SHA-256 **du fichier réellement conservé**.
3. **Section `timestamp_status`**, explicite : horodatage du fichier `VALID`, `PENDING` (en attente) ou `NONE` ; tête de chaîne `ANCHORED` ou `NONE`, avec le numéro ancré ; et `unanchored_events`, le nombre d'événements postérieurs au dernier ancrage (dont l'événement `CHAIN_ANCHORED` lui-même), couverts par la chaîne seulement. Une preuve en attente ou non ancrée ne peut pas passer pour certifiée.
4. **Schéma strict et cohérent** : un `CHAIN_HEAD` exige un numéro ancré, un `FILE` l'interdit, un jeton non `VALID` est refusé, `chain_head = ANCHORED` exige un numéro, et les chemins doivent rester dans `timestamp/` (testé).
5. **Toujours aucun champ variable** : les entrées sont triées de façon déterministe ; deux exports du même état restent identiques octet pour octet, ancrage réutilisé compris. `tools` indique aussi la version de `rfc3161-client`.

## Conséquences

- Avec le manifeste et les fichiers `.tsr`/`.tsq`, un tiers vérifie la chaîne (`verify_chain`), chaque jeton (`verify_timestamp_token`) et l'ancrage (`verify_anchor`) : c'est exactement ce que fera le vérificateur autonome (phase 4), et un test le simule déjà de bout en bout.
- Lire le manifeste ouvre les fichiers `.tsr` et `.tsq` conservés pour en calculer l'empreinte : quelques kilo-octets par jeton.
- Toute évolution de structure exigera une nouvelle `format_version` et un nouveau schéma, publiés à côté des précédents.
