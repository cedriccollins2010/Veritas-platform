# ADR-0014 — Spécification du passeport de preuve `veritas-passport-v1`

Date : 2026-11-13 · Statut : accepté · Issue : #34

## Contexte

La phase 4 doit permettre à un tiers de vérifier un dossier VERITAS sans faire confiance au serveur. L'outil (`veritas verify`, #36) ne suffit pas : il faut une règle publique que n'importe qui puisse réimplémenter. Le document de référence esquissait une arborescence (`cryptographic/`, `custody/custody-events.json`, `timestamp/tsa-certificates/`, `report/`). Cette esquisse est antérieure au manifeste 1.1, qui contient déjà la chaîne de possession, les empreintes et les références des jetons.

## Décisions

1. **Spécification normative `verifier/SPECIFICATION.md`, sous Apache 2.0**, à côté de l'implémentation de référence. Les schémas JSON du manifeste quittent `documentation/api/` pour `verifier/src/veritas_verifier/schemas/`, parce qu'ils font partie de la règle publique. Ils sont livrés avec le paquet (`manifest.load_schema`). Les ADR-0007 et ADR-0012 citent encore l'ancien chemin.
2. **Archive ZIP au contenu exact et minimal.** Elle contient `manifest.json`, `original/<file_id>`, ainsi que `timestamp/<id>.tsr` et `<id>.tsq`, et rien d'autre. J'ai écarté les éléments suivants de l'esquisse :
   - copie de la chaîne (`custody-events.json`), fichiers `sha256.txt` et `hash-metadata.json` : redondants avec le manifeste. Deux sources qui peuvent se contredire obligent à décider laquelle croire.
   - dossier `tsa-certificates/` : les jetons embarquent leurs certificats, et un jeton n'entre au manifeste que s'il a été vérifié `VALID` avec ces seuls certificats.
   - `report/` : P2, et un rapport serait un résultat produit par le serveur, que le destinataire n'a pas à croire.
   - Toute entrée en trop rend l'archive `INCOMPLETE` : un faux « rapport VALIDE » glissé dans l'archive est signalé.
3. **Chemins dérivés des identifiants, jamais du nom d'origine.** La grammaire des noms tient en une expression régulière, ce qui écarte la traversée de répertoire et les noms ambigus.
4. **Écriture déterministe** : entrées triées, méthode stockée (sans compression), date 1980-01-01, attributs fixes, sans champ supplémentaire ni « data descriptor ». Deux exports du même état sont identiques octet pour octet, et n'importe qui peut reconstruire l'archive à partir de son contenu (testé sur l'exemple). Ces règles lient le producteur, pas le vérificateur : une archive recompressée reste vérifiable, puisque l'intégrité vient des empreintes. En revanche, les règles de **lecture** sont des règles de sécurité et entraînent un refus. Elles écartent :
   - les archives polyglottes ;
   - les noms hors grammaire et les doublons ;
   - les liens et les entrées chiffrées ;
   - les tailles hors limites. La lecture est bornée : 16 Mio pour le manifeste, 1 Mio pour un jeton, et la taille déclarée plus un octet pour un original.
5. **Implémentation de référence de l'archive : `veritas_verifier.passport`.** Elle fournit la grammaire, `expected_entries` et `write_passport`. `write_passport` refuse d'écrire un passeport inexact (manifeste non canonique, entrée manquante ou en trop). L'export du serveur (#35) l'utilisera, et le vérificateur (#36) lira avec les mêmes définitions.
6. **Six contrôles normatifs** :
   - `MANIFEST` ;
   - `INTEGRITY` ;
   - `TIMESTAMP` (jetons des fichiers) ;
   - `CERTIFICATE` (signature et chaîne de chaque jeton, certificats évalués à la date du jeton) ;
   - `CUSTODY` (chaîne et ancrage) ;
   - `COMPLETENESS`.

   Le verdict vaut `VALID` si tout est `PASS` et `COMPLETE`, `INVALID` dès qu'un `FAIL` apparaît, `INCONCLUSIVE` sinon. Sont donc `INCONCLUSIVE`, jamais `VALID` : une preuve en attente d'horodatage, une chaîne non ancrée (`CUSTODY = UNKNOWN`), un passeport en empreinte seule vérifié sans le fichier (`INTEGRITY = UNKNOWN`). La révocation reste une information `UNKNOWN` hors des six contrôles, comme en ADR-0009. Sinon aucun dossier ne serait jamais `VALID` hors ligne.
7. **Champs garantis et champs déclaratifs.** L'empreinte du manifeste se recalcule par n'importe qui : elle ne protège que contre une altération maladroite. La spécification exige donc que le manifeste **concorde avec la chaîne** :
   - les fichiers avec leur événement `FILE_RECEIVED` ou `HASH_DECLARED` ;
   - les jetons avec leur événement `TIMESTAMP_ATTACHED` ou `CHAIN_ANCHORED`, empreinte du `.tsr` comprise.

   Cette concordance place sous l'ancrage le nom, la taille, le type et l'empreinte du fichier. Le titre, l'organisation, le propriétaire, le statut et la date de création ne sont couverts par aucun horodatage : ils sont déclarés comme tels et n'entrent dans aucun verdict. J'ai vérifié que le serveur actuel produit déjà des manifestes qui respectent ces règles, dans quatre cas : certifié et ancré, en attente, non horodaté, empreinte seule.
8. **Racines de confiance** : le vérificateur apporte les siennes, publiées avec leur provenance. L'ajout d'une racine est explicite et apparaît dans le résultat. Le passeport n'en contient jamais.
9. **Exemple publié** (`verifier/examples/passport-v1/`) : un passeport synthétique, signé par une TSA d'exemple dont seule la racine publique est versionnée. La politique `2.999.1` appartient à l'arc OID réservé aux exemples. Un README refait chaque contrôle à la main (`sha256sum`, `openssl ts -verify`, quelques lignes de Python), et des tests garantissent que l'exemple, son README et la spécification restent d'accord.

## Conséquences

- #35 produit l'archive avec `write_passport`. #36 implémente la section 5, et les tests de l'exemple en sont déjà une première version.
- La table `verification_records` (migration 0001) n'admet que `PASS`/`FAIL` pour `integrity_status` et `custody_status`. La spécification y prévoit `UNKNOWN` (empreinte seule sans fichier, chaîne non ancrée). Il faudra une migration si #38 enregistre les vérifications.
- Toute évolution exige une nouvelle version du passeport : nouvelle entrée, nouvelle règle d'archive, algorithme de contrôle modifié, nouvelle version du manifeste. Le relèvement d'une limite de lecture ou l'ajout d'une racine n'en exige pas.
- Régénérer l'exemple change ses valeurs : il faut alors mettre à jour son README, ce que vérifie un test.
