import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

class Settings(BaseModel):
    token: str = Field(default_factory=lambda: os.getenv("DISCORD_TOKEN",""))
    guild_id: int = int(os.getenv("GUILD_ID","0"))
    data_backend: str = os.getenv("DATA_BACKEND","json")
    data_dir: str = os.getenv("DATA_DIR","./data")
    sync_scope: str = os.getenv("SYNC_SCOPE", "both")

settings = Settings()
