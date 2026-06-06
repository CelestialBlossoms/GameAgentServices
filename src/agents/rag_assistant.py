from datetime import datetime
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import (
    RunnableConfig,
    RunnableLambda,
    RunnableSerializable,
)
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import ToolNode

from agents.safeguard import Safeguard, SafeguardOutput, SafetyAssessment
from agents.tools import database_search
from core import get_model, settings


class AgentState(MessagesState, total=False):
    """`total=False` 符合 PEP589 规范。

    文档：https://typing.readthedocs.io/en/latest/spec/typeddict.html#totality
    """

    safety: SafeguardOutput
    remaining_steps: RemainingSteps


tools = [database_search]


current_date = datetime.now().strftime("%B %d, %Y")
instructions = f"""
    You are a game AI Agent service assistant designed to answer questions based on game knowledge,
    activity rules, FAQ, task text, item descriptions, and operational documents.
    Answer in Chinese by default.
    Today's date is {current_date}.

    NOTE: THE USER CAN'T SEE THE TOOL RESPONSE.

    A few things to remember:
    - Use database_search when the question needs game rules, activity details, FAQ, task text, item
      descriptions, or operational knowledge. Search at most twice for one user request, then summarize
      the best available information.
    - After receiving tool results, produce a final answer for the user. Do not keep searching just to
      improve wording or gather marginally more evidence.
    - If the database does not contain enough information, explain what is missing and provide practical
      next steps or a draft answer based on the user's supplied context.
    - Please include markdown-formatted links to any citations used in your response. Only include one
    or two citations per response unless more are needed. ONLY USE LINKS RETURNED BY THE TOOLS.
    - Do not invent exact game rules, reward numbers, dates, or configuration values that are not present
      in the database or user input.
    """


def wrap_model(model: BaseChatModel) -> RunnableSerializable[AgentState, AIMessage]:
    bound_model = model.bind_tools(tools)
    preprocessor = RunnableLambda(
        lambda state: [SystemMessage(content=instructions)] + state["messages"],
        name="StateModifier",
    )
    return preprocessor | bound_model  # type: ignore[return-value]


def format_safety_message(safety: SafeguardOutput) -> AIMessage:
    content = (
        f"This conversation was flagged for unsafe content: {', '.join(safety.unsafe_categories)}"
    )
    return AIMessage(content=content)


async def acall_model(state: AgentState, config: RunnableConfig) -> AgentState:
    m = get_model(config["configurable"].get("model", settings.DEFAULT_MODEL))
    model_runnable = wrap_model(m)
    response = await model_runnable.ainvoke(state, config)

    if state["remaining_steps"] < 2 and response.tool_calls:
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content=(
                        "当前问题需要继续检索知识库，但本轮可用步骤已接近上限。"
                        "我没有拿到足够稳定的检索结果来给出可靠结论，请把问题拆成更具体的一项，"
                        "或补充游戏名称、活动名称、道具名称、配置字段等关键信息后重试。"
                    ),
                )
            ]
        }
    # 我们返回一个列表，因为这将被添加到现有列表中
    return {"messages": [response]}


async def safeguard_input(state: AgentState, config: RunnableConfig) -> AgentState:
    safeguard = Safeguard()
    safety_output = await safeguard.ainvoke(state["messages"])
    return {"safety": safety_output, "messages": []}


async def block_unsafe_content(state: AgentState, config: RunnableConfig) -> AgentState:
    safety: SafeguardOutput = state["safety"]
    return {"messages": [format_safety_message(safety)]}


# 定义图
agent = StateGraph(AgentState)
agent.add_node("model", acall_model)
agent.add_node("tools", ToolNode(tools))
agent.add_node("guard_input", safeguard_input)
agent.add_node("block_unsafe_content", block_unsafe_content)
agent.set_entry_point("guard_input")


# 检查是否存在不安全输入，如果发现则阻止进一步处理
def check_safety(state: AgentState) -> Literal["unsafe", "safe"]:
    safety: SafeguardOutput = state["safety"]
    match safety.safety_assessment:
        case SafetyAssessment.UNSAFE:
            return "unsafe"
        case _:
            return "safe"


agent.add_conditional_edges(
    "guard_input", check_safety, {"unsafe": "block_unsafe_content", "safe": "model"}
)

# 阻止不安全内容后始终结束 (END)
agent.add_edge("block_unsafe_content", END)

# 在 "tools" 之后始终运行 "model"
agent.add_edge("tools", "model")


# 在 "model" 之后，如果有工具调用，则运行 "tools"。否则结束 (END)。
def pending_tool_calls(state: AgentState) -> Literal["tools", "done"]:
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage):
        raise TypeError(f"Expected AIMessage, got {type(last_message)}")
    if last_message.tool_calls:
        return "tools"
    return "done"


agent.add_conditional_edges("model", pending_tool_calls, {"tools": "tools", "done": END})

rag_assistant = agent.compile()
