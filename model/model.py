from langchain.chat_models import init_chat_model
from nemoguardrails import RailsConfig
from nemoguardrails.integrations.langchain.runnable_rails import RunnableRails

model = init_chat_model("gpt-4o-mini", model_provider="openai")
config = RailsConfig.from_path("./config")

guard_rails = RunnableRails(config)
