# Passeport d'exemple — vérification à la main

Ce dossier contient un passeport `veritas-passport-v1` complet et **entièrement synthétique** :

- `veritas-passport-6f1c3a52-9d0e-4b7a-8c21-5e4f0a9b7d10.zip` : le passeport. Il contient un court texte inventé, déposé, horodaté, puis dont la chaîne de possession a été ancrée.
- `example-root-ca.pem` : la racine de la **TSA d'exemple** qui a signé les deux jetons. Elle n'est reconnue par aucun vérificateur par défaut : il faut l'ajouter explicitement, ce que font les commandes ci-dessous. Ne l'installez jamais comme racine de confiance de votre système.

Les étapes suivantes refont chaque contrôle de `SPECIFICATION.md` (section 5) sans le code de VERITAS. Il faut `unzip`, `sha256sum`, OpenSSL 3, et Python 3 avec le paquet `rfc8785` pour la chaîne de possession. Les valeurs affichées sont celles de ce passeport. Si vous régénérez l'exemple, elles changent.

```bash
mkdir /tmp/passeport && cd /tmp/passeport
unzip -q <chemin>/veritas-passport-6f1c3a52-9d0e-4b7a-8c21-5e4f0a9b7d10.zip
ls -R            # manifest.json, original/<id>, timestamp/<id>.tsr et .tsq — rien d'autre
```

## 1. Complétude

Le manifeste annonce un fichier conservé (`STORED`) et deux jetons, `FILE` et `CHAIN_HEAD`. L'archive doit donc contenir exactement six entrées :

- `manifest.json` ;
- `original/c4e8a1f2-7b3d-4e5f-9a6b-0c1d2e3f4a50` ;
- `timestamp/e1f2a3b4-c5d6-4e7f-8091-a2b3c4d5e6f7.tsr` et `.tsq` (jeton du fichier) ;
- `timestamp/f7e6d5c4-b3a2-4918-8f7e-6d5c4b3a2918.tsr` et `.tsq` (ancrage).

## 2. Intégrité du fichier

```bash
sha256sum original/c4e8a1f2-7b3d-4e5f-9a6b-0c1d2e3f4a50
# d9e5c92cb677bebbfab05a2e681df0a351fa926786cac05a13b615838e892430
python3 -c "import json; print(json.load(open('manifest.json'))['files'][0]['hashes'][0]['digest'])"
# la même valeur
```

## 3. Manifeste : forme canonique et empreinte

```bash
python3 - <<'EOF'
import hashlib, json, rfc8785
raw = open("manifest.json", "rb").read()
manifest = json.loads(raw)
assert rfc8785.dumps(manifest) == raw, "pas sous forme canonique"
body = {k: v for k, v in manifest.items() if k != "manifest_digest"}
print(hashlib.sha256(rfc8785.dumps(body)).hexdigest())
print(manifest["manifest_digest"]["value"])   # doit être identique
EOF
```

## 4. Jetons d'horodatage et chaîne de certificats

Les deux commandes doivent afficher `Verification: OK`.

```bash
ROOT=<chemin>/example-root-ca.pem
openssl ts -verify -queryfile timestamp/e1f2a3b4-c5d6-4e7f-8091-a2b3c4d5e6f7.tsq \
  -in timestamp/e1f2a3b4-c5d6-4e7f-8091-a2b3c4d5e6f7.tsr -CAfile "$ROOT"
openssl ts -verify -queryfile timestamp/f7e6d5c4-b3a2-4918-8f7e-6d5c4b3a2918.tsq \
  -in timestamp/f7e6d5c4-b3a2-4918-8f7e-6d5c4b3a2918.tsr -CAfile "$ROOT"
```

Avec `-queryfile`, OpenSSL contrôle trois choses à la fois : l'empreinte horodatée est celle de la requête, le nonce est identique, et la signature remonte à la racine.

Il reste à relier chaque jeton au manifeste :

- **Jeton du fichier.** Son empreinte (`Message data` dans la commande ci-dessous) doit être celle du fichier (étape 2).
- **Jeton d'ancrage.** Son empreinte doit être l'`event_hash` de l'événement n° 2 de la chaîne : `6333256b2350f2204a2243b83878d2c713f1e312cd7f330c59e517a91213755e`.

```bash
openssl ts -reply -in timestamp/e1f2a3b4-c5d6-4e7f-8091-a2b3c4d5e6f7.tsr -text
# Time stamp, Serial number, Policy OID (2.999.1 : arc réservé aux exemples)
# et Message data doivent concorder avec l'entrée « timestamps » du manifeste.
```

OpenSSL vérifie les certificats **à la date d'aujourd'hui**, alors que la spécification les vérifie à la date du jeton. Les certificats d'exemple sont valables jusqu'en 2036. Au-delà, ajoutez `-attime <date du jeton en secondes Unix>`.

## 5. Chaîne de possession et ancrage

```bash
python3 - <<'EOF'
import hashlib, json, rfc8785
m = json.load(open("manifest.json"))
previous = bytes(32)                       # H(0) : 32 octets nuls
for e in m["custody"]["events"]:
    payload = {"format": "veritas-custody-v1", "event_id": e["event_id"],
               "evidence_id": m["evidence"]["id"], "sequence_number": e["sequence_number"],
               "event_type": e["event_type"], "actor_id": e["actor_id"],
               "occurred_at": e["occurred_at"], "event_data": e["event_data"]}
    h = hashlib.sha256(previous + rfc8785.dumps(payload)).hexdigest()
    print(e["sequence_number"], e["event_type"], h == e["event_hash"])
    previous = bytes.fromhex(h)
anchor = next(t for t in m["timestamps"] if t["purpose"] == "CHAIN_HEAD")
n = anchor["anchored_sequence_number"]
print("ancrage n°", n, m["custody"]["events"][n - 1]["event_hash"] == anchor["message_imprint"])
EOF
# 1 FILE_RECEIVED True / 2 TIMESTAMP_ATTACHED True / 3 CHAIN_ANCHORED True / ancrage n° 2 True
```

L'événement n° 3 (`CHAIN_ANCHORED`) suit l'ancrage : il n'est couvert que par la chaîne. C'est ce qu'indique `timestamp_status.unanchored_events = 1`.

## Résultat attendu

| Contrôle | Résultat |
| --- | --- |
| `MANIFEST` | `PASS` |
| `INTEGRITY` | `PASS` |
| `TIMESTAMP` | `PASS` |
| `CERTIFICATE` | `PASS` (avec la racine d'exemple ajoutée explicitement ; `FAIL` sans elle) |
| `CUSTODY` | `PASS` (événements 1 et 2 ancrés, l'événement 3 couvert par la chaîne seulement) |
| `COMPLETENESS` | `COMPLETE` |
| Verdict | `VALID` |

Une fois écrit (#36), `veritas verify` donnera le même verdict avec `--trust-root example-root-ca.pem`. Modifiez un seul octet du fichier dans `original/`, et `INTEGRITY` passe à `FAIL`.

Le texte du fichier est inventé, et les identifiants comme les noms sont fictifs. Ce passeport ne prouve rien d'autre que le bon fonctionnement du format.
