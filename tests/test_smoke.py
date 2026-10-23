from sqlalchemy import text


def test_db_connects(session):
    assert session.execute(text("SELECT 1")).scalar() == 1
