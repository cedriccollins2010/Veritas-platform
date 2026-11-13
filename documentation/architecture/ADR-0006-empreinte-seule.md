# ADR-0006 — Mode « empreinte seule »

Date : 2026-11-13 · Statut : accepté · Issue : #6

## Contexte

Certaines pièces ne doivent pas quitter la garde de l'analyste (image disque de plusieurs centaines de Go, capture réseau sensible). Le document de référence prévoit qu'il puisse alors enregistrer seulement l'empreinte, calculée sur son poste. Le serveur ne voit jamais le fichier : il ne peut pas garantir que l'empreinte correspond à quoi que ce soit. Il peut seulement attester l'avoir reçue, à une date donnée, de la part d'un utilisateur donné.

## Décisions

1. **Route séparée, `POST /api/v1/evidence/hash-only`, corps JSON** (nom d'origine, taille, empreinte, titre, type et outil de calcul facultatifs). Le document de référence évoquait un formulaire multipart pour les deux modes ; sans fichier, il ne reste que des données structurées, que JSON et Pydantic valident strictement. Téléverser un fichier et déclarer une empreinte restent deux opérations distinctes, sans ambiguïté.
2. **Empreinte validée par `normalize_digest`** : exactement 64 caractères hexadécimaux, mise en minuscules ; sinon 400, et rien n'est créé.
3. **L'origine est enregistrée partout où elle compte** : `evidence_files.storage_mode = HASH_ONLY` et `storage_key` nul, `hash_records.source = CLIENT`, et un événement de possession dédié, `HASH_DECLARED`, dont les données hachées indiquent `hash_source = CLIENT` et l'outil déclaré (`hash_tool`, enregistré aussi dans `engine_version`). Le premier événement d'un fichier téléversé indique désormais `hash_source = SERVER`.
4. **`verified_by_server` dans chaque réponse**, calculé à partir de `hash_records.source` : vrai seulement si VERITAS a calculé l'empreinte sur le fichier reçu. C'est le champ que l'interface et le manifeste devront lire ; une preuve en empreinte seule ne peut donc pas être présentée comme vérifiée par le serveur.
5. **État `HASHED`** : l'empreinte est enregistrée, comme pour un fichier téléversé. La différence de garantie est portée par `source` et `verified_by_server`, pas par l'état.
6. **Une seule transaction** : sans fichier, aucune étape ne peut échouer à moitié.

## Conséquences

- Le manifeste (issue #8) doit reprendre `storage_mode`, `source` et `verified_by_server`, et le vérificateur devra signaler qu'une empreinte déclarée n'a pas été vérifiée contre un fichier tant que le fichier n'est pas fourni.
- La commande `veritas hash` (phase 4) calculera l'empreinte localement et appellera cette route.
- La taille déclarée est limitée à 2^53−1 octets, comme tout entier haché (I-JSON).
