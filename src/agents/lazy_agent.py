"""具有异步初始化和动态图创建功能的智能体类型。"""

from abc import ABC, abstractmethod

from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel


class LazyLoadingAgent(ABC):
    """需要异步加载的智能体的基类。"""

    def __init__(self) -> None:
        """初始化智能体。"""
        self._loaded = False
        self._graph: CompiledStateGraph | Pregel | None = None

    @abstractmethod
    async def load(self) -> None:
        """
        为此智能体执行异步加载。

        此方法在服务启动期间调用，应处理：
        - 设置外部连接（MCP 客户端、数据库等）
        - 加载工具或资源
        - 所需的任何其他异步设置
        - 创建智能体的图
        """
        raise NotImplementedError  # pragma: no cover

    def get_graph(self) -> CompiledStateGraph | Pregel:
        """
        获取智能体的图。

        返回在 load() 期间创建的图实例。

        返回：
            智能体的图 (CompiledStateGraph 或 Pregel)
        """
        if not self._loaded:
            raise RuntimeError("Agent not loaded. Call load() first.")
        if self._graph is None:
            raise RuntimeError("Agent graph not created during load().")
        return self._graph
