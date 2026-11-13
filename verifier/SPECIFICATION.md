# Passeport de preuve VERITAS — spécification `veritas-passport-v1`

Statut : version 1, publiée · Licence : Apache 2.0 (comme tout le dossier `verifier/`) · Implémentation de référence : paquet `veritas-verifier` (`veritas_verifier.passport` pour l'archive). Décisions : ADR-0014.

Ce document décrit le passeport de preuve exporté par VERITAS, et ce qu'il faut calculer pour le vérifier. Il suffit à écrire un vérificateur indépendant, dans n'importe quel langage, sans lire le code de VERITAS et sans contacter son serveur. L'exemple de `examples/passport-v1/` se vérifie à la main avec `unzip`, `sha256sum`, `openssl` et quelques lignes de Python.

## 1. Objet et principe

Un passeport est une archive ZIP qui accompagne un fichier (la « pièce »). Il permet à un tiers de répondre à trois questions :

1. **Intégrité.** Le fichier que j'ai entre les mains est-il celui qui a été déposé, octet pour octet ?
2. **Antériorité.** Ce fichier existait-il au plus tard à une date donnée ? Une autorité d'horodatage (TSA, RFC 3161) indépendante de VERITAS l'atteste.
3. **Traçabilité.** La chronologie des opérations (dépôt, horodatage, ancrage) a-t-elle été modifiée depuis son ancrage ?

**Le vérificateur ne fait pas confiance au serveur VERITAS.** Tout ce qu'il croit vient de trois sources seulement :

- les calculs qu'il refait lui-même (SHA-256, RFC 8785) ;
- les signatures des autorités d'horodatage ;
- **ses propres racines de confiance**, qui ne viennent jamais du passeport.

Un champ que seul VERITAS affirme, sans signature d'une TSA, reste **déclaratif** (section 4.3).

**Ce qu'un passeport ne prouve pas** :

- que le contenu dit vrai ;
- l'identité de la personne qui a déposé le fichier (`actor_id` désigne un compte VERITAS, pas une personne vérifiée) ;
- la date de création du fichier : seulement qu'il existait au plus tard à la date du jeton ;
- sa recevabilité devant un tribunal.

Un vérificateur doit le rappeler à la personne qui lit le résultat.

## 2. Conventions

- **DOIT**, **NE DOIT PAS**, **PEUT** ont le sens de « MUST », « MUST NOT », « MAY » (RFC 2119).
- **Empreinte** : SHA-256 (FIPS 180-4), écrite en hexadécimal minuscule (64 caractères). Toute comparaison d'empreintes DEVRAIT se faire en temps constant.
- **JCS** : canonicalisation JSON RFC 8785. Le format VERITAS interdit en plus les nombres non entiers et les entiers hors de ±(2^53 − 1).
- **Date** : UTC, RFC 3339, six chiffres de microsecondes, suffixe `Z` (`2026-11-13T04:36:44.000000Z`).
- **Producteur** : le logiciel qui crée le passeport, aujourd'hui le serveur VERITAS. **Vérificateur** : le logiciel qui le contrôle.

## 3. L'archive

### 3.1 Contenu exact

Le passeport contient **exactement** les entrées ci-dessous, rien de plus, rien de moins. Leur liste se calcule à partir du manifeste seul (`veritas_verifier.passport.expected_entries`).

| Entrée | Présente quand | Contenu |
| --- | --- | --- |
| `manifest.json` | toujours | Le manifeste (section 4), octets de sa forme canonique JCS |
| `original/<file_id>` | pour chaque fichier dont `storage_mode` vaut `STORED` | Le fichier déposé, octet pour octet |
| `timestamp/<id>.tsr` | pour chaque entrée de `timestamps` | La réponse RFC 3161 complète (`TimeStampResp`, DER), telle que la TSA l'a renvoyée |
| `timestamp/<id>.tsq` | pour chaque entrée de `timestamps` | La requête RFC 3161 envoyée (`TimeStampReq`, DER) |

`<file_id>` est `files[].id` et `<id>` est `timestamps[].timestamp_record_id` : des UUID en minuscules. Les chemins annoncés par le manifeste (`token.path`, `request.path`) DOIVENT être exactement `timestamp/<id>.tsr` et `timestamp/<id>.tsq`.

Règles qui découlent de ce tableau :

- **Un nom d'entrée suit l'un des trois motifs ci-dessus**, en ASCII minuscule. L'expression régulière est `^(manifest\.json|original/U|timestamp/U\.ts[qr])$`, où `U` vaut `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`.
- **Le nom d'origine du fichier n'est jamais un chemin.** Il reste dans le manifeste (`original_filename`). Un nom choisi par l'utilisateur permettrait une traversée de répertoire (`../../…`) chez le destinataire.
- **En mode « empreinte seule »** (`HASH_ONLY`), il n'y a pas d'entrée `original/` : VERITAS n'a jamais reçu le fichier.
- **La chaîne de possession n'a pas de fichier à part** : elle est entière dans le manifeste. Une copie séparée pourrait contredire le manifeste sans qu'on sache laquelle croire.
- **Les certificats de la TSA sont ceux que le jeton embarque.** Le passeport ne contient ni certificat séparé ni racine de confiance (section 7). Un jeton n'apparaît dans le manifeste que s'il a été vérifié `VALID` avec ses seuls certificats embarqués. Le vérificateur n'a donc besoin de rien d'autre.
- **Aucun résultat de vérification** n'est inclus : le destinataire vérifie lui-même.

### 3.2 Règles de production (déterminisme)

Le producteur DOIT écrire l'archive ainsi. Deux exports du même état donnent alors la même archive, octet pour octet :

- format ZIP (PKWARE APPNOTE), entrées de fichier seulement (aucune entrée de répertoire), triées par ordre croissant des octets du nom ;
- méthode `0` (stockée, sans compression) : la compression varie selon les bibliothèques et leurs versions ;
- date et heure de chaque entrée : 1980-01-01 00:00:00 (valeur MS-DOS minimale) ;
- « version made by » : système `3` (Unix), quel que soit le système qui écrit ; attributs externes : `0o100644 << 16` (fichier ordinaire) ;
- aucun champ supplémentaire (« extra field »), aucun commentaire d'entrée ni d'archive, aucun chiffrement ;
- aucun « data descriptor » (bit 3) : les tailles et le CRC-32 sont dans l'en-tête local ;
- ZIP64 seulement si la taille d'une entrée ou de l'archive l'exige ;
- nom de fichier recommandé : `veritas-passport-<evidence_id>.zip` ; type de média : `application/zip`.

Ces règles servent la reproductibilité, pas la sécurité : un vérificateur NE DOIT PAS refuser une archive pour ce seul motif (par exemple une archive recompressée par un autre outil). L'intégrité vient des empreintes, pas de la forme du ZIP.

### 3.3 Règles de lecture (sécurité)

Une archive reçue est hostile tant qu'elle n'est pas vérifiée. Le vérificateur DOIT **refuser** l'archive, sans en interpréter le contenu, dans les cas suivants :

- l'archive est illisible, ou des octets précèdent la première entrée ou suivent la fin du répertoire central (fichier polyglotte) ;
- une entrée est chiffrée, ou sa méthode n'est ni `0` (stockée) ni `8` (Deflate) ;
- un nom d'entrée ne suit pas la grammaire de la section 3.1 : chemin absolu, `..`, barre oblique inverse, répertoire, majuscules, caractère non ASCII ou de contrôle ;
- deux entrées portent le même nom ;
- une entrée n'est pas un fichier ordinaire, par exemple un lien symbolique déclaré dans les attributs Unix ;
- les limites sont dépassées : plus de 10 000 entrées ; `manifest.json` au-delà de 16 Mio ; un `.tsr` ou un `.tsq` au-delà de 1 Mio.

**Lire avec une taille bornée.** Le vérificateur ne lit jamais une entrée au-delà de sa taille attendue : il arrête la décompression dès que la limite est atteinte (protection contre les « bombes » de décompression). Pour `original/<file_id>`, la taille attendue est `files[].size` : le vérificateur lit au plus un octet de plus. Une taille différente n'est pas un refus d'archive mais un `INTEGRITY = FAIL` (section 5.2). Ces limites PEUVENT être relevées explicitement par l'utilisateur, jamais en silence.

**Ne jamais extraire sous le nom de l'archive.** Le vérificateur lit les entrées en mémoire, ou les copie dans un répertoire temporaire sous des noms qu'il choisit lui-même. Aucun fichier n'est écrit hors de ce répertoire. Le contenu n'est jamais exécuté ni interprété autrement que comme décrit ici.

**Archive refusée.** Les résultats sont alors les suivants : `MANIFEST = FAIL` (« archive refusée : rien n'a été lu »), `COMPLETENESS = INCOMPLETE`, et `UNKNOWN` pour les autres contrôles. Le verdict est `INVALID`.

**Forme répertoire.** Un vérificateur PEUT accepter un passeport déjà extrait, sous forme de répertoire. Les mêmes règles s'appliquent : mêmes noms, fichiers ordinaires seulement, aucun lien symbolique, aucun fichier en plus.

## 4. Le manifeste dans le passeport

### 4.1 Version et forme

Un passeport v1 contient un manifeste `veritas-manifest` de version **`1.1`**. Son schéma JSON (draft 2020-12) est publié avec cette spécification : `src/veritas_verifier/schemas/manifest-v1.1.schema.json`. Le schéma 1.0 y figure aussi, mais un manifeste 1.0 n'est jamais dans un passeport.

`manifest.json` DOIT contenir **exactement les octets de la forme canonique JCS** du manifeste, encodée en UTF-8, sans indentation ni retour à la ligne final. Cette règle a trois effets :

- il n'existe qu'une représentation possible ;
- un manifeste réindenté est rejeté ;
- un objet avec deux fois la même clé est rejeté (I-JSON, RFC 7493), puisque sa forme canonique diffère des octets reçus.

### 4.2 Empreinte du manifeste

`manifest_digest` vaut :

```json
{"algorithm": "SHA-256", "canonicalization": "JCS-RFC8785", "value": "<v>"}
```

`<v>` est le SHA-256 de la forme canonique JCS du manifeste **privé de son champ `manifest_digest`**.

Cette empreinte détecte une altération accidentelle ou maladroite. **Elle ne protège pas contre un faussaire**, qui peut la recalculer. La protection forte vient des jetons d'horodatage, signés par une TSA (sections 5.3 et 5.5). La section 4.3 dit quels champs ils couvrent.

### 4.3 Champs garantis et champs déclaratifs

| Champ du manifeste | Garanti par | Statut |
| --- | --- | --- |
| `files[].hashes[].digest` | jeton `FILE` (signature de la TSA) | **Garanti**, avec la date du jeton |
| `files[]` : `id`, `original_filename`, `media_type`, `size`, `storage_mode`, `source` | l'événement `FILE_RECEIVED` ou `HASH_DECLARED`, couvert par l'ancrage | **Garanti** si cet événement est ancré |
| `custody.events[]` jusqu'au numéro ancré | jeton `CHAIN_HEAD` (ancrage) | **Garanti** |
| `custody.events[]` après le numéro ancré | la chaîne seulement | Détectable s'il est modifié isolément, mais pas une réécriture de toute la fin |
| `timestamps[]` : `generation_time`, `serial_number`, `policy_oid`, `message_imprint` | le jeton lui-même | **Garanti** (relu dans le jeton) |
| `timestamps[].tsa.name`, `tsa.url` | rien | Déclaratif : l'identité de la TSA est le sujet de son certificat |
| `evidence` : `title`, `organization_id`, `owner_id`, `status`, `created_at` | rien | **Déclaratif** |
| `tools`, `timestamp_status` | cohérence avec le reste (section 5.1) | Déclaratif |

Un vérificateur DOIT afficher les champs déclaratifs comme tels, et NE DOIT JAMAIS fonder un verdict sur eux. Exemple : `evidence.status = "CERTIFIED"` ne remplace pas la vérification d'un jeton.

## 5. Les contrôles

Six contrôles, chacun avec son propre résultat. Les identifiants ci-dessous sont normatifs.

| Identifiant | Contrôle | Résultats possibles |
| --- | --- | --- |
| `MANIFEST` | Format et intégrité du manifeste | `PASS` / `FAIL` |
| `INTEGRITY` | Intégrité du ou des fichiers | `PASS` / `FAIL` / `UNKNOWN` |
| `TIMESTAMP` | Jetons d'horodatage des fichiers | `PASS` / `FAIL` / `UNKNOWN` |
| `CERTIFICATE` | Chaîne de certificats de chaque jeton | `PASS` / `FAIL` / `UNKNOWN` |
| `CUSTODY` | Chaîne de possession et ancrage | `PASS` / `FAIL` / `UNKNOWN` |
| `COMPLETENESS` | Complétude de l'archive | `COMPLETE` / `INCOMPLETE` |

`UNKNOWN` signifie « l'information manque pour conclure ». Ce n'est jamais un succès. Chaque résultat DOIT être accompagné d'un détail lisible : ce qui a échoué ou ce qui manque.

**Ordre et dépendances.** Le vérificateur lit d'abord l'archive (section 3.3), puis le manifeste.

- Si `manifest.json` manque, n'est pas du JSON, ne respecte pas le schéma 1.1 ou n'est pas d'une version admise, alors `MANIFEST = FAIL`, `COMPLETENESS = INCOMPLETE`, et les autres contrôles valent `UNKNOWN`.
- Sinon, tous les contrôles sont évalués, même si `MANIFEST` échoue : leurs résultats aident à localiser l'altération. Le verdict, lui, sera `INVALID`.

Les fonctions citées entre parenthèses sont celles de l'implémentation de référence (`veritas_verifier`).

### 5.1 `MANIFEST` — format et intégrité du manifeste

`PASS` si et seulement si toutes les conditions suivantes sont vraies :

1. `manifest.json` est un JSON UTF-8 dont la forme canonique JCS est **identique** aux octets reçus (section 4.1).
2. Le document respecte le schéma `manifest-v1.1.schema.json`.
3. `manifest_digest` est correct (`manifest.digest_is_valid`).
4. **Les chemins sont canoniques** : pour chaque entrée de `timestamps`, `token.path` et `request.path` valent exactement `timestamp/<timestamp_record_id>.tsr` et `.tsq`.
5. **Cohérence de la chaîne** : `custody.event_count` est le nombre d'événements, et `custody.head_hash` est l'`event_hash` du dernier.
6. **Les fichiers concordent avec la chaîne.** Chaque fichier `f` a exactement un événement `FILE_RECEIVED` (si `STORED`) ou `HASH_DECLARED` (si `HASH_ONLY`) dont `event_data.file_id = f.id`. Dans cet événement, `original_filename`, `media_type`, `size`, `storage_mode`, `hash_algorithm` = `SHA-256`, `digest` et `hash_source` sont égaux aux valeurs du manifeste. `hash_source` correspond à `hashes[].source`.
7. **Les jetons concordent avec la chaîne.**
   - Chaque entrée `FILE` a un événement `TIMESTAMP_ATTACHED` du même `timestamp_record_id`, avec les mêmes `purpose`, `message_imprint`, `generation_time`, `serial_number` et `policy_oid`. Son `token_sha256` est égal à `token.sha256`.
   - Chaque entrée `CHAIN_HEAD` a un événement `CHAIN_ANCHORED` du même `timestamp_record_id`, avec les mêmes `anchored_sequence_number`, `generation_time` et `serial_number`. Son `anchored_hash` est égal à `message_imprint`, et son `token_sha256` à `token.sha256`.
8. **`timestamp_status` est cohérent** :
   - `file = VALID` si et seulement s'il existe une entrée `FILE` ;
   - `chain_head = ANCHORED` si et seulement s'il existe une entrée `CHAIN_HEAD`, et `anchored_sequence_number` est alors le plus grand numéro ancré ;
   - `unanchored_events = event_count − (anchored_sequence_number ou 0)`.

Sinon `FAIL`, avec la liste des conditions non remplies.

### 5.2 `INTEGRITY` — intégrité des fichiers

Pour chaque fichier `f` du manifeste, on calcule un résultat `r(f)` :

- **`STORED`** :
  - si `original/<f.id>` est présent, `r(f) = PASS` quand sa taille vaut `f.size` et que son SHA-256 est égal à `f.hashes[0].digest`, sinon `FAIL` ;
  - si l'entrée est absente, `r(f) = UNKNOWN` (et `COMPLETENESS = INCOMPLETE`).
- **`HASH_ONLY`** : le fichier n'est pas dans le passeport.
  - si le destinataire fournit le fichier séparément (par exemple `veritas verify … --original <fichier>`), `r(f)` se calcule comme ci-dessus sur ce fichier ;
  - sinon `r(f) = UNKNOWN`.

  Un `PASS` signifie alors : « le fichier fourni est celui dont l'analyste avait déclaré l'empreinte ». Avec un jeton `FILE` valide, cette empreinte existait à la date du jeton.

`INTEGRITY = FAIL` si un `r(f)` vaut `FAIL`, `PASS` si tous valent `PASS`, `UNKNOWN` sinon.

### 5.3 `TIMESTAMP` — jetons d'horodatage des fichiers

Un jeton `FILE` est une entrée `t` de `timestamps` avec `purpose = FILE`. Pour chacun :

1. Les octets de `timestamp/<id>.tsr` et `.tsq` ont pour SHA-256 `t.token.sha256` et `t.request.sha256`.
2. `t.message_imprint` est l'empreinte d'un fichier du manifeste.
3. Les contrôles RFC 3161 de `verify_timestamp_token(tsr, tsq, t.message_imprint, racines)` sont tous `PASS`, sauf `SIGNATURE_AND_CHAIN`, qui relève de `CERTIFICATE`. Ces contrôles sont les suivants :
   - `RESPONSE_READABLE` : la réponse se décode en DER strict ;
   - `STATUS_GRANTED` : la TSA a accordé l'horodatage ;
   - `MESSAGE_IMPRINT` : le jeton porte l'algorithme SHA-256 et l'empreinte attendue ;
   - `REQUEST_MATCH` : la requête portait cette même empreinte ;
   - `NONCE` : le nonce du jeton est celui de la requête ;
   - `TSA_CERTIFICATE` : le certificat désigné par la signature (`issuerAndSerialNumber`) porte l'usage étendu critique `id-kp-timeStamping`.
4. La date (`genTime`), le numéro de série et la politique lus **dans le jeton** sont ceux du manifeste (`generation_time`, `serial_number` en hexadécimal minuscule, `policy_oid`).

`TIMESTAMP = FAIL` si un jeton `FILE` échoue à l'une de ces étapes. `PASS` si chaque fichier a au moins un jeton `FILE` et que tous réussissent. Sinon `UNKNOWN`, par exemple pour une preuve en attente d'horodatage (`timestamp_status.file = PENDING`) ou jamais horodatée (`NONE`). Une preuve non horodatée n'est jamais présentée comme certifiée.

La date à afficher est le `genTime` du jeton, avec sa précision (`accuracy`) si la TSA la donne. Elle signifie : **« ce fichier existait au plus tard à cette date »**.

### 5.4 `CERTIFICATE` — chaîne de certificats

Pour **chaque** jeton du passeport (`FILE` et `CHAIN_HEAD`), le vérificateur contrôle trois points :

- la signature CMS du jeton ;
- la chaîne de certificats, depuis le certificat signataire embarqué jusqu'à l'une **de ses propres racines de confiance** (section 7) ;
- la validité des certificats **à la date `genTime` du jeton**, pas à la date de la vérification.

C'est le contrôle `SIGNATURE_AND_CHAIN` de `verify_timestamp_token`. L'implémentation de référence le délègue à `rfc3161-client` : aucune cryptographie n'est réimplémentée.

`CERTIFICATE = PASS` si tous les jetons réussissent, `FAIL` si l'un échoue (chaîne qui aboutit à une racine non reconnue comprise), `UNKNOWN` si le passeport ne contient aucun jeton.

**Révocation.** L'état de révocation des certificats (OCSP, CRL) ne se consulte pas hors ligne. Le vérificateur le signale comme `UNKNOWN`, à titre d'information. Ce n'est pas l'un des six contrôles, et il n'empêche donc pas `VALID`. Il NE DOIT JAMAIS l'afficher comme vérifié (section 8).

### 5.5 `CUSTODY` — chaîne de possession et ancrage

**La chaîne.** On reconstruit chaque événement `E(n)` avec exactement les champs hachés du format `veritas-custody-v1` (ADR-0005) :

```text
{format: "veritas-custody-v1", event_id, evidence_id, sequence_number,
 event_type, actor_id, occurred_at, event_data}
```

`evidence_id` vaut `evidence.id`. Puis `H(n) = SHA-256(H(n−1) ‖ JCS(E(n)))`, avec `H(0)` = 32 octets nuls. La chaîne est valide si les conditions suivantes sont toutes réunies (`custody_chain.verify_chain`) :

- les numéros vont de 1 à N, dans l'ordre et sans trou ;
- chaque `previous_event_hash` vaut l'`event_hash` précédent, et `null` pour le premier ;
- chaque `event_hash` recalculé est égal à celui du manifeste ;
- aucun identifiant d'événement n'apparaît deux fois.

**L'ancrage.** Pour chaque entrée `CHAIN_HEAD` `a`, quatre conditions sont requises :

- les fichiers `.tsr` et `.tsq` ont les empreintes annoncées ;
- les contrôles RFC 3161 de `verify_timestamp_token(tsr, tsq, a.message_imprint, racines)` réussissent, comme en 5.3, étape 3 ;
- la date, le numéro de série et la politique du jeton sont ceux du manifeste ;
- l'événement n° `a.anchored_sequence_number` existe et son `event_hash` vaut `a.message_imprint` (`custody_chain.verify_anchor`).

Un événement ancré manquant révèle une **suppression en fin de chaîne**. Une empreinte différente révèle une **réécriture**, même si toutes les empreintes ont été recalculées.

**Résultat :**

| Situation | `CUSTODY` |
| --- | --- |
| Chaîne invalide, ou un ancrage échoue | `FAIL` |
| Chaîne valide, aucun ancrage | `UNKNOWN` (« tête de chaîne non ancrée ») |
| Chaîne valide, tous les ancrages réussissent | `PASS` |

Avec `PASS`, le détail DOIT indiquer le numéro ancré le plus élevé `k` et les événements `k+1 … N`. Ces derniers sont couverts par la chaîne seulement, pas par un horodatage externe. L'événement `CHAIN_ANCHORED` du dernier ancrage en fait toujours partie.

### 5.6 `COMPLETENESS` — complétude de l'archive

`COMPLETE` si l'ensemble des entrées de l'archive est **exactement** celui de la section 3.1, calculé à partir du manifeste. Sinon `INCOMPLETE`, avec la liste des entrées manquantes et des entrées en trop. `INCOMPLETE` aussi si le manifeste ne permet pas de calculer cet ensemble.

Une entrée en trop n'altère aucun élément vérifié, mais l'archive n'est plus celle que VERITAS a produite. Exemple : un `rapport.pdf` qui affirmerait « VALIDE ». Le vérificateur le signale et ne l'ouvre jamais.

## 6. Verdict global

| Verdict | Condition |
| --- | --- |
| `VALID` | `MANIFEST`, `INTEGRITY`, `TIMESTAMP`, `CERTIFICATE` et `CUSTODY` valent `PASS`, **et** `COMPLETENESS` vaut `COMPLETE` |
| `INVALID` | au moins un contrôle vaut `FAIL` |
| `INCONCLUSIVE` | aucun `FAIL`, mais au moins un `UNKNOWN` ou `INCOMPLETE` |

Le verdict ne remplace pas les résultats détaillés : le vérificateur DOIT toujours les afficher tous. Exemples de dossiers authentiques mais `INCONCLUSIVE` :

- une preuve en attente d'horodatage ;
- une tête de chaîne jamais ancrée ;
- un passeport en mode empreinte seule vérifié sans le fichier.

C'est voulu : `VALID` n'est jamais accordé faute de preuve contraire.

## 7. Racines de confiance

- **Le vérificateur apporte ses racines.** Il NE DOIT JAMAIS lire une racine dans le passeport : un faussaire y mettrait la sienne et signerait ce qu'il veut.
- **Liste publiée.** L'implémentation de référence livre sa liste avec, pour chaque racine, l'empreinte SHA-256 du certificat et sa provenance documentée : la racine DigiCert Trusted Root G4 pour la TSA de DigiCert utilisée en production pilote. Toute modification de cette liste passe par une relecture.
- **Ajout explicite.** L'utilisateur PEUT ajouter une racine pour une vérification donnée, par exemple la racine d'exemple de `examples/passport-v1/`. Le vérificateur DOIT alors indiquer dans son résultat qu'une racine fournie par l'utilisateur a servi.
- **Racines d'exemple ou de test.** Elles ne figurent jamais dans la liste par défaut.

## 8. Menaces couvertes et limites

| Altération | Contrôle qui la détecte |
| --- | --- |
| Un octet du fichier modifié | `INTEGRITY = FAIL` |
| Le manifeste modifié sans recalcul | `MANIFEST = FAIL` (empreinte) |
| Le manifeste modifié **et** son empreinte recalculée : empreinte, nom ou taille du fichier | `MANIFEST = FAIL` (concordance avec la chaîne, 5.1), `TIMESTAMP = FAIL` (empreinte horodatée) ou `CUSTODY = FAIL` (ancrage) |
| Événement modifié, supprimé, inséré ou réordonné | `CUSTODY = FAIL` |
| Derniers événements supprimés, ou chaîne entière réécrite avec des empreintes recalculées | `CUSTODY = FAIL` (ancrage), pour la partie ancrée |
| Jeton remplacé par celui d'une autre empreinte, ou d'un autre dossier | `TIMESTAMP` ou `CUSTODY = FAIL` (empreinte, `token_sha256` attesté par la chaîne) |
| Jeton forgé avec une fausse TSA | `CERTIFICATE = FAIL` (racine inconnue) |
| Requête remplacée | `TIMESTAMP = FAIL` (`REQUEST_MATCH`, `NONCE`) |
| Fichier ajouté ou retiré de l'archive | `COMPLETENESS = INCOMPLETE` |
| Archive piégée : traversée de répertoire, lien, bombe de décompression, polyglotte | Archive refusée (3.3) |

**Limites connues** (à rappeler à l'utilisateur) :

- **Champs déclaratifs.** Les champs de la section 4.3 marqués « Déclaratif », comme le titre, l'organisation ou le statut, peuvent être modifiés par quiconque recalcule l'empreinte du manifeste.
- **Fin de chaîne non ancrée.** Les événements postérieurs au dernier ancrage peuvent être réécrits ensemble sans être détectés.
- **Faux dossier daté plus tard.** Un faussaire peut constituer un nouveau dossier pour un fichier modifié, avec un horodatage valide **daté de plus tard**. Le passeport prouve l'antériorité (« existait au plus tard à »), pas l'absence d'une autre version.
- **Révocation inconnue.** La révocation d'un certificat de TSA n'est pas vérifiée hors ligne. Un horodatage antérieur à une révocation reste en principe valable (RFC 3161, section 4), sauf compromission de la clé de la TSA.
- **Racines.** La confiance dans le résultat ne dépasse pas la confiance dans les racines du vérificateur.

## 9. Versions

- Ce document décrit `veritas-passport-v1`. Un passeport v1 contient un manifeste `1.1`.
- **Ce qui exige une nouvelle version du passeport** : toute nouvelle entrée, tout changement des noms, des règles de la section 3 ou de l'algorithme d'un contrôle. Une nouvelle version du manifeste aussi.
- **Ce qui n'en exige pas** : le relèvement d'une limite de lecture (section 3.3) ou l'ajout d'une racine de confiance.

## 10. Exemple

`examples/passport-v1/` contient un passeport complet et synthétique :

- un court texte inventé, horodaté et ancré par une **TSA d'exemple** ;
- la racine de cette TSA, à ajouter explicitement (`example-root-ca.pem`) ;
- un `README.md` qui refait chaque contrôle à la main.

Le script `examples/generate_example.py` le régénère. Les tests de `tests/test_example_passport.py` vérifient que l'exemple et cette spécification restent d'accord.
