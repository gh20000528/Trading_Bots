from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    bingx_api_key:    str = "3tyg8ErUggyYxCWBy5uNPHyMJsVmPUgnLRQWP9pIWqQCE84ccYEsyWy8gtLaDjRF3E71Uo8Ww6ACD7oAVA"
    bingx_secret:     str = "xJnoiXJwxbBT1sL124hyVhLNgSWeuZZ5Pe7UMmg5fKDpld89SQmeK5S93KDBVXlbhkxeAeDUDK7bfbbBESQWw"
    database_url:     str = "postgresql+asyncpg://xuhansheng@localhost:5432/xuhansheng"
    telegram_token:   str = ""
    telegram_chat_id: str = ""
    # Optional: Coinalyze free API key (https://coinalyze.net)
    coinalyze_api_key: str = ""
    # Optional: CoinGlass API key (https://coinglass.com/pricing)
    coinglass_api_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
