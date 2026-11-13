# ADR-0011 — Ancrage de la tête de chaîne par la TSA

Date : 2026-11-13 · Statut : accepté · Issue : #26

## Contexte

La chaîne de possession détecte toute modification, suppression ou inversion d'un événement au milieu de la chaîne. Elle ne détecte pas, seule, la suppression des **derniers** événements, ni une réécriture complète avec des empreintes recalculées par quelqu'un qui contrôle la base (ADR-0005, limite connue). Le document de référence prévoit d'ancrer la tête de chaîne par un horodatage RFC 3161 à l'export.

## Décisions

1. **L'ancrage horodate l'empreinte de la tête de chaîne** : une ligne `timestamp_records` avec `purpose = CHAIN_HEAD`, `hash_record_id` nul, `message_imprint` = empreinte de l'événement de tête, et son numéro de séquence dans la nouvelle colonne **`anchored_sequence_number`** (migration 0003). Une contrainte impose que cette colonne soit remplie pour un ancrage, et vide pour l'horodatage d'un fichier.
2. **Action explicite, `POST /evidence/{id}/anchor`**, et non un effet de bord d'une lecture : un `GET` ne doit rien modifier, alors qu'ancrer appelle la TSA et écrit en base. L'export complet (phase 4) l'appellera. Réponses : 200 (`ANCHORED` ou `REUSED`), 503 (TSA indisponible), 502 (jeton refusé), 409 (preuve incomplète), 404.
3. **Même chemin que l'horodatage d'un fichier** (ADR-0010) : verrou de la preuve, appel à la TSA, conservation de la requête et du jeton, vérification complète (`verify_timestamp_token` avec l'empreinte de la tête comme empreinte attendue), journal `evidence.anchor`.
4. **Événement `CHAIN_ANCHORED` ajouté après l'ancrage** : identifiant de l'ancrage, numéro et empreinte ancrés, TSA, date de génération, numéro de série, empreinte du fichier `.tsr`. Il désigne l'ancrage, mais il n'est lui-même couvert que par l'ancrage suivant ; le manifeste devra le dire.
5. **Pas d'ancrage inutile** : si le seul événement postérieur au dernier ancrage `VALID` est son propre `CHAIN_ANCHORED`, l'ancrage est réutilisé (`REUSED`). Sans cette règle, l'événement `CHAIN_ANCHORED`, qui change la tête, provoquerait un nouvel ancrage à chaque export.
6. **Vérification pure `verify_anchor(événements, numéro ancré, empreinte ancrée)`** dans `app/crypto/custody_chain.py` : `PASS` si l'événement ancré est présent avec l'empreinte horodatée ; `FAIL` s'il manque (fin supprimée) ou si son empreinte diffère (réécriture) ; `UNKNOWN` sans ancrage, jamais `PASS`. Le vérificateur autonome l'utilisera avec `verify_chain` et `verify_timestamp_token`.

## Conséquences

- La limite connue de l'ADR-0005 est fermée **jusqu'au numéro ancré** : suppression en fin de chaîne et réécriture complète sont détectées (testé). Les événements postérieurs au dernier ancrage restent couverts seulement par la chaîne, jusqu'au prochain ancrage.
- Si la TSA est indisponible, la tête n'est pas ancrée : l'export restera possible, mais le manifeste (issue #27) devra l'indiquer, et le vérificateur répondra `UNKNOWN` pour l'ancrage.
