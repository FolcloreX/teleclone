from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from pydantic import Field, computed_field

from typing import Optional, Literal
from pathlib import Path
import logging


def setup_logging():
    log_file = settings.log_dir / 'cloner.log'
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(levelname)s - %(asctime)s - [%(name)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, mode='w'),
            logging.StreamHandler(),
        ],
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    project_root: Path = Field(
        default=Path(__file__).resolve().parents[1],
        description='Path to the root of the project',
    )

    account_name: str
    phone_number: str
    api_id: int
    api_hash: str
    password: Optional[str]
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'] = Field(
        default='INFO', description='Nível de detalhe dos logs.'
    )

    @computed_field
    def log_dir(self) -> Path:
        path = self.project_root / 'logs'
        path.mkdir(parents=True, exist_ok=True)
        return path

    @computed_field
    def download_dir(self) -> Path:
        path = self.project_root / 'download'
        path.mkdir(parents=True, exist_ok=True)
        return path

    @computed_field
    def database_path(self) -> Path:
        return self.project_root / 'track.db'

    @computed_field
    def profiles_dir(self) -> Path:
        path = self.project_root / 'profiles'
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
