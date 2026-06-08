package handlers

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/game-agent-services/go-gateway/config"
)

// TraceEvent Python Agent 上报的调用链数据结构
type TraceEvent struct {
	// 请求标识
	RequestID string `json:"request_id"`
	AgentID   string `json:"agent_id"`
	SessionID string `json:"session_id,omitempty"`
	UserID    string `json:"user_id,omitempty"`

	// 性能指标
	TotalLatencyMs   float64 `json:"total_latency_ms"`
	FirstTokenMs     float64 `json:"first_token_ms,omitempty"`
	RAGLatencyMs     float64 `json:"rag_latency_ms,omitempty"`
	ToolLatencyMs    float64 `json:"tool_latency_ms,omitempty"`
	LLMLatencyMs     float64 `json:"llm_latency_ms,omitempty"`

	// Token 计费
	InputTokens  int    `json:"input_tokens"`
	OutputTokens int    `json:"output_tokens"`
	ModelName    string `json:"model_name"`

	// 状态
	Status    string `json:"status"` // success / failed / cancelled / timeout
	ErrorMsg  string `json:"error_msg,omitempty"`

	// 元数据
	Timestamp string `json:"timestamp"`
}

// TelemetryHandler 调用链 Trace 数据处理器
type TelemetryHandler struct {
	cfg     *config.Config
	mu      sync.Mutex
	logFile *os.File

	// 内存中的实时统计（面试时可用于展示 Dashboard）
	stats TelemetryStats
}

// TelemetryStats 实时统计数据
type TelemetryStats struct {
	TotalRequests    int64   `json:"total_requests"`
	SuccessCount     int64   `json:"success_count"`
	FailedCount      int64   `json:"failed_count"`
	CancelledCount   int64   `json:"cancelled_count"`
	TotalInputTokens int64   `json:"total_input_tokens"`
	TotalOutputTokens int64  `json:"total_output_tokens"`
	AvgLatencyMs     float64 `json:"avg_latency_ms"`
	latencySum       float64
}

// NewTelemetryHandler 创建 Trace 处理器实例
func NewTelemetryHandler(cfg *config.Config) *TelemetryHandler {
	h := &TelemetryHandler{cfg: cfg}

	// 创建日志目录和文件
	logDir := "/var/log/gateway"
	if err := os.MkdirAll(logDir, 0755); err != nil {
		// 如果无法创建目录（如本地开发），使用当前目录
		logDir = "."
		log.Printf("[Telemetry] 无法创建日志目录 %s，改用当前目录: %v", cfg.TelemetryLogPath, err)
	}

	logPath := logDir + "/traces.jsonl"
	f, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		log.Printf("[Telemetry] 无法打开审计日志文件: %v", err)
	} else {
		h.logFile = f
		log.Printf("[Telemetry] 审计日志写入: %s", logPath)
	}

	return h
}

// ReceiveTrace 接收 Python Agent 上报的 Trace 数据
func (h *TelemetryHandler) ReceiveTrace(c *gin.Context) {
	var event TraceEvent
	if err := c.ShouldBindJSON(&event); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的 Trace 数据格式", "detail": err.Error()})
		return
	}

	// 补充时间戳
	if event.Timestamp == "" {
		event.Timestamp = time.Now().UTC().Format(time.RFC3339)
	}

	// 更新内存统计
	h.mu.Lock()
	h.stats.TotalRequests++
	h.stats.TotalInputTokens += int64(event.InputTokens)
	h.stats.TotalOutputTokens += int64(event.OutputTokens)
	h.stats.latencySum += event.TotalLatencyMs

	switch event.Status {
	case "success":
		h.stats.SuccessCount++
	case "failed":
		h.stats.FailedCount++
	case "cancelled":
		h.stats.CancelledCount++
	}

	if h.stats.TotalRequests > 0 {
		h.stats.AvgLatencyMs = h.stats.latencySum / float64(h.stats.TotalRequests)
	}

	// 写入 JSONL 审计日志
	if h.logFile != nil {
		data, _ := json.Marshal(event)
		h.logFile.Write(append(data, '\n'))
	}
	h.mu.Unlock()

	log.Printf("[Telemetry] 收到 Trace | req=%s agent=%s model=%s tokens=%d/%d latency=%.0fms status=%s",
		event.RequestID, event.AgentID, event.ModelName,
		event.InputTokens, event.OutputTokens,
		event.TotalLatencyMs, event.Status)

	c.JSON(http.StatusOK, gin.H{"status": "accepted"})
}

// GetStats 返回实时统计数据（供 Dashboard 查询）
func (h *TelemetryHandler) GetStats(c *gin.Context) {
	h.mu.Lock()
	defer h.mu.Unlock()

	c.JSON(http.StatusOK, gin.H{
		"stats": h.stats,
	})
}
