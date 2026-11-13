# Racines de confiance des autorités d'horodatage

Un jeton RFC 3161 n'est accepté que si la chaîne de certificats de la TSA remonte à l'une
des racines de ce dossier. Ajouter une racine, c'est décider de faire confiance à une
autorité : chaque ajout passe par une pull request relue, avec sa provenance ci-dessous.

| Fichier | Autorité | Empreinte SHA-256 | Provenance |
| --- | --- | --- | --- |
| `digicert-trusted-root-g4.pem` | DigiCert Trusted Root G4 (racine des jetons de `timestamp.digicert.com`) | `55:2F:7B:DC:F1:A7:AF:9E:6C:E6:72:01:7F:4F:12:AB:F7:72:40:C7:8E:76:1A:C2:03:D1:D9:D2:0A:C8:99:88` | Magasin de certificats de Mozilla, paquet `certifi` 2026.10.23 ; empreinte identique à celle publiée par DigiCert. Valide jusqu'au 15 janvier 2038. |

## Racine de FreeTSA (à ajouter)

FreeTSA (`https://freetsa.org/tsr`) utilise sa propre racine, absente des magasins de
confiance courants. Elle n'a pas pu être téléchargée depuis l'environnement de
développement (réseau bloqué). Pour l'ajouter, depuis une machine qui a accès au réseau :

```bash
curl -sSfO https://freetsa.org/files/cacert.pem
openssl x509 -in cacert.pem -noout -subject -enddate -fingerprint -sha256
```

Comparer l'empreinte avec celle publiée sur https://freetsa.org/ (page d'accueil et
documentation), puis enregistrer le fichier sous `freetsa-root.pem` et compléter le
tableau. FreeTSA ne sert qu'aux tests : sa racine ne doit jamais être utilisée pour
certifier une vraie preuve.

## Vérifier une racine

```bash
openssl x509 -in digicert-trusted-root-g4.pem -noout -subject -enddate -fingerprint -sha256
```
