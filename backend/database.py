from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import ROOT
from backend.models.tables import Base


class Database:
    def __init__(self, url):
        parsed = make_url(url)
        if parsed.drivername != 'sqlite':
            raise ValueError('This prototype supports SQLite only')
        memory = parsed.database in (None, '', ':memory:')
        if not memory:
            db_path = Path(parsed.database).resolve()
            if not db_path.is_relative_to((ROOT / '.local').resolve()):
                raise ValueError('File databases must stay inside backend/.local/')
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 3},
                                    **({'poolclass': StaticPool} if memory else {}))

        @event.listens_for(self.engine, 'connect')
        def enable_foreign_keys(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self):
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self):
        with self.sessions() as session:
            with session.begin():
                yield session
