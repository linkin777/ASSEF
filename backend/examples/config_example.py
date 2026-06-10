"""演示配置文件使用方式：加载 config.default.json、创建 LLM 客户端、获取默认配置。"""

from assef.models.config import load_config, build_target_spec_from_config, Config, LLMBackendConfig
from assef.llm import LLMClient

config = load_config("config.default.json")
print(f"Loaded {len(config.llm_backends)} LLM backends")
print(f"Game rules: max {config.game_rules.max_arena_rounds} rounds")

for backend_cfg in config.llm_backends:
    client = LLMClient.from_config(backend_cfg)
    print(f"Backend: {client._backend}, Model: {client._model}")

default_config = Config()
print(f"Default config has {len(default_config.llm_backends)} backends")

print("Config example completed successfully!")
