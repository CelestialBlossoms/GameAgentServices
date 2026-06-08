package router

import (
	"github.com/gin-gonic/gin"

	"github.com/game-agent-services/go-gateway/config"
	"github.com/game-agent-services/go-gateway/handlers"
	"github.com/game-agent-services/go-gateway/middleware"
)

// Setup 初始化路由引擎，注册中间件和处理器
func Setup(cfg *config.Config) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	engine := gin.New()

	// 全局中间件
	engine.Use(gin.Recovery())
	engine.Use(middleware.Logger())
	engine.Use(middleware.CORS())
	engine.Use(middleware.RequestID())

	// ==========================================
	// Go 网关自身提供的接口（不代理到 Python）
	// ==========================================

	// 健康检查
	engine.GET("/health", handlers.Health)

	// 网关运行信息
	engine.GET("/gateway/info", handlers.GatewayInfo)

	// 调用链 Trace 上报接口（供 Python Agent 节点异步 POST 上报）
	engine.POST("/telemetry/traces", handlers.NewTelemetryHandler(cfg).ReceiveTrace)

	// ==========================================
	// 反向代理到 Python Agent Service 的接口
	// ==========================================
	proxy := middleware.NewReverseProxy(cfg)

	// 代理组 - 所有 /agent/* 请求转发到 Python
	agentGroup := engine.Group("")
	{
		// 鉴权中间件（如果配置了 AUTH_SECRET）
		if cfg.AuthSecret != "" {
			agentGroup.Use(middleware.Auth(cfg))
		}

		// Agent 同步调用
		agentGroup.POST("/invoke", proxy.Forward)
		agentGroup.POST("/:agent_id/invoke", proxy.Forward)

		// Agent 流式调用（SSE 反向代理 + Token 拦截统计）
		agentGroup.POST("/stream", proxy.ForwardStream)
		agentGroup.POST("/:agent_id/stream", proxy.ForwardStream)

		// 会话历史
		agentGroup.POST("/history", proxy.Forward)

		// 用户反馈
		agentGroup.POST("/feedback", proxy.Forward)

		// 服务元信息
		agentGroup.GET("/info", proxy.Forward)

		// 登录鉴权
		agentGroup.POST("/auth/login", proxy.Forward)
	}

	return engine
}
