from typing import Any

from langchain.agents import create_agent
from langgraph_supervisor import create_supervisor

from core import get_model, settings

model = get_model(settings.DEFAULT_MODEL)


def add(a: float, b: float) -> float:
    """两个数相加。"""
    return a + b


def multiply(a: float, b: float) -> float:
    """两个数相乘。"""
    return a * b


def web_search(query: str) -> str:
    """在网络上搜索信息。"""
    return (
        "Here are the headcounts for each of the FAANG companies in 2024:\n"
        "1. **Facebook (Meta)**: 67,317 employees.\n"
        "2. **Apple**: 164,000 employees.\n"
        "3. **Amazon**: 1,551,000 employees.\n"
        "4. **Netflix**: 14,000 employees.\n"
        "5. **Google (Alphabet)**: 181,269 employees."
    )


math_agent: Any = create_agent(
    model=model,
    tools=[add, multiply],
    name="sub-agent-math_expert",
    system_prompt="You are a math expert. Always use one tool at a time.",
).with_config(tags=["skip_stream"])

research_agent: Any = create_agent(
    model=model,
    tools=[web_search],
    name="sub-agent-research_expert",
    system_prompt="You are a world class researcher with access to web search. Do not do any math.",
).with_config(tags=["skip_stream"])


# 创建主管工作流
workflow = create_supervisor(
    [research_agent, math_agent],
    model=model,
    prompt=(
        "You are a team supervisor managing a research expert and a math expert. "
        "For current events, use research_agent. "
        "For math problems, use math_agent."
    ),
    add_handoff_back_messages=True,
    # UI 现在要求此项为 True，这样我们就不必猜测何时发生交回 (handoff back)
    output_mode="full_history",  # 否则在重新加载对话时，子智能体的消息将不被包含
)

langgraph_supervisor_agent = workflow.compile()
