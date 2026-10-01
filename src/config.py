"""
全局配置：从环境变量 / .env 文件读取，集中管理所有可调参数。

设计要点（面试可讲）：
- 用 pydantic-settings 统一收口配置，避免散落各处的 os.getenv；
- 所有外部依赖（LLM、数仓、向量库）都通过 provider 字段做"可插拔"切换，
  这是技术方案里"技术选型与版本锁定"思想的落地：接口稳定、实现可换。
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: str = "mock"          # mock | openai_compatible
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_api_key: str = ""

    # 数仓
    warehouse_url: str = "sqlite:///data/warehouse.db"

    # 向量库
    vector_store: str = "builtin"       # builtin | milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # Agent 行为
    sql_max_retry: int = 2
    sql_result_limit: int = 200

    @property
    def sqlite_path(self) -> str:
        """从 sqlite:///xxx 中解析出文件路径。"""
        if self.warehouse_url.startswith("sqlite:///"):
            return self.warehouse_url.replace("sqlite:///", "", 1)
        raise ValueError("当前 demo 仅内置 SQLite 执行器，生产请扩展 sandbox 的 executor")


@lru_cache
def get_settings() -> Settings:
    return Settings()
