## Ce que change cette pull request

<!-- Une ou deux phrases. Exemple : « Ajoute l'inscription avec création de l'organisation personnelle. » -->

Closes #

## Pourquoi

<!-- La décision technique et ce qui a été écarté. C'est ce que tu reliras dans six mois. -->

## Vérifications

- [ ] Les tests passent (`pytest -q`, et `npm run lint && npm run typecheck && npm run build` si le frontend change)
- [ ] De nouveaux tests couvrent le comportement ajouté, y compris les cas d'erreur
- [ ] Migration : aucune, ou le cycle `upgrade → downgrade → upgrade` passe
- [ ] Aucun secret, aucune vraie pièce à conviction dans le diff
- [ ] `CLAUDE.md` est à jour si une décision ou l'état du projet a changé

## Points de sécurité à relire

<!-- Cryptographie, authentification, accès entre organisations, fichiers déposés... Écris « Aucun » sinon. -->
