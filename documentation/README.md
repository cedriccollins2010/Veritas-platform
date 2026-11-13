# Documentation VERITAS

| Dossier | Contenu |
| --- | --- |
| `requirements/` | Spécification produit. Y placer l'export Markdown du **Document de référence unifié** (`veritas-reference.md`). |
| `architecture/` | Décisions d'architecture (ADR), schémas. |
| `security/` | Modèle de menaces, procédures de sauvegarde et de restauration. |
| `sources/` | Les quatre documents d'origine (cahier des charges, TDD v1.0, blueprint, stratégie). **Historiques** : le document de référence unifié les remplace en cas de contradiction. |

Le Document de référence unifié est un doc Claude modifiable. Pour le mettre à jour ici : ouvrir le doc, menu Exporter → Markdown, puis remplacer `requirements/veritas-reference.md`.

La référence de l'API est générée par FastAPI (`/docs`, `/openapi.json`). La spécification publique du passeport de preuve et les schémas JSON du manifeste sont dans `verifier/` (Apache 2.0) : `verifier/SPECIFICATION.md`, `verifier/src/veritas_verifier/schemas/`.
