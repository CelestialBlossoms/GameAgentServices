package handlers

import (
	"net/http"
	"runtime"
	"time"

	"github.com/gin-gonic/gin"
)

var startTime = time.Now()

// Health 健康检查接口
func Health(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":  "ok",
		"service": "go-gateway",
	})
}

// GatewayInfo 网关运行信息
func GatewayInfo(c *gin.Context) {
	var memStats runtime.MemStats
	runtime.ReadMemStats(&memStats)

	c.JSON(http.StatusOK, gin.H{
		"service":       "GameAgentServices Go Gateway",
		"version":       "1.0.0",
		"uptime":        time.Since(startTime).String(),
		"go_version":    runtime.Version(),
		"goroutines":    runtime.NumGoroutine(),
		"os_arch":       runtime.GOOS + "/" + runtime.GOARCH,
		"memory": gin.H{
			"alloc_mb":       memStats.Alloc / 1024 / 1024,
			"sys_mb":         memStats.Sys / 1024 / 1024,
			"gc_cycles":      memStats.NumGC,
		},
	})
}
