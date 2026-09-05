from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# `create_all()` does not add columns to an existing table. Keep this migration
# deliberately small and idempotent so installations that already have the
# prototype SQLite database gain the trust fields without losing any rows.
_TENDER_TRUST_COLUMNS = {
    "bid_start_date": "VARCHAR(50)",
    "bid_deadline_at": "VARCHAR(50)",
    "bid_notice_status": "VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN'",
    "bid_evidence_url": "VARCHAR(2000)",
    "bid_evidence_hash": "VARCHAR(64)",
    "bid_evidence_excerpt": "TEXT",
    "bidding_checked_at": "DATETIME",
    "data_origin": "VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN'",
    "verification_status": "VARCHAR(32) NOT NULL DEFAULT 'PENDING'",
    "verification_method": "VARCHAR(100)",
    "confidence_score": "FLOAT",
    "is_official_source": "BOOLEAN NOT NULL DEFAULT FALSE",
    "source_record_id": "VARCHAR(255)",
    "evidence_hash": "VARCHAR(128)",
    "raw_payload_json": "TEXT",
    "first_seen_at": "DATETIME",
    "last_seen_at": "DATETIME",
    "last_verified_at": "DATETIME",
    "is_demo": "BOOLEAN NOT NULL DEFAULT FALSE",
    "is_quarantined": "BOOLEAN NOT NULL DEFAULT FALSE",
    "quarantine_reason": "TEXT",
}

# Codes that only ever existed in the discarded prototype catalogue. They are
# matched by code as well as by the trust flags so a database written before the
# flags existed is still cleaned.
_LEGACY_DEMO_CODES = (
    "AOT-67-11204",
    "BBL-67-PT08",
    "BDMS-67-MED01",
    "BOT-67-08912",
    "CPN-67-PAM03",
    "EGAT-67-03319",
    "GHB-67-08129",
    "GSB-67-HSM01",
    "KBANK-67-CY01",
    "KTB-67-MDR02",
    "MOPH-67-09881",
    "MTL-67-CLD02",
    "NCSA-67-00122",
    "NCSA-67-00188",
    "NHSO-67-00933",
    "NT-67-01994",
    "PTT-67-OT05",
    "PWA-67-04190",
    "RD-67-05520",
    "SCB-67-SW03",
    "SCG-67-GSOC01",
    "SEC-67-00451",
    "TRUE-67-5G09",
    "TTB-67-ZT04",
)

# Supplier-portal URLs the prototype guessed at. None of them is a published
# procurement feed, so the rows are removed rather than left looking like
# sources a user could switch back on.
_FICTIONAL_SOURCE_URLS = (
    "https://www.kasikornbank.com/th/supplier",
    "https://www.scb.co.th/th/about-us/procurement.html",
    "https://www.bangkokbank.com/th-th/about-us/procurement",
    "https://procurement.pttplc.com",
    "https://www.scg.com/th/supplier",
    "https://www.true.th/procurement",
)


def run_database_migrations() -> None:
    """Add trust columns, then delete every fabricated row left by the prototype."""
    table_names = set(inspect(engine).get_table_names())
    if "tenders" not in table_names:
        return

    existing_columns = {column["name"] for column in inspect(engine).get_columns("tenders")}
    with engine.begin() as connection:
        for name, definition in _TENDER_TRUST_COLUMNS.items():
            if name not in existing_columns:
                connection.execute(text(f'ALTER TABLE tenders ADD COLUMN "{name}" {definition}'))

        # Indexes matter because every public tender query applies the
        # quarantine predicate.
        for index_sql in (
            "CREATE INDEX IF NOT EXISTS ix_tenders_data_origin ON tenders (data_origin)",
            "CREATE INDEX IF NOT EXISTS ix_tenders_verification_status ON tenders (verification_status)",
            "CREATE INDEX IF NOT EXISTS ix_tenders_source_record_id ON tenders (source_record_id)",
            "CREATE INDEX IF NOT EXISTS ix_tenders_is_demo ON tenders (is_demo)",
            "CREATE INDEX IF NOT EXISTS ix_tenders_is_quarantined ON tenders (is_quarantined)",
            "CREATE INDEX IF NOT EXISTS ix_tenders_bid_deadline_at ON tenders (bid_deadline_at)",
        ):
            connection.execute(text(index_sql))

        code_params = {
            f"demo_code_{index}": code for index, code in enumerate(_LEGACY_DEMO_CODES)
        }
        placeholders = ", ".join(f":{name}" for name in code_params)
        # A demo row is any row flagged as demo, any row still carrying a
        # prototype code, or any prototype row whose only "TOR" was a link the
        # old code generated for itself.
        demo_predicate = f"""
            is_demo = 1
            OR data_origin = 'DEMO'
            OR verification_status = 'DEMO'
            OR tender_code IN ({placeholders})
            OR (tender_code LIKE 'NEW-%' AND tor_url LIKE '%/tor/NEW-%')
        """

        if "tender_provenance" in table_names:
            connection.execute(
                text(
                    "DELETE FROM tender_provenance WHERE source_type = 'DEMO' "
                    f"OR tender_id IN (SELECT id FROM tenders WHERE {demo_predicate})"
                ),
                code_params,
            )
        if "notification_logs" in table_names:
            connection.execute(
                text(
                    "DELETE FROM notification_logs WHERE tender_id IN "
                    f"(SELECT id FROM tenders WHERE {demo_predicate})"
                ),
                code_params,
            )
        connection.execute(text(f"DELETE FROM tenders WHERE {demo_predicate}"), code_params)

        if "scraper_sources" in table_names:
            url_params = {
                f"fake_url_{index}": url
                for index, url in enumerate(_FICTIONAL_SOURCE_URLS)
            }
            url_placeholders = ", ".join(f":{name}" for name in url_params)
            connection.execute(
                text(f"DELETE FROM scraper_sources WHERE url IN ({url_placeholders})"),
                url_params,
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
