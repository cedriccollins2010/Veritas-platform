Je te propose de formaliser VERITAS comme un véritable projet informatique, avec un document de spécifications fonctionnelles et techniques (cahier des charges).

Je vais le rédiger comme un document professionnel qui pourrait servir à trois choses :

* Guider ton développement en tant que développeuse principale du projet.

* Servir de référence pour les décisions d'architecture et les choix technologiques.

* Présenter le projet à de futurs partenaires, collaborateurs ou investisseurs.

Le document tiendra compte d'une contrainte essentielle : VERITAS doit être réalisable progressivement par une seule développeuse de niveau intermédiaire, sans sacrifier la sécurité, la fiabilité ni les possibilités d'évolution.

# CAHIER DES CHARGES FONCTIONNEL ET TECHNIQUE
# PROJET VERITAS
### Plateforme universelle de certification, de traçabilité et de vérification des preuves numériques

**Version :** 1.0
**Date :** 11 novembre 2026
**Statut :** Document de spécifications initiales
**Type de projet :** Application web SaaS
**Responsable du développement :** Développeuse principale (équipe technique initiale : une personne)

---

# 1. PRÉSENTATION GÉNÉRALE DU PROJET

## 1.1. Contexte

La transformation numérique entraîne une augmentation considérable de la production, de la circulation et de la conservation des données numériques.

Les documents électroniques, les photographies, les vidéos, les courriels, les journaux systèmes et les fichiers informatiques constituent désormais des éléments susceptibles d'être utilisés comme preuves dans différents contextes :

- Enquêtes judiciaires et investigations numériques.
- Analyses de cybersécurité et informatique légale (Digital Forensics).
- Réclamations et dossiers d'assurance.
- Transactions commerciales.
- Gestion documentaire des entreprises.
- Litiges entre particuliers et organisations.
- Audits de conformité et contrôles internes.

Cependant, plusieurs difficultés persistent :

- Modification ou altération des fichiers numériques.
- Contestation de la date de création ou de réception d'un document.
- Difficulté à démontrer l'intégrité d'un fichier.
- Absence de traçabilité fiable des manipulations.
- Difficulté à partager une preuve tout en préservant son authenticité et sa confidentialité.
- Dépendance à l'égard de plateformes propriétaires pour vérifier les preuves.

VERITAS ambitionne de répondre à ces difficultés en proposant une infrastructure numérique indépendante permettant de créer, conserver, tracer et vérifier des preuves numériques.

## 1.2. Vision du projet

Faire de VERITAS une infrastructure de confiance numérique accessible à tous, capable de fournir des mécanismes normalisés et vérifiables de protection de l'intégrité des données.

La plateforme ne cherchera pas simplement à stocker des fichiers. Elle cherchera à établir un historique cryptographiquement vérifiable de leur existence, de leur intégrité et des événements associés.

## 1.3. Mission

Développer une plateforme web permettant à un utilisateur ou à une organisation de :

1. Enregistrer une preuve numérique.
2. Calculer son empreinte cryptographique.
3. Obtenir une preuve d'horodatage fiable.
4. Enregistrer les événements associés à cette preuve.
5. Conserver les éléments nécessaires à sa vérification.
6. Permettre à un tiers indépendant de vérifier son intégrité.

---

# 2. OBJECTIFS DU PROJET

## 2.1. Objectif général

Concevoir et développer une application web sécurisée qui permet de constituer des dossiers de preuves numériques vérifiables indépendamment.

## 2.2. Objectifs spécifiques

- Garantir la détection de toute modification du contenu original.
- Fournir un mécanisme d'horodatage cryptographique.
- Assurer la traçabilité des opérations effectuées sur les preuves.
- Protéger les documents contre les accès non autorisés.
- Générer des certificats de vérification.
- Permettre une vérification indépendante sans nécessiter de compte utilisateur.
- Proposer une API permettant l'intégration avec des applications externes.
- Préparer une architecture évolutive permettant d'ajouter de nouveaux mécanismes de certification.

## 2.3. Indicateurs de réussite

Le MVP sera considéré comme fonctionnel lorsque :

- Un utilisateur pourra téléverser un document.
- La plateforme pourra calculer et enregistrer son empreinte SHA-256.
- Un horodatage RFC 3161 pourra être obtenu et vérifié.
- Un dossier de preuve pourra être généré.
- Une modification du document pourra être détectée.
- Un tiers pourra vérifier la preuve indépendamment.
- Les événements du dossier pourront être contrôlés cryptographiquement.

---

# 3. UTILISATEURS CIBLES

## 3.1. Particuliers

Personnes souhaitant protéger des documents, contrats, photographies ou échanges numériques.

## 3.2. Entreprises

Organisations souhaitant renforcer la traçabilité et la fiabilité de leurs documents numériques.

## 3.3. Professionnels du droit

Avocats, juristes et autres professionnels souhaitant disposer d'un mécanisme de vérification de l'intégrité des documents.

## 3.4. Professionnels de la cybersécurité

Analystes SOC, spécialistes en réponse aux incidents, experts en informatique légale et consultants en cybersécurité.

## 3.5. Compagnies d'assurance

Organisations souhaitant documenter et vérifier les éléments numériques associés aux réclamations.

---

# 4. PÉRIMÈTRE FONCTIONNEL

Le développement sera divisé en trois grandes versions.

## 4.1. Version 1 : MVP

Cette version représente le produit minimum commercialisable à tester.

Fonctionnalités :

- Création de compte et authentification.
- Gestion des utilisateurs.
- Téléversement de documents PDF.
- Calcul d'empreintes SHA-256.
- Horodatage RFC 3161.
- Enregistrement des métadonnées.
- Historique des événements.
- Génération d'un dossier de preuve.
- Vérification indépendante.
- Tableau de bord utilisateur.

## 4.2. Version 2 : Extension fonctionnelle

- Support des images, vidéos, fichiers ZIP et journaux systèmes.
- Gestion des organisations et des équipes.
- Partage sécurisé des preuves.
- Gestion avancée des permissions.
- API publique.
- Rapports de vérification avancés.
- Stockage avec mécanismes de rétention immuable.
- Export de dossiers de preuves au format standardisé.

## 4.3. Version 3 : Plateforme avancée

- Analyse assistée par intelligence artificielle.
- Détection d'incohérences dans les métadonnées.
- Analyse de vidéos et de contenus synthétiques.
- Certification de lots de fichiers.
- Arbres de Merkle pour les preuves multiples.
- Intégrations avec des systèmes judiciaires et des plateformes de cybersécurité.
- Infrastructure de vérification distribuée.
- Interopérabilité avec des systèmes externes.

L'intelligence artificielle ne devra jamais être présentée comme une autorité certifiant la vérité d'un document.

---

# 5. SPÉCIFICATIONS FONCTIONNELLES DÉTAILLÉES

## 5.1. Module d'authentification

Le système doit permettre :

- La création d'un compte.
- La connexion sécurisée.
- La déconnexion.
- La réinitialisation du mot de passe.
- La gestion des sessions.
- La vérification de l'adresse électronique.

Évolutions souhaitées :

- Authentification multifacteur (MFA).
- Authentification par fournisseur d'identité externe.
- Gestion des rôles et permissions.

Rôles initiaux :

| Rôle | Permissions |
|---|---|
| Utilisateur | Déposer et consulter ses preuves |
| Administrateur | Administrer la plateforme |
| Vérificateur | Vérifier les dossiers auxquels il a accès |

## 5.2. Module de dépôt des preuves

L'utilisateur doit pouvoir sélectionner et téléverser un fichier.

Pour le MVP :

- Format accepté : PDF.
- Taille maximale initiale : 25 Mo, configurable.
- Vérification du type réel de fichier.
- Vérification des limites de taille.
- Attribution d'un identifiant unique.
- Enregistrement de la date de réception par la plateforme.

Le fichier original doit être conservé sans modification.

Le système doit éviter de modifier automatiquement le document avant le calcul de son empreinte.

## 5.3. Module cryptographique

Ce module constitue le cœur technique de VERITAS.

À chaque dépôt, le système doit calculer une empreinte cryptographique SHA-256.

Exemple :

Fichier : contrat.pdf

Empreinte :

`SHA256 = 9f86d081884c7d659a2feaa0c55ad015...`

L'empreinte représente une signature mathématique du contenu du fichier.

Si un seul octet du document est modifié, son empreinte devrait être différente, avec une probabilité de collision négligeable pour un usage normal.

Le système devra :

- Calculer l'empreinte du fichier.
- Enregistrer l'algorithme utilisé.
- Associer l'empreinte à un identifiant unique.
- Permettre de recalculer l'empreinte lors d'une vérification.
- Comparer les deux valeurs.

Résultat possible :

- INTACT : les empreintes correspondent.
- MODIFIÉ : les empreintes sont différentes.
- NON VÉRIFIABLE : les éléments nécessaires à la vérification sont incomplets.

## 5.4. Module d'horodatage

VERITAS devra intégrer un service d'horodatage conforme à la norme RFC 3161.

Objectif : obtenir un jeton d'horodatage signé par une autorité d'horodatage (TSA).

Processus :

1. Calculer l'empreinte du document.
2. Envoyer cette empreinte au service TSA.
3. Recevoir un jeton d'horodatage signé.
4. Conserver le jeton original.
5. Vérifier sa signature et sa chaîne de certificats.
6. Associer le jeton au dossier de preuve.

Le jeton devra permettre de démontrer que l'empreinte correspondante existait au plus tard à l'instant indiqué par l'autorité d'horodatage.

VERITAS devra conserver les informations nécessaires à la validation du jeton, notamment les certificats pertinents et les informations de révocation disponibles.

## 5.5. Module de traçabilité et chaîne de possession

Ce module est particulièrement important pour les applications en informatique légale.

Chaque événement associé à une preuve devra être enregistré.

Exemples :

- Création d'une preuve.
- Téléversement.
- Calcul d'empreinte.
- Obtention d'un horodatage.
- Consultation.
- Téléchargement.
- Partage.
- Vérification.
- Archivage.

Chaque événement devra comporter :

- Identifiant de l'événement.
- Identifiant de la preuve.
- Type d'opération.
- Date et heure.
- Acteur ou service responsable.
- Résultat de l'opération.
- Empreinte de l'événement précédent.
- Empreinte cryptographique de l'événement courant.

Les événements seront liés cryptographiquement afin de rendre détectable toute modification de l'historique.

Une architecture de journal append-only devra être privilégiée.

Pour renforcer la confiance, les événements critiques pourront également faire l'objet d'horodatages externes périodiques.

**Important :** une chaîne de hachage seule ne rend pas un historique absolument immuable. La protection devra également reposer sur les contrôles d'accès, la séparation des privilèges, les sauvegardes et, à terme, un stockage avec verrouillage de rétention.

## 5.6. Module de génération du dossier de preuve

À la fin du processus, VERITAS devra générer un dossier téléchargeable.

Contenu minimal :

1. Identifiant unique de la preuve.
2. Nom du fichier.
3. Taille du fichier.
4. Empreinte SHA-256.
5. Date de réception.
6. Jeton d'horodatage RFC 3161.
7. Historique des événements.
8. Informations de validation cryptographique.
9. Version du système ayant produit le dossier.

Formats de sortie envisagés :

- PDF : rapport lisible.
- JSON : manifeste structuré.
- Fichier TSA : jeton d'horodatage original.
- Fichier original : document déposé, selon les droits de l'utilisateur.

Le dossier devra pouvoir être vérifié sans dépendre exclusivement des serveurs de VERITAS.

## 5.7. Module de vérification indépendante

Ce module constitue l'une des principales différenciations du produit.

Un tiers devra pouvoir vérifier un dossier de preuve sans créer de compte.

Processus :

1. Accéder au portail de vérification.
2. Déposer le document et son dossier de preuve.
3. Recalculer l'empreinte SHA-256.
4. Comparer les empreintes.
5. Vérifier le jeton RFC 3161.
6. Vérifier la cohérence de l'historique cryptographique.
7. Générer un rapport.

Le rapport devra présenter :

- Intégrité du document.
- Validité du jeton d'horodatage.
- Cohérence de la chaîne de possession.
- Éléments manquants.
- Limites de la vérification.

Le vérificateur ne devra pas conclure que le contenu du document est vrai, que son auteur est authentique ou que sa valeur juridique est automatiquement reconnue.

---

# 6. EXIGENCES NON FONCTIONNELLES

## 6.1. Sécurité

La sécurité devra être intégrée dès la conception.

Exigences :

- Utilisation de HTTPS/TLS.
- Stockage sécurisé des secrets.
- Chiffrement des fichiers au repos.
- Gestion stricte des permissions.
- Protection contre les attaques courantes OWASP.
- Validation des entrées utilisateur.
- Protection contre les téléversements malveillants.
- Journalisation des événements de sécurité.
- Sauvegardes sécurisées.
- Gestion des vulnérabilités et mises à jour.

Les fichiers déposés ne devront jamais être exécutés sur le serveur.

## 6.2. Confidentialité

La plateforme devra appliquer les principes de minimisation des données.

Les preuves ne devront pas être accessibles publiquement par défaut.

Les utilisateurs devront pouvoir contrôler les accès à leurs documents.

Le système devra prévoir une politique de conservation et de suppression des fichiers, tout en distinguant la suppression des contenus de la conservation des éléments cryptographiques nécessaires à l'audit.

## 6.3. Performance

Objectifs initiaux à valider par des tests :

- Temps de réponse des interfaces : inférieur à 2 secondes pour les opérations courantes.
- Calcul d'empreinte : traitement en flux pour éviter de charger les fichiers volumineux entièrement en mémoire.
- Vérification d'un petit document : objectif inférieur à 5 secondes, hors délai du service d'horodatage.
- Gestion des erreurs sans perte silencieuse des opérations.

## 6.4. Disponibilité

Le MVP devra disposer de mécanismes de sauvegarde et de restauration.

Objectif initial : disponibilité de 99,5 % à terme, sous réserve de l'infrastructure et des fournisseurs utilisés.

## 6.5. Évolutivité

L'architecture devra permettre :

- L'ajout de nouveaux algorithmes cryptographiques.
- L'intégration de plusieurs autorités d'horodatage.
- Le support de différents formats.
- L'ajout d'utilisateurs et d'organisations.
- L'intégration de services externes.

---

# 7. ARCHITECTURE TECHNIQUE

## 7.1. Approche architecturale

L'architecture initiale sera un monolithe modulaire.

Cette approche permettra de limiter la complexité opérationnelle tout en conservant une séparation claire des responsabilités.

Les microservices ne seront envisagés que lorsque les besoins de charge, d'isolation ou de déploiement le justifieront.

## 7.2. Technologies recommandées

| Composant | Technologie |
|---|---|
| Frontend | Next.js / React |
| Backend | Python / FastAPI |
| Base de données | PostgreSQL |
| ORM | SQLAlchemy |
| Cryptographie | Python cryptography |
| Horodatage | RFC 3161 / TSA externe |
| Stockage | S3 compatible |
| Conteneurisation | Docker Compose |
| Tests | Pytest |
| Versionnement | Git / GitHub |
| CI/CD | GitHub Actions |

## 7.3. Architecture logique

L'application sera structurée autour des composants suivants :

**Frontend**
- Interface utilisateur.
- Tableau de bord.
- Formulaire de dépôt.
- Historique des preuves.
- Portail de vérification.

**Backend**
- Module d'authentification.
- Module de gestion des preuves.
- Module cryptographique.
- Module d'horodatage.
- Module de traçabilité.
- Module de génération des rapports.
- Module de vérification.

**Persistance**
- PostgreSQL pour les métadonnées et les événements.
- Stockage objet pour les fichiers originaux.
- Stockage sécurisé des certificats et jetons.

## 7.4. Organisation indicative du code

```text
veritas/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── services/
│   └── public/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── evidence/
│   │   ├── crypto/
│   │   ├── timestamp/
│   │   ├── custody/
│   │   ├── verification/
│   │   ├── reports/
│   │   └── database/
│   │
│   └── tests/
│
├── infrastructure/
│   ├── docker/
│   └── configuration/
│
├── documentation/
│
└── docker-compose.yml
```

---

# 8. MODÈLE DE DONNÉES INITIAL

Les principales entités de la base de données seront :

| Entité | Description |
|---|---|
| User | Informations des utilisateurs |
| Organization | Organisations clientes |
| Evidence | Informations générales sur une preuve |
| EvidenceFile | Fichier et métadonnées |
| HashRecord | Empreinte cryptographique |
| TimestampRecord | Informations d'horodatage |
| CustodyEvent | Événements de traçabilité |
| Verification | Résultats des vérifications |
| AccessLog | Journal des accès |
| Certificate | Informations relatives aux certificats |

Relations principales :

- Un utilisateur peut posséder plusieurs preuves.
- Une organisation peut regrouper plusieurs utilisateurs.
- Une preuve peut comporter plusieurs fichiers.
- Une preuve peut comporter plusieurs événements.
- Une preuve peut avoir plusieurs opérations de vérification.
- Un fichier peut être associé à plusieurs enregistrements cryptographiques au fil de son cycle de vie.

Les identifiants devront être uniques et les relations protégées par des contraintes d'intégrité.

---

# 9. API ET INTÉGRATIONS

L'application devra exposer une API REST documentée.

Endpoints initiaux envisagés :

| Méthode | Endpoint | Fonction |
|---|---|---|
| POST | /api/v1/auth/register | Création de compte |
| POST | /api/v1/auth/login | Connexion |
| POST | /api/v1/evidence | Création d'une preuve |
| GET | /api/v1/evidence | Liste des preuves |
| GET | /api/v1/evidence/{id} | Consultation |
| POST | /api/v1/evidence/{id}/timestamp | Horodatage |
| GET | /api/v1/evidence/{id}/report | Rapport |
| POST | /api/v1/verify | Vérification indépendante |

Les opérations devront respecter les contrôles d'autorisation et les limites de taille.

La documentation sera générée à partir d'OpenAPI via FastAPI.

---

# 10. PRINCIPAUX SCÉNARIOS D'UTILISATION

## Scénario 1 : Certification d'un document

Acteur : utilisateur enregistré.

1. L'utilisateur se connecte.
2. Il sélectionne un fichier PDF.
3. Il lance le dépôt.
4. Le système calcule l'empreinte.
5. Le système obtient l'horodatage.
6. Le dossier de preuve est créé.
7. L'utilisateur télécharge son certificat.

Résultat attendu : un dossier contenant les éléments nécessaires à la vérification de l'intégrité et de l'horodatage.

## Scénario 2 : Vérification d'un document

Acteur : vérificateur externe.

1. Le vérificateur ouvre le portail.
2. Il dépose le document et le dossier associé.
3. Le système recalcule l'empreinte.
4. Il valide le jeton d'horodatage.
5. Il contrôle la cohérence des événements.
6. Il génère un rapport.

Résultat attendu : un rapport présentant les éléments validés et les éventuelles anomalies.

## Scénario 3 : Détection d'une modification

Acteur : utilisateur ou vérificateur.

1. Un document précédemment certifié est modifié.
2. Le nouveau document est soumis à vérification.
3. Le système calcule son empreinte.
4. Le résultat est comparé à l'empreinte originale.
5. Le système détecte la différence.

Résultat attendu : le document est déclaré non conforme à l'empreinte initialement enregistrée.

---

# 11. CONFORMITÉ ET RÉFÉRENTIELS

Le développement devra tenir compte des référentiels suivants :

- RFC 3161 : protocole d'horodatage.
- RFC 5280 : certificats numériques X.509.
- ISO/IEC 27001 : management de la sécurité de l'information.
- ISO/IEC 27037 : identification, collecte, acquisition et préservation des preuves numériques.
- OWASP ASVS : exigences de sécurité des applications.
- WCAG : accessibilité des interfaces.
- Principes de protection des renseignements personnels applicables au Canada, notamment la LPRPDE et les lois québécoises pertinentes.

La conformité à ces référentiels devra faire l'objet d'une évaluation distincte. Leur simple prise en compte dans le développement ne constitue pas une certification.

---

# 12. PLAN DE RÉALISATION

Le projet sera exécuté par phases.

| Phase | Activités | Livrable |
|---|---|---|
| 1 | Analyse et conception | Architecture et modèle de données |
| 2 | Initialisation technique | Application fonctionnelle |
| 3 | Authentification et dépôt | Module de gestion des preuves |
| 4 | Cryptographie | Calcul SHA-256 |
| 5 | Horodatage | Intégration RFC 3161 |
| 6 | Traçabilité | Journal cryptographique |
| 7 | Vérification | Portail indépendant |
| 8 | Tests et sécurité | Version MVP stabilisée |
| 9 | Déploiement pilote | Première version accessible |

Estimation indicative : 6 à 10 semaines à temps plein pour un MVP limité, avec des dépendances externes et des fonctionnalités simplifiées. Une période supplémentaire devra être prévue pour les tests approfondis, la sécurisation et la préparation à une utilisation commerciale.

---

# 13. RISQUES DU PROJET

| Risque | Conséquence | Mesure préventive |
|---|---|---|
| Perte des fichiers | Perte de preuves | Sauvegardes et redondance |
| Compromission du serveur | Altération des données | Contrôles d'accès et audit |
| Défaillance du fournisseur TSA | Absence d'horodatage | Fournisseur alternatif |
| Mauvaise gestion des clés | Perte de confiance | Gestion sécurisée des clés |
| Accès non autorisé | Fuite de documents | MFA et permissions |
| Falsification des événements | Historique contestable | Chaînage cryptographique et ancrage externe |
| Complexité technique | Retard du projet | Développement progressif |
| Mauvaise interprétation juridique | Responsabilité commerciale | Documentation des limites et avis juridique |

---

# 14. MODÈLE ÉCONOMIQUE ENVISAGÉ

VERITAS pourrait adopter un modèle SaaS.

**Offre gratuite**
- Nombre limité de preuves.
- Fonctionnalités essentielles.
- Vérification publique limitée.

**Offre individuelle**
- Volume supérieur de documents.
- Historique étendu.
- Rapports téléchargeables.
- Conservation prolongée.

**Offre professionnelle**
- Gestion des équipes.
- API.
- Gestion avancée des accès.
- Rapports personnalisés.

**Offre entreprise**
- Intégration avec les systèmes internes.
- Gestion multi-organisations.
- Politiques de conservation.
- Support spécialisé.
- Options d'hébergement dédiées.

Les prix seront déterminés après validation du marché et estimation des coûts de stockage, d'horodatage et d'exploitation.

---

# 15. PERSPECTIVES D'ÉVOLUTION

À long terme, VERITAS devra dépasser le simple cadre du dépôt et de la vérification de documents.

Les axes stratégiques envisagés sont :

1. Devenir une infrastructure de certification numérique accessible par API.
2. Permettre la vérification de preuves entre différentes organisations.
3. Développer un mécanisme de certification de lots de données.
4. Étendre la plateforme aux preuves issues des objets connectés.
5. Intégrer des mécanismes d'analyse des métadonnées.
6. Proposer des outils spécialisés pour les investigations numériques.
7. Développer une infrastructure de vérification indépendante et interopérable.

---

# 16. CRITÈRES D'ACCEPTATION DU MVP

Le MVP devra réussir les tests suivants :

| ID | Test | Résultat attendu |
|---|---|---|
| T01 | Déposer un PDF valide | Dépôt réussi |
| T02 | Calculer SHA-256 | Empreinte enregistrée |
| T03 | Modifier un octet du fichier | Modification détectée |
| T04 | Obtenir un horodatage | Jeton RFC 3161 reçu |
| T05 | Vérifier le jeton | Signature et chaîne validées |
| T06 | Consulter l'historique | Événements affichés |
| T07 | Modifier un événement | Incohérence détectée |
| T08 | Exporter le dossier | Dossier complet généré |
| T09 | Vérifier sans compte | Vérification possible |
| T10 | Accéder à une preuve d'un autre utilisateur | Accès refusé |

---

# 17. DÉCISIONS STRATÉGIQUES FONDAMENTALES

Les principes suivants devront guider toutes les décisions de développement :

**Principe 1 : La preuve avant l'intelligence artificielle.**

La priorité est la fiabilité cryptographique. L'IA sera une extension et non le fondement du système.

**Principe 2 : La vérification indépendante.**

Un utilisateur ne doit pas être obligé de faire confiance uniquement à VERITAS pour vérifier une preuve produite par VERITAS.

**Principe 3 : La simplicité architecturale.**

L'architecture doit rester adaptée aux ressources humaines et financières initiales.

**Principe 4 : La sécurité dès la conception.**

La sécurité ne sera pas une fonctionnalité ajoutée à la fin du développement.

**Principe 5 : L'interopérabilité.**

Les dossiers de preuve doivent pouvoir être exploités par des outils externes selon des formats documentés.

**Principe 6 : La transparence des limites.**

VERITAS certifie des propriétés techniques vérifiables. Il ne garantit pas automatiquement la véracité du contenu, l'identité de son auteur ou son admissibilité juridique.

---

# 18. CONCLUSION

VERITAS est conçu comme un projet d'infrastructure de confiance numérique.

Son ambition est de rendre la certification et la vérification de l'intégrité des données accessibles à différents types d'utilisateurs, sans imposer une dépendance exclusive envers un fournisseur central.

Le projet sera construit progressivement, en privilégiant la qualité cryptographique, la sécurité, la traçabilité et l'interopérabilité.

La première version devra démontrer une capacité fondamentale : **permettre à une personne de produire une preuve numérique dont l'intégrité et l'horodatage peuvent être vérifiés indépendamment.**

Cette capacité constituera le socle technologique sur lequel pourront être développées les futures fonctionnalités de la plateforme.

**VERITAS — Trust through verifiable evidence.**

*La confiance par la preuve vérifiable.*

### Mon avis d'architecte : trois éléments à ne pas négliger

Avant de commencer le développement, je voudrais attirer ton attention sur trois décisions structurantes :

* Ne pas confondre intégrité et authenticité. SHA-256 permet de détecter une modification, mais ne démontre pas à lui seul qui a créé le fichier.

* Ne pas confondre horodatage et date de création. Un jeton RFC 3161 établit qu'une empreinte existait au moment attesté par la TSA, pas nécessairement que le document a été créé à ce moment.

* Ne pas confondre journal chaîné et stockage immuable. Nous devrons concevoir plusieurs mécanismes complémentaires pour empêcher la manipulation de l'historique.

La prochaine étape logique sera de transformer ce cahier des charges en dossier de conception technique (Technical Design Document), avec les diagrammes UML, le schéma PostgreSQL, les API détaillées et les flux de traitement. C'est ce document qui nous permettra ensuite de commencer à programmer méthodiquement, sans improviser l'architecture.
