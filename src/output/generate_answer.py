from config.settings import Settings
from llm.client import LLMClient


def generate_answer(question: str, context: dict, settings: Settings) -> str:
    del settings

    topics_summary = context.get("topics_summary", "Тем пока нет.")
    excerpts = context.get("excerpts", [])
    context_block = "\n".join(excerpts) if excerpts else "Подходящих постов за последние 7 дней не найдено."
    prompt = (
        f"Question:\n{question}\n\n"
        f"Topics:\n{topics_summary}\n\n"
        f"Relevant Telegram excerpts from the last 7 days:\n{context_block}"
    )
    system = (
        "You are a research assistant. Answer based only on the provided Telegram channel data context. "
        "Be concise (max 300 words). Answer in the same language as the question."
    )
    response_text = LLMClient.complete(prompt=prompt, system=system, max_tokens=600, category="bot_ask").strip()
    if not response_text:
        return "Не нашёл достаточно данных, чтобы ответить по последним постам."
    return response_text
