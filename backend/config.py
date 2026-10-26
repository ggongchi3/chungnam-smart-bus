from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    database_url: str = 'sqlite:///' + (ROOT / '.local' / 'bus.sqlite3').as_posix()
    data_mode: str = 'demo'
    demo_scenario: str = 'normal'
    cors_origins: tuple[str, ...] = ('http://localhost:5173', 'http://127.0.0.1:5173')

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.getenv('BUS_DATABASE_URL', cls.database_url),
            data_mode=os.getenv('BUS_DATA_MODE', 'demo'),
            demo_scenario=os.getenv('BUS_DEMO_SCENARIO', 'normal'),
            cors_origins=tuple(os.getenv('BUS_CORS_ORIGINS', ','.join(cls.cors_origins)).split(',')),
        )
