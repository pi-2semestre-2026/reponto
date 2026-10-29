"""Postgres transactional notifications for the authenticated checkout stream."""

CHANNEL = "reponto_changes"

NOTIFY_FUNCTION = """
CREATE OR REPLACE FUNCTION reponto_notify_change() RETURNS trigger AS $$
DECLARE
    row_data jsonb;
    owner uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN row_data := to_jsonb(OLD);
    ELSE row_data := to_jsonb(NEW);
    END IF;
    IF TG_TABLE_NAME = 'markets' THEN
        owner := (row_data->>'owner_id')::uuid;
    ELSE
        SELECT owner_id INTO owner FROM markets WHERE id = (row_data->>'market_id')::uuid;
    END IF;
    IF owner IS NOT NULL THEN
        PERFORM pg_notify('reponto_changes', owner::text);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


async def install_triggers(conn):
    from sqlalchemy import text

    await conn.execute(text(NOTIFY_FUNCTION))
    for table in ("markets", "products", "sales"):
        await conn.execute(text(f"""
            CREATE OR REPLACE TRIGGER reponto_change
            AFTER INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reponto_notify_change()
        """))
