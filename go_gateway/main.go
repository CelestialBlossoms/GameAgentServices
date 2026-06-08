package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/game-agent-services/go-gateway/config"
	"github.com/game-agent-services/go-gateway/router"
)

func main() {
	// 加载配置
	cfg := config.Load()

	log.Printf("[Gateway] ============================================")
	log.Printf("[Gateway] GameAgentServices Go 控制网关启动中...")
	log.Printf("[Gateway] 监听端口: %s", cfg.Port)
	log.Printf("[Gateway] Python Agent 后端地址: %s", cfg.PythonAgentURL)
	log.Printf("[Gateway] Redis 地址: %s", cfg.RedisURL)
	log.Printf("[Gateway] ============================================")

	// 初始化路由
	engine := router.Setup(cfg)

	// 优雅退出
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		addr := fmt.Sprintf(":%s", cfg.Port)
		if err := engine.Run(addr); err != nil {
			log.Fatalf("[Gateway] 服务启动失败: %v", err)
		}
	}()

	<-quit
	log.Println("[Gateway] 收到退出信号，正在优雅关闭...")
	log.Println("[Gateway] 网关服务已停止")
}
