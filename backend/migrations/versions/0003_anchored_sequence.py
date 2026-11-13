"""Ancrage de la tête de chaîne : numéro de séquence ancré

Un horodatage CHAIN_HEAD atteste l'empreinte de la tête de la chaîne de possession à un
moment donné. Pour qu'un tiers sache jusqu'où la chaîne est garantie, l'ancrage
enregistre le numéro de séquence de l'événement dont l'empreinte a été horodatée.

- anchored_sequence_number : rempli pour un ancrage (CHAIN_HEAD), vide pour
  l'horodatage d'un fichier (FILE) ;
- aucune ligne existante n'est concernée : seuls des horodatages FILE existent.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_SQL = r"""
ALTER TABLE timestamp_records
    ADD COLUMN anchored_sequence_number BIGINT
        CONSTRAINT timestamp_records_anchored_sequence_number_check
        CHECK (anchored_sequence_number >= 1);

ALTER TABLE timestamp_records
    ADD CONSTRAINT timestamp_records_anchor_check
        CHECK ((purpose = 'CHAIN_HEAD') = (anchored_sequence_number IS NOT NULL));
"""

DOWNGRADE_SQL = r"""
ALTER TABLE timestamp_records DROP CONSTRAINT timestamp_records_anchor_check;
ALTER TABLE timestamp_records DROP COLUMN anchored_sequence_number;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
