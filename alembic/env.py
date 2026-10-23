from alembic import context
from sqlalchemy import create_engine

from freerise.config import get_settings
from freerise.models import Base

config = context.config
url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
# ponytail: -x url=... override supported too
url = context.get_x_argument(as_dictionary=True).get("url", url)

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
