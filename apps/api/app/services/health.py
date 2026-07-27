from sqlalchemy import text
from sqlalchemy.orm import Session


def database_is_available(session: Session) -> bool:
    try:
        session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
