from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# No migration framework is used for this local/offline demo DB -- schema
# additions to existing tables are applied here as idempotent ALTERs so an
# existing sqlite file keeps working after a model change.
_LIGHT_MIGRATIONS = [
    ("cameras", "active", "ALTER TABLE cameras ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1"),
    ("incidents", "disposition", "ALTER TABLE incidents ADD COLUMN disposition VARCHAR"),
]


def run_light_migrations():
    with engine.connect() as conn:
        for table, column, ddl in _LIGHT_MIGRATIONS:
            existing_cols = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")]
            if column not in existing_cols:
                conn.exec_driver_sql(ddl)
                conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
