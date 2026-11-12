"""Schéma initial VERITAS

Reprend le script SQL du blueprint (section 3.2) avec les corrections du document de
référence unifié :
- evidence.organization_id obligatoire (isolation par organisation) ;
- table sessions pour l'authentification par cookie ;
- mode « empreinte seule » (fichier non conservé, empreinte calculée côté client) ;
- UNIQUE (file_id, algorithm) sur hash_records, version du moteur et origine du calcul ;
- timestamp_records : requête, policy OID, numéro de série, nonce, objet horodaté ;
- custody_events : date incluse dans l'empreinte, journal append-only imposé par la base ;
- contraintes CHECK sur toutes les valeurs énumérées ;
- aucune suppression en cascade.

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_SQL = r"""
-- gen_random_uuid() est intégré à PostgreSQL depuis la version 13.

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    email_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Unicité insensible à la casse : Alice@x.ca et alice@x.ca sont le même compte.
CREATE UNIQUE INDEX uq_users_email_lower ON users (LOWER(email));

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    -- Organisation créée automatiquement à l'inscription pour un utilisateur seul.
    is_personal BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE organization_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id UUID NOT NULL REFERENCES users(id),
    role VARCHAR(30) NOT NULL
        CHECK (role IN ('OWNER', 'ADMIN', 'MEMBER', 'VIEWER')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, user_id)
);
CREATE INDEX idx_org_members_user ON organization_members (user_id);

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    -- Seule l'empreinte du jeton de session est stockée, jamais le jeton lui-même.
    token_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    ip_address INET,
    user_agent VARCHAR(512),
    CHECK (expires_at > created_at)
);
CREATE INDEX idx_sessions_user ON sessions (user_id);

CREATE TABLE evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    owner_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'RECEIVED'
        CHECK (status IN ('RECEIVED', 'PROCESSING', 'HASHED', 'TIMESTAMP_PENDING',
                          'CERTIFIED', 'FAILED', 'ARCHIVED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    certified_at TIMESTAMPTZ,
    CHECK ((status = 'CERTIFIED') <= (certified_at IS NOT NULL))
);
CREATE INDEX idx_evidence_organization ON evidence (organization_id, created_at DESC);
CREATE INDEX idx_evidence_owner ON evidence (owner_id);
CREATE INDEX idx_evidence_status ON evidence (status);

CREATE TABLE evidence_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID NOT NULL REFERENCES evidence(id),
    original_filename VARCHAR(255) NOT NULL,
    -- STORED : l'original est conservé dans le stockage objet.
    -- HASH_ONLY : seule l'empreinte, calculée en local par l'analyste, est enregistrée.
    storage_mode VARCHAR(20) NOT NULL DEFAULT 'STORED'
        CHECK (storage_mode IN ('STORED', 'HASH_ONLY')),
    storage_key VARCHAR(512) UNIQUE,
    media_type VARCHAR(255) NOT NULL DEFAULT 'application/octet-stream',
    file_size BIGINT NOT NULL CHECK (file_size >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((storage_mode = 'STORED') = (storage_key IS NOT NULL))
);
CREATE INDEX idx_evidence_files_evidence ON evidence_files (evidence_id);

CREATE TABLE hash_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id UUID NOT NULL REFERENCES evidence_files(id),
    algorithm VARCHAR(30) NOT NULL CHECK (algorithm IN ('SHA-256')),
    digest VARCHAR(128) NOT NULL CHECK (digest ~ '^[0-9a-f]+$'),
    encoding VARCHAR(10) NOT NULL DEFAULT 'hex' CHECK (encoding = 'hex'),
    engine_version VARCHAR(20) NOT NULL,
    -- SERVER : calculée par VERITAS sur le fichier reçu. CLIENT : mode empreinte seule.
    source VARCHAR(10) NOT NULL CHECK (source IN ('SERVER', 'CLIENT')),
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (file_id, algorithm)
);
CREATE INDEX idx_hash_digest ON hash_records (digest);

CREATE TABLE timestamp_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID NOT NULL REFERENCES evidence(id),
    -- FILE : horodatage de l'empreinte d'un fichier.
    -- CHAIN_HEAD : horodatage de la tête de la chaîne de possession (ancrage).
    purpose VARCHAR(20) NOT NULL CHECK (purpose IN ('FILE', 'CHAIN_HEAD')),
    hash_record_id UUID REFERENCES hash_records(id),
    hash_algorithm VARCHAR(30) NOT NULL CHECK (hash_algorithm IN ('SHA-256')),
    message_imprint VARCHAR(128) NOT NULL CHECK (message_imprint ~ '^[0-9a-f]+$'),
    tsa_name VARCHAR(255) NOT NULL,
    tsa_url VARCHAR(512) NOT NULL,
    nonce NUMERIC(40, 0),
    request_storage_key VARCHAR(512),
    token_storage_key VARCHAR(512),
    policy_oid VARCHAR(255),
    serial_number VARCHAR(128),
    generation_time TIMESTAMPTZ,
    validation_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (validation_status IN ('PENDING', 'VALID', 'INVALID', 'ERROR')),
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated_at TIMESTAMPTZ,
    CHECK ((purpose = 'FILE') = (hash_record_id IS NOT NULL)),
    -- Un jeton déclaré valide doit exister et porter son heure de génération.
    CHECK (validation_status <> 'VALID'
           OR (token_storage_key IS NOT NULL AND generation_time IS NOT NULL))
);
CREATE INDEX idx_timestamp_evidence ON timestamp_records (evidence_id);
CREATE INDEX idx_timestamp_pending ON timestamp_records (validation_status)
    WHERE validation_status = 'PENDING';

CREATE TABLE custody_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID NOT NULL REFERENCES evidence(id),
    actor_id UUID REFERENCES users(id),
    event_type VARCHAR(80) NOT NULL,
    sequence_number BIGINT NOT NULL CHECK (sequence_number >= 1),
    -- Date incluse dans l'empreinte de l'événement (fixée par l'application, en UTC).
    occurred_at TIMESTAMPTZ NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}',
    canonicalization VARCHAR(30) NOT NULL DEFAULT 'JCS-RFC8785',
    previous_event_hash CHAR(64) CHECK (previous_event_hash ~ '^[0-9a-f]{64}$'),
    event_hash CHAR(64) NOT NULL CHECK (event_hash ~ '^[0-9a-f]{64}$'),
    -- Date d'écriture en base : informative, non incluse dans l'empreinte.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (evidence_id, sequence_number),
    CHECK ((sequence_number = 1) = (previous_event_hash IS NULL))
);

-- Journal append-only : toute modification ou suppression est refusée par la base,
-- même si le code applicatif contient une erreur.
CREATE FUNCTION custody_events_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'custody_events est append-only : % refusé', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_custody_events_no_update_delete
    BEFORE UPDATE OR DELETE ON custody_events
    FOR EACH ROW EXECUTE FUNCTION custody_events_append_only();

CREATE TRIGGER trg_custody_events_no_truncate
    BEFORE TRUNCATE ON custody_events
    FOR EACH STATEMENT EXECUTE FUNCTION custody_events_append_only();

CREATE TABLE verification_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Nul quand le dossier vérifié ne provient pas de cette instance de VERITAS.
    evidence_id UUID REFERENCES evidence(id),
    verifier_id UUID REFERENCES users(id),
    manifest_digest CHAR(64),
    verifier_version VARCHAR(20) NOT NULL,
    manifest_status VARCHAR(10) NOT NULL CHECK (manifest_status IN ('PASS', 'FAIL')),
    integrity_status VARCHAR(10) NOT NULL CHECK (integrity_status IN ('PASS', 'FAIL')),
    timestamp_status VARCHAR(10) NOT NULL
        CHECK (timestamp_status IN ('PASS', 'FAIL', 'UNKNOWN')),
    certificate_status VARCHAR(10) NOT NULL
        CHECK (certificate_status IN ('PASS', 'FAIL', 'UNKNOWN')),
    custody_status VARCHAR(10) NOT NULL CHECK (custody_status IN ('PASS', 'FAIL')),
    completeness VARCHAR(12) NOT NULL CHECK (completeness IN ('COMPLETE', 'INCOMPLETE')),
    overall_status VARCHAR(15) NOT NULL
        CHECK (overall_status IN ('VALID', 'INVALID', 'INCONCLUSIVE')),
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- VALID seulement si tous les contrôles obligatoires sont PASS.
    CHECK (overall_status <> 'VALID' OR (
        manifest_status = 'PASS' AND integrity_status = 'PASS'
        AND timestamp_status = 'PASS' AND certificate_status = 'PASS'
        AND custody_status = 'PASS' AND completeness = 'COMPLETE'))
);
CREATE INDEX idx_verification_evidence ON verification_records (evidence_id);

CREATE TABLE access_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    outcome VARCHAR(10) NOT NULL CHECK (outcome IN ('SUCCESS', 'DENIED', 'ERROR')),
    ip_address INET,
    user_agent VARCHAR(512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_access_logs_org_time ON access_logs (organization_id, created_at DESC);
CREATE INDEX idx_access_logs_user_time ON access_logs (user_id, created_at DESC);
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS access_logs;
DROP TABLE IF EXISTS verification_records;
DROP TRIGGER IF EXISTS trg_custody_events_no_truncate ON custody_events;
DROP TRIGGER IF EXISTS trg_custody_events_no_update_delete ON custody_events;
DROP TABLE IF EXISTS custody_events;
DROP FUNCTION IF EXISTS custody_events_append_only();
DROP TABLE IF EXISTS timestamp_records;
DROP TABLE IF EXISTS hash_records;
DROP TABLE IF EXISTS evidence_files;
DROP TABLE IF EXISTS evidence;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS organization_members;
DROP TABLE IF EXISTS organizations;
DROP TABLE IF EXISTS users;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    # Destructif : ne jamais exécuter en production sans sauvegarde vérifiée.
    op.execute(DOWNGRADE_SQL)
