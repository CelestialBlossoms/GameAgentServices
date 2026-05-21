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
    "chatbot": Agent(description="一个简单的聊天机器人。", name="聊天机器人", graph_like=chatbot),
    "research-assistant": Agent(
        description="支持网页搜索和计算器的 AI 研究助手。",
        name="研究助手",
        graph_like=research_assistant,
    ),
    "rag-assistant": Agent(
        description="RAG 知识库助手，可查询企业内部文档。",
        name="RAG 知识库助手",
        graph_like=rag_assistant,
    ),
    "command-agent": Agent(description="命令执行智能体。", name="命令智能体", graph_like=command_agent),
    "bg-task-agent": Agent(description="后台任务智能体。", name="后台任务", graph_like=bg_task_agent),
    "langgraph-supervisor-agent": Agent(
        description="多智能体主管协调器",
        name="主管智能体",
        graph_like=langgraph_supervisor_agent,
    ),
    "langgraph-supervisor-hierarchy-agent": Agent(
        description="支持嵌套层级的多智能体主管",
        name="层级主管智能体",
        graph_like=langgraph_supervisor_hierarchy_agent,
    ),
    "interrupt-agent": Agent(
        description="支持中断流程的智能体。", name="中断流程", graph_like=interrupt_agent
    ),
    "knowledge-base-agent": Agent(
        description="基于 Amazon Bedrock 知识库的 RAG 智能体",
        name="知识库检索",
        graph_like=kb_agent,
    ),
    "github-mcp-agent": Agent(
        description="集成 GitHub MCP 工具，支持仓库管理和开发工作流。",
        name="GitHub 助手",
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
