# ADR-0008 — Client d'horodatage RFC 3161

Date : 2026-11-13 · Statut : accepté · Issue : #23

## Contexte

Une autorité d'horodatage (TSA) signe un jeton qui atteste qu'une empreinte existait au plus tard à une date donnée. VERITAS doit obtenir ce jeton pour l'empreinte d'un fichier téléversé, et aussi pour une empreinte déclarée (mode empreinte seule), dont il n'a pas le fichier.

## Décisions

1. **Interface `TimestampProvider`** (`app/timestamp/provider.py`) : `request_timestamp(digest) -> TimestampExchange` (nom et URL de la TSA, empreinte, nonce, requête et réponse brutes). Le reste du code ne connaît qu'elle ; le module ne connaît ni utilisateur ni organisation.
2. **`rfc3161-client` 1.0.9** (Trail of Bits, >= 1.0.3 exigé pour la CVE-2025-52556) pour décoder et, à l'issue #24, vérifier les jetons. **`httpx` 0.28.1** (dernière version stable) passe de dépendance de test à dépendance d'exécution, pour l'envoi HTTP.
3. **Requête encodée par VERITAS**, sur décision de la développeuse. `rfc3161-client` sait seulement construire une requête en hachant lui-même des données, alors que VERITAS horodate une empreinte déjà calculée ou déclarée. La requête est une structure ASN.1 fixe d'environ 60 octets (version, empreinte SHA-256, nonce, `certReq`), encodée en DER en une quinzaine de lignes (`app/timestamp/request.py`). Ce n'est pas de la cryptographie. Garde-fous : chaque requête est relue par l'analyseur de `rfc3161-client` et ses champs comparés aux valeurs voulues avant envoi, et les tests vérifient qu'elle est identique octet pour octet à celle d'OpenSSL (`openssl ts -query`) et à celle de `rfc3161-client` pour les mêmes données. Écartés : ajouter `pyasn1` (deux dépendances pour une structure) et horodater `SHA-256(empreinte)` (double hachage non standard, invérifiable avec `openssl ts -verify -data`).
4. **Contrôles à la réception** : HTTP 200, type `application/timestamp-reply`, taille maximale de 64 Kio, aucune redirection suivie, réponse décodable, statut « accordé », **nonce et empreinte identiques à la requête** (une réponse rejouée ou destinée à une autre empreinte est refusée). La vérification complète (signature, chaîne de certificats, usage `timeStamping`) est l'objet de l'issue #24.
5. **Erreurs typées** : `TsaUnavailableError` (injoignable, délai dépassé : réessayer plus tard), `TsaProtocolError`, `TsaRejectedError`, `TsaResponseMismatchError`. Le délai est borné par `TSA_TIMEOUT_SECONDS` (10 s par défaut).
6. **Fournisseurs** : DigiCert (`http://timestamp.digicert.com`, développement et pilote) et FreeTSA (`https://freetsa.org/tsr`, tests), choisis par `TSA_PROVIDER`. Le transport HTTP simple de DigiCert est acceptable : le jeton est signé, son intégrité ne dépend pas du canal, et seule l'empreinte est envoyée.
7. **Conservation** : la requête (`.tsq`) et la réponse (`.tsr`) originales sont enregistrées octet pour octet dans le stockage (`timestamps/<uuid>.tsq|.tsr`), pour que le passeport les embarque et qu'un tiers refasse la vérification avec ses propres outils.
8. **Tests sans TSA réelle** : une autorité d'horodatage de test est créée localement avec OpenSSL (racine + certificat de TSA avec `extendedKeyUsage = timeStamping`) ; elle répond à de vraies requêtes par de vrais jetons, validés aussi par `openssl ts -verify`. Seul le test `tsa_live` (T04) appelle FreeTSA ; il est ignoré sans accès au réseau.

## Conséquences

- **Point à surveiller** : `rfc3161-client` applique strictement DER et refuse une réponse dont les certificats ne sont pas triés comme l'exige DER (cas d'OpenSSL quand il joint plusieurs certificats). La TSA de test n'en joint donc qu'un. Le test `tsa_live` en CI dira si les réponses de FreeTSA sont acceptées ; DigiCert devra être vérifié de même avant le pilote.
- L'interface `rfc3161_client._rust.parse_timestamp_request`, utilisée en garde-fou, n'est pas publique : la version de la bibliothèque est figée, et un test échouera si elle change.
