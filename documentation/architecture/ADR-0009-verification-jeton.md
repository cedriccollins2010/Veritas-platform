# ADR-0009 — Vérification d'un jeton RFC 3161

Date : 2026-11-13 · Statut : accepté · Issue : #24

## Contexte

Un jeton d'horodatage ne vaut que s'il est vérifié : signé par une TSA reconnue, pour la bonne empreinte, en réponse à la bonne requête. Le document de référence et `CLAUDE.md` exigent un résultat par contrôle, `VALID` seulement si tout est `PASS`, `UNKNOWN` quand l'information manque, et des verdicts comparés à ceux d'`openssl ts -verify`.

## Décisions

1. **Fonction pure `verify_timestamp_token(réponse, requête, empreinte, racines)`** dans `app/crypto/timestamp_verification.py` : ni base, ni réseau, ni horloge. Le vérificateur autonome la reprendra telle quelle.
2. **Un résultat par contrôle.** Obligatoires : `RESPONSE_READABLE`, `STATUS_GRANTED`, `MESSAGE_IMPRINT` (SHA-256 et empreinte attendue), `REQUEST_MATCH`, `NONCE`, `TSA_CERTIFICATE` (certificat désigné par la signature, usage critique `id-kp-timeStamping`), `SIGNATURE_AND_CHAIN`. Informatif : `REVOCATION`, toujours `UNKNOWN` hors ligne (OCSP/CRL après le MVP) ; il ne bloque pas la validité, mais ne prétend jamais avoir été vérifié.
3. **La cryptographie est déléguée** : la signature et la chaîne de certificats (valides à la date d'horodatage) sont vérifiées par le `Verifier` de `rfc3161-client`. Les autres contrôles, simples, sont faits séparément pour produire un résultat par contrôle (le `Verifier` s'arrête à la première erreur).
4. **Robustesse** : un jeton malformé, même partiellement (certificat illisible, structure altérée), donne des `FAIL` et jamais d'exception. Testé en modifiant chacun des quelque mille octets d'un jeton.
5. **Racines de confiance versionnées** dans `app/timestamp/trust/`, avec leur provenance dans `trust/README.md`. DigiCert Trusted Root G4 est issue du magasin de Mozilla (`certifi`) et son empreinte est vérifiée par un test. **La racine de FreeTSA n'a pas pu être téléchargée** depuis l'environnement de développement (réseau bloqué) : la procédure pour l'ajouter est documentée. Les tests utilisent une TSA locale OpenSSL et une seconde autorité « imposteur ».
6. **Résultat enregistré** dans `timestamp_records` (`apply_verification`) : `validation_status` (`VALID` ou `INVALID`), date de génération, numéro de série, policy OID, et la liste des contrôles en échec dans `error_detail`. La contrainte de la base refuse `VALID` sans jeton conservé ni date (testé).

## Conséquences

- **Comparaison avec OpenSSL** : sur un corpus (jeton valide, autre empreinte, autre nonce, autre TSA, une quarantaine de jetons altérés d'un octet), nos verdicts sont identiques à ceux d'`openssl ts -verify`.
- **Malléabilité connue de CMS** : une dizaine d'octets sur environ mille ne sont pas couverts par la signature (numéros de version de `SignedData` et `SignerInfo`, étiquette de l'algorithme de signature). Les modifier laisse le jeton valide, pour nous comme pour OpenSSL, sans changer ce qui est attesté (date, empreinte, nonce, numéro de série) : un test le vérifie à chaque position. Pour que toute retouche du fichier `.tsr` conservé reste visible, **son empreinte sera enregistrée dans la chaîne de possession** (issue #25).
- `rfc3161-client` refuse les statuts « accordé avec modifications » : plus strict qu'OpenSSL, sans conséquence avec DigiCert et FreeTSA, qui accordent simplement.
