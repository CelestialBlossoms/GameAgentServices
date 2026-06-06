from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agents.bg_task_agent.bg_task_agent import bg_task_agent
from agents.chatbot import chatbot
from agents.command_agent import command_agent
from agents.github_mcp_agent.github_mcp_agent import github_mcp_agent
from agents.interrupt_agent import interrupt_agent
from agents.knowledge_base_agent import kb_agent
from agents.langgraph_supervisor_agent import langgraph_supervisor_agent
from agents.langgraph_supervisor_hierarchy_agent import langgraph_supervisor_hierarchy_agent
from agents.lazy_agent import LazyLoadingAgent
from agents.rag_assistant import rag_assistant
from agents.research_assistant import research_assistant
from schema import AgentInfo

DEFAULT_AGENT = "research-assistant"

# 类型别名，用于处理 LangGraph 的不同智能体模式
# - @entrypoint 函数返回 Pregel
# - StateGraph().compile() 返回 CompiledStateGraph
AgentGraph = CompiledStateGraph | Pregel  # get_agent() 的返回类型（始终已加载）
AgentGraphLike = CompiledStateGraph | Pregel | LazyLoadingAgent  # 可存储在注册表中的类型


@dataclass
class Agent:
    description: str
    name: str = ""
    graph_like: AgentGraphLike | None = None

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.description


agents: dict[str, Agent] = {
    "chatbot": Agent(
        description="面向游戏服务日常巡检、发布协助、异常定位和运营问题排查的运维助手。",
        name="游戏运维",
        graph_like=chatbot,
    ),
    "research-assistant": Agent(
        description="面向游戏活动咨询、活动规则解读、运营内容生成和玩家问题归纳的活动助手。",
        name="游戏活动",
        graph_like=research_assistant,
    ),
    "rag-assistant": Agent(
        description="面向任务文本、道具说明、FAQ 和游戏规则知识库检索的内容生成助手。",
        name="道具生成",
        graph_like=rag_assistant,
    ),
    "command-agent": Agent(
        description="面向玩家智能客服、问题分类、回复模板和异常工单辅助处理的客服助手。",
        name="游戏客服",
        graph_like=command_agent,
    ),
    "bg-task-agent": Agent(
        description="面向 Prompt 版本、灰度开关、限流配置、任务记录和后台作业处理的配置助手。",
        name="游戏配置",
        graph_like=bg_task_agent,
    ),
    "langgraph-supervisor-agent": Agent(
        description="基于简历中的 LangGraph 多 Agent 平台经验，统一协调客服、活动、道具、配置和运维任务。",
        name="游戏服务调度",
        graph_like=langgraph_supervisor_agent,
    ),
    "langgraph-supervisor-hierarchy-agent": Agent(
        description="面向游戏 AI Agent 智能服务平台的层级化任务编排，支持复杂游戏业务流程拆解和多 Agent 协作。",
        name="游戏业务编排",
        graph_like=langgraph_supervisor_hierarchy_agent,
    ),
    "interrupt-agent": Agent(
        description="面向运营内容、配置变更和敏感客服回复的人机协同审核流程。",
        name="人工审核流程",
        graph_like=interrupt_agent,
    ),
    "knowledge-base-agent": Agent(
        description="面向游戏规则、活动说明、FAQ、任务文本和道具说明的 RAG 知识库检索能力。",
        name="游戏知识库",
        graph_like=kb_agent,
    ),
    "github-mcp-agent": Agent(
        description="面向游戏 AI Agent 平台代码仓库、版本迭代、上线检查清单和故障复盘文档的研发协作助手。",
        name="研发协作助手",
        graph_like=github_mcp_agent,
    ),
}


async def load_agent(agent_id: str) -> None:
    """根据需要加载延迟加载的智能体。"""
    graph_like = agents[agent_id].graph_like
    if isinstance(graph_like, LazyLoadingAgent):
        await graph_like.load()


def get_agent(agent_id: str) -> AgentGraph:
    """获取智能体图，根据需要加载延迟加载的智能体。"""
    agent_graph = agents[agent_id].graph_like

    # 如果是延迟加载智能体，确保它已加载并返回其图
    if isinstance(agent_graph, LazyLoadingAgent):
        if not agent_graph._loaded:
            raise RuntimeError(f"Agent {agent_id} not loaded. Call load() first.")
        return agent_graph.get_graph()

    # 否则直接返回图
    return agent_graph


def get_all_agent_info() -> list[AgentInfo]:
    return [
        AgentInfo(key=agent_id, name=agent.name, description=agent.description)
        for agent_id, agent in agents.items()
    ]
