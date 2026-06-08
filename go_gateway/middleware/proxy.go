package middleware

import (
	"bufio"
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/game-agent-services/go-gateway/config"
)

// ReverseProxy 反向代理中间件，将请求转发到 Python Agent Service
type ReverseProxy struct {
	target *url.URL
	proxy  *httputil.ReverseProxy
	cfg    *config.Config
}

// NewReverseProxy 创建反向代理实例
func NewReverseProxy(cfg *config.Config) *ReverseProxy {
	target, err := url.Parse(cfg.PythonAgentURL)
	if err != nil {
		log.Fatalf("[Proxy] 无法解析 Python Agent URL: %v", err)
	}

	proxy := httputil.NewSingleHostReverseProxy(target)

	// 自定义 Transport，配置连接池和超时
	proxy.Transport = &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 50,
		IdleConnTimeout:     90 * time.Second,
		ResponseHeaderTimeout: 120 * time.Second,
	}

	// 错误处理：当 Python 后端不可用时的兜底
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		log.Printf("[Proxy] 代理转发失败: %v", err)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		fmt.Fprintf(w, `{"error":"Python Agent 服务不可用","detail":"%s"}`, err.Error())
	}

	return &ReverseProxy{
		target: target,
		proxy:  proxy,
		cfg:    cfg,
	}
}

// Forward 普通请求的反向代理（invoke、history、feedback 等）
func (rp *ReverseProxy) Forward(c *gin.Context) {
	startTime := time.Now()
	requestID := c.GetString("X-Request-ID")

	log.Printf("[Proxy] [%s] 转发请求: %s %s -> %s",
		requestID, c.Request.Method, c.Request.URL.Path, rp.target.String())

	// 重写 Host 头
	c.Request.Host = rp.target.Host
	c.Request.URL.Scheme = rp.target.Scheme
	c.Request.URL.Host = rp.target.Host

	rp.proxy.ServeHTTP(c.Writer, c.Request)

	latency := time.Since(startTime)
	log.Printf("[Proxy] [%s] 请求完成: %s %s 耗时=%v",
		requestID, c.Request.Method, c.Request.URL.Path, latency)
}

// ForwardStream SSE 流式响应的反向代理（带 Token 拦截统计）
func (rp *ReverseProxy) ForwardStream(c *gin.Context) {
	startTime := time.Now()
	requestID := c.GetString("X-Request-ID")

	log.Printf("[Proxy:Stream] [%s] 转发流式请求: %s %s",
		requestID, c.Request.Method, c.Request.URL.Path)

	// 构建发往 Python Agent 的请求
	targetURL := fmt.Sprintf("%s%s", rp.cfg.PythonAgentURL, c.Request.URL.Path)
	proxyReq, err := http.NewRequestWithContext(c.Request.Context(), c.Request.Method, targetURL, c.Request.Body)
	if err != nil {
		log.Printf("[Proxy:Stream] [%s] 创建代理请求失败: %v", requestID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "创建代理请求失败"})
		return
	}

	// 复制原始请求头
	for key, values := range c.Request.Header {
		for _, value := range values {
			proxyReq.Header.Add(key, value)
		}
	}
	proxyReq.Header.Set("X-Request-ID", requestID)
	proxyReq.Header.Set("X-Forwarded-For", c.ClientIP())

	// 使用自定义 HTTP 客户端发起流式请求
	client := &http.Client{
		Timeout: 300 * time.Second, // Agent 任务最大超时 5 分钟
		Transport: &http.Transport{
			MaxIdleConns:        50,
			MaxIdleConnsPerHost: 20,
			IdleConnTimeout:     90 * time.Second,
		},
	}

	resp, err := client.Do(proxyReq)
	if err != nil {
		log.Printf("[Proxy:Stream] [%s] 上游请求失败: %v", requestID, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": "Python Agent 服务不可用"})
		return
	}
	defer resp.Body.Close()

	// 设置 SSE 响应头
	c.Writer.Header().Set("Content-Type", "text/event-stream")
	c.Writer.Header().Set("Cache-Control", "no-cache")
	c.Writer.Header().Set("Connection", "keep-alive")
	c.Writer.Header().Set("X-Request-ID", requestID)
	c.Writer.WriteHeader(resp.StatusCode)

	// 逐行读取上游 SSE 数据并转发给客户端，同时统计 Token
	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024) // 最大 1MB 行缓冲

	tokenCount := 0
	chunkCount := 0
	var firstTokenTime time.Duration
	clientDisconnected := false

	for scanner.Scan() {
		line := scanner.Text()

		// 检查客户端是否已断开
		select {
		case <-c.Request.Context().Done():
			clientDisconnected = true
			log.Printf("[Proxy:Stream] [%s] 检测到客户端断开连接，停止转发", requestID)
			goto done
		default:
		}

		// 统计 Token（解析 SSE data 行）
		if strings.HasPrefix(line, "data: ") {
			chunkCount++
			dataContent := strings.TrimPrefix(line, "data: ")

			// 记录首 Token 耗时
			if chunkCount == 1 {
				firstTokenTime = time.Since(startTime)
			}

			// 简单估算 Token 数量（按空格和标点分词）
			if dataContent != "[DONE]" && strings.Contains(dataContent, "token") {
				tokenCount++
			}
		}

		// 原封不动地将每一行 SSE 数据 Flush 给前端
		fmt.Fprintf(c.Writer, "%s\n", line)
		c.Writer.(http.Flusher).Flush()
	}

done:
	totalLatency := time.Since(startTime)

	// 输出调用链摘要日志
	log.Printf("[Proxy:Stream] [%s] 流式传输结束 | chunks=%d tokens≈%d 首Token=%v 总耗时=%v 客户端断开=%v",
		requestID, chunkCount, tokenCount, firstTokenTime, totalLatency, clientDisconnected)

	if err := scanner.Err(); err != nil {
		log.Printf("[Proxy:Stream] [%s] 读取上游流时发生错误: %v", requestID, err)
	}
}
