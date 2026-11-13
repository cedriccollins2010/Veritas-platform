"""Bibliothèque de vérification VERITAS (Apache 2.0).

Code cryptographique pur, partagé par le serveur VERITAS et le vérificateur autonome :
empreintes SHA-256, canonicalisation RFC 8785, chaîne de possession veritas-custody-v1,
empreinte du manifeste et vérification des jetons RFC 3161.

Ce paquet ne dépend jamais du serveur : ni base de données, ni réseau, ni framework web.
Un tiers peut l'installer seul pour refaire chaque contrôle.
"""

__version__ = "0.1.0"
