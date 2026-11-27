"""Configuration centralisée, sans valeurs secrètes codées en dur."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_env: str
    projects_dir: Path
    output_dir: Path
    log_level: str
    video_provider: str
    agnes_api_key: str | None

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        provider = os.getenv("VIDEO_PROVIDER", "disabled").strip().lower()
        if provider not in {"disabled", "agnes"}:
            raise ValueError(
                "VIDEO_PROVIDER doit être 'disabled' ou 'agnes'."
            )
        key = os.getenv("AGNES_API_KEY", "").strip() or None
        if provider == "agnes" and not key:
            raise ValueError(
                "AGNES_API_KEY est obligatoire lorsque VIDEO_PROVIDER=agnes."
            )
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            projects_dir=Path(os.getenv("PROJECTS_DIR", "projects")),
            output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            video_provider=provider,
            agnes_api_key=key,
        )
