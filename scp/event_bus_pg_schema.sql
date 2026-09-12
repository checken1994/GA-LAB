-- SCP event bus — canonical PostgreSQL schema (ADOPT-AND-FIX Track C2)
--
-- Design contract (ADOPT-AND-FIX-PLAN Track C2, V2 "borrow the platform"):
--   The durable scp_events TABLE is the source of truth. PostgreSQL
--   LISTEN/NOTIFY is ONLY a wake-up bell. A NOTIFY that is never heard
--   (listener down at publish time, restart, network blip) loses nothing:
--   the row is already committed in the table and is recovered by
--   PgEventBus.replay_undelivered() or by a fresh subscriber's cursor poll.
--   Nobody may read this file as "NOTIFY is a queue".
--
-- This table is PG-native and INDEPENDENT of the TaskKernel journal
-- (scp/kernel_storage_pg_schema.sql `events`): the kernel journal stays the
-- task-lifecycle source of truth; scp_events is the inter-container pub-sub
-- transport. TaskKernel is NOT wired to it in Track C2 (known gap).
--
-- Parameterized access only: PgEventBus never interpolates values into SQL.

CREATE TABLE IF NOT EXISTS scp_events (
    id BIGSERIAL PRIMARY KEY,
    channel TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    correlation_id TEXT,
    -- bounded poison-message guard: handler failures increment attempts;
    -- at max_attempts the row is marked dead=TRUE (logged CRITICAL) so a
    -- poison payload can never block the channel cursor forever.
    attempts BIGINT NOT NULL DEFAULT 0,
    dead BOOLEAN NOT NULL DEFAULT FALSE
);

-- Cursor poll order + channel scoping (required by Track C2 spec).
CREATE INDEX IF NOT EXISTS idx_scp_events_channel_id ON scp_events(channel, id);

-- replay_undelivered() hot path: undelivered rows per channel.
CREATE INDEX IF NOT EXISTS idx_scp_events_undelivered
    ON scp_events(channel, id) WHERE delivered_at IS NULL;
