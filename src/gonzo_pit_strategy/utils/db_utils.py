
import os
from typing import Optional

def get_db_url(
    host: str = "localhost",
    port: int = 5432,
    dbname: str = "f1db",
    user: str = "postgres",
    password: Optional[str] = None
) -> str:
    """Get SQLAlchemy/Goose compatible connection string."""
    if not password:
        password = os.environ.get("PGPASSWORD", "")
        
    return f"postgres://{user}:{password}@{host}:{port}/{dbname}?sslmode=disable"
