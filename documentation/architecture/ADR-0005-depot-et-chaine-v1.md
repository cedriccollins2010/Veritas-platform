# ADR-0005 — Dépôt d'une preuve et format « veritas-custody-v1 »

Date : 2026-11-13 · Statut : accepté · Issue : #5 (et fondation de l'issue #7)

## Contexte

`POST /api/v1/evidence` reçoit un fichier jusqu'à 500 Mo, calcule son empreinte, le stocke et crée la preuve avec le premier événement de sa chaîne de possession. Cet événement doit être haché avec sa structure définitive : une empreinte ne doit jamais changer de définition après coup.

## Décisions

### Réception

1. **Lecture en flux avec l'analyseur de `python-multipart`**, et non `UploadFile` de FastAPI, qui reçoit toute la requête avant de rendre la main. Chaque morceau est compté, haché et écrit dans un fichier temporaire. La réception s'arrête dès que la limite est dépassée (413), et une taille annoncée trop grande (`Content-Length`) est refusée sans rien lire.
2. **Mémoire bornée** : environ 1 Mo de tampon, quelle que soit la taille du fichier (mesuré : 1,1 Mo pour 315 Mo ; serveur réel inchangé pour 400 Mo). Le hachage et l'écriture tournent dans un fil séparé, pour ne pas bloquer les autres requêtes.
3. **L'authentification et le jeton CSRF sont vérifiés avant de lire le corps** : un envoi non autorisé ne consomme ni disque ni temps de calcul. La transaction de lecture ouverte par ces vérifications est terminée avant la réception, pour ne pas occuper une connexion à la base pendant tout l'envoi.
3 bis. **Un envoi n'est accepté que complet** : l'analyseur doit avoir vu la fin de la partie fichier et la frontière finale du formulaire. Un corps tronqué (connexion coupée) est refusé (400) ; sans ce contrôle, un fichier partiel serait enregistré comme preuve. Un formulaire mal formé donne aussi 400, pas 500. Le titre refuse les caractères de contrôle.
4. **Le fichier n'est jamais interprété.** Le nom d'origine et le type déclaré sont conservés comme informations, nettoyés (dernier segment du chemin, caractères de contrôle retirés, longueur bornée), et ne servent ni de chemin ni à décider d'un traitement. Le contrôle du type réel viendra en phase 5.

### Création

5. **Vérification après copie.** L'original est relu dans le stockage et son empreinte recalculée ; elle doit être identique à celle de la réception (`digests_match`), sinon le dépôt échoue. `HASHED` garantit donc que le fichier conservé est exactement celui qui a été haché.
5 bis. **Deux transactions.** La preuve est d'abord enregistrée à l'état `PROCESSING`. Ensuite, le stockage du fichier, l'enregistrement du fichier, de l'empreinte (`source = SERVER`) et du premier événement, puis le passage à `HASHED` forment une seule transaction. En cas d'échec, la preuve passe à `FAILED` (avec une ligne `ERROR` dans `access_logs`), aucune ligne de fichier, d'empreinte ou d'événement ne reste, et le fichier temporaire est supprimé. Un envoi refusé pendant la réception (413, formulaire invalide) ne crée aucune ligne.
6. **Isolation des organisations** : toutes les lectures passent par une seule requête filtrée sur l'organisation courante. Une preuve d'une autre organisation et une preuve inexistante donnent la même réponse 404.

### Chaîne de possession, format v1

7. **`H(n) = SHA-256(H(n-1) ‖ JCS(E(n)))`**, où `H(n-1)` est l'empreinte précédente sous forme de 32 octets (absente pour le premier événement) et `JCS` la canonicalisation RFC 8785 (bibliothèque `rfc8785` de Trail of Bits, sans dépendance).
8. **Champs hachés `E(n)`** : `format` (`"veritas-custody-v1"`), `event_id`, `evidence_id`, `sequence_number`, `event_type`, `actor_id`, `occurred_at` (UTC, RFC 3339, microsecondes) et `data`. L'identifiant de l'événement est choisi par l'application, puisqu'il est haché. `created_at` n'est pas haché.
9. **Pas de nombres à virgule dans les données hachées**, et des entiers limités à ±(2^53−1) : leur représentation pourrait varier entre PostgreSQL, Python et JavaScript.
10. **Ce code vit dans `app/crypto/`** (`canonical.py`, `custody_chain.py`), sans dépendance vers le reste de VERITAS : le vérificateur autonome l'utilisera tel quel. L'ajout d'un événement (`app/custody/service.py`) verrouille d'abord la preuve (`SELECT ... FOR UPDATE`).
11. **Premier événement** : `FILE_RECEIVED`, avec l'identifiant du fichier, le nom d'origine, le type déclaré, la taille, l'algorithme, l'empreinte et le mode de stockage.

## Conséquences

- Changer les champs hachés exigera un nouveau format (`veritas-custody-v2`), jamais une modification de la v1.
- L'issue #7 ajoutera la vérification de la chaîne, les tests d'altération (modification, suppression, réordonnancement) et un test d'insertions concurrentes.
- `UPLOAD_TEMP_DIR` doit pouvoir contenir `MAX_UPLOAD_SIZE_MB` par dépôt simultané.
- En cas d'échec, la cause est journalisée côté serveur avec la clé du fichier éventuellement stocké sans référence (jamais supprimé), et le marquage `FAILED` est protégé contre une seconde panne.
- Les tests HTTP ne peuvent pas mesurer la mémoire : le `TestClient` de Starlette lit tout le corps avant de l'envoyer. La mesure se fait au niveau ASGI (`tests/test_upload.py`).
