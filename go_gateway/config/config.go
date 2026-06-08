package config

import "os"

// Config 网关全局配置
type Config struct {
	// Port 网关服务监听端口
	Port string

	// PythonAgentURL Python Agent 后端服务地址（内部网络）
	PythonAgentURL string

	// RedisURL Redis 连接地址（用于限流和任务状态）
	RedisURL string

	// AuthSecret 鉴权密钥（与 Python 端保持一致）
	AuthSecret string

	// RateLimitPerSecond 每秒最大请求数
	RateLimitPerSecond int

	// TelemetryLogPath 调用链 Trace 审计日志路径
	TelemetryLogPath string
}

// Load 从环境变量加载配置，提供合理默认值
func Load() *Config {
	return &Config{
		Port:               getEnv("GATEWAY_PORT", "8000"),
		PythonAgentURL:     getEnv("PYTHON_AGENT_URL", "http://agent_service:8080"),
		RedisURL:           getEnv("REDIS_URL", "redis://localhost:6379/0"),
		AuthSecret:         getEnv("AUTH_SECRET", ""),
		RateLimitPerSecond: 100,
		TelemetryLogPath:   getEnv("TELEMETRY_LOG_PATH", "/var/log/gateway/traces.jsonl"),
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
