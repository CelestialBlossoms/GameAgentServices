from langchain.agents import create_agent
from langgraph_supervisor import create_supervisor

from agents.langgraph_supervisor_agent import add, multiply, web_search
from core import get_model, settings

model = get_model(settings.DEFAULT_MODEL)


def workflow(chosen_model):
    math_agent = create_agent(
        model=chosen_model,
        tools=[add, multiply],
        name="sub-agent-math_expert",  # 将图节点标识为子智能体
        system_prompt="You are a math expert. Always use one tool at a time.",
    ).with_config(tags=["skip_stream"])

    research_agent = (
        create_supervisor(
            [math_agent],
            model=chosen_model,
            tools=[web_search],
            prompt="You are a world class researcher with access to web search. Do not do any math, you have a math expert for that. ",
            supervisor_name="supervisor-research_expert",  # 将图节点标识为数学智能体的主管
        )
        .compile(
            name="sub-agent-research_expert"
        )  # 将图节点标识为主主管的子智能体
        .with_config(tags=["skip_stream"])
    )  # 在 UI 中，子智能体的流式令牌会被忽略

    # Create supervisor workflow
    return create_supervisor(
        [research_agent],
        model=chosen_model,
        prompt=(
            "You are a team supervisor managing a research expert with math capabilities."
            "For current events, use research_agent. "
        ),
        add_handoff_back_messages=True,
        # UI 现在要求此项为 True，这样我们就不必猜测何时发生交回 (handoff back)
        output_mode="full_history",  # 否则在重新加载对话时，子智能体的消息将不被包含
    )  # 主管的默认名称是 "supervisor"。


langgraph_supervisor_hierarchy_agent = workflow(model).compile()
