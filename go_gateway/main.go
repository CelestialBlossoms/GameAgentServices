package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

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

	srv := &http.Server{
		Addr:    fmt.Sprintf(":%s", cfg.Port),
		Handler: engine,
	}

	// 监听退出信号
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[Gateway] 服务启动失败: %v", err)
		}
	}()

	<-quit
	log.Println("[Gateway] 收到退出信号，开始优雅关闭...")

	// 设定 15 秒的最大等待时间，等待正在处理的请求完成
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("[Gateway] 服务关闭失败: %v", err)
	}

	log.Println("[Gateway] 网关服务已停止")
}
