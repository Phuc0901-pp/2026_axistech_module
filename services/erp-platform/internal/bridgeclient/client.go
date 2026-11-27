package bridgeclient

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/domain"
)

// BridgeSSEEvent represents an event streamed by Python bridge /api/v1/stream.
type BridgeSSEEvent struct {
	EventType string `json:"event_type"`
	Data      string `json:"data"`
}

// Client is an HTTP + SSE client for the Python axisstream-bridge with Retry & Circuit Breaker.
type Client struct {
	baseURL       string
	apiKey        string
	httpClient    *http.Client
	maxRetries    int
	baseBackoff   time.Duration
	cbMu          sync.Mutex
	cbFailures    int
	cbThreshold   int
	cbOpenUntil   time.Time
	cbRecoveryDur time.Duration
}

type Option func(*Client)

func WithTimeout(d time.Duration) Option {
	return func(c *Client) { c.httpClient.Timeout = d }
}

func WithRetries(maxRetries int, baseBackoff time.Duration) Option {
	return func(c *Client) {
		c.maxRetries = maxRetries
		c.baseBackoff = baseBackoff
	}
}

func WithCircuitBreaker(threshold int, recovery time.Duration) Option {
	return func(c *Client) {
		c.cbThreshold = threshold
		c.cbRecoveryDur = recovery
	}
}

func New(baseURL, apiKey string, opts ...Option) *Client {
	c := &Client{
		baseURL:       strings.TrimRight(baseURL, "/"),
		apiKey:        apiKey,
		httpClient:    &http.Client{Timeout: 15 * time.Second},
		maxRetries:    2,
		baseBackoff:   100 * time.Millisecond,
		cbThreshold:   5,
		cbRecoveryDur: 20 * time.Second,
	}
	for _, opt := range opts {
		opt(c)
	}
	return c
}

func (c *Client) allowRequest() error {
	c.cbMu.Lock()
	defer c.cbMu.Unlock()
	if c.cbFailures >= c.cbThreshold && time.Now().Before(c.cbOpenUntil) {
		return fmt.Errorf("%w: bridge circuit breaker open", domain.ErrUpstream)
	}
	return nil
}

func (c *Client) recordSuccess() {
	c.cbMu.Lock()
	defer c.cbMu.Unlock()
	c.cbFailures = 0
	c.cbOpenUntil = time.Time{}
}

func (c *Client) recordFailure() {
	c.cbMu.Lock()
	defer c.cbMu.Unlock()
	c.cbFailures++
	if c.cbFailures >= c.cbThreshold {
		c.cbOpenUntil = time.Now().Add(c.cbRecoveryDur)
	}
}

func (c *Client) doJSON(ctx context.Context, method, path, correlationID string, out any) error {
	if err := c.allowRequest(); err != nil {
		return err
	}

	var lastErr error
	for attempt := 0; attempt <= c.maxRetries; attempt++ {
		req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, nil)
		if err != nil {
			return err
		}
		req.Header.Set("Accept", "application/json")
		req.Header.Set("X-API-Key", c.apiKey)
		if correlationID != "" {
			req.Header.Set("X-Correlation-ID", correlationID)
		}

		resp, err := c.httpClient.Do(req)
		if err != nil {
			c.recordFailure()
			lastErr = fmt.Errorf("%w: %v", domain.ErrUpstream, err)
			if attempt < c.maxRetries {
				select {
				case <-ctx.Done():
					return ctx.Err()
				case <-time.After(c.baseBackoff * time.Duration(1<<attempt)):
				}
				continue
			}
			return lastErr
		}

		body, readErr := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
		_ = resp.Body.Close()
		if readErr != nil {
			c.recordFailure()
			return fmt.Errorf("%w: read body failed: %v", domain.ErrUpstream, readErr)
		}

		if resp.StatusCode >= 500 || resp.StatusCode == 429 {
			c.recordFailure()
			lastErr = fmt.Errorf("%w: bridge HTTP %d", domain.ErrUpstream, resp.StatusCode)
			if attempt < c.maxRetries {
				select {
				case <-ctx.Done():
					return ctx.Err()
				case <-time.After(c.baseBackoff * time.Duration(1<<attempt)):
				}
				continue
			}
			return lastErr
		}

		if resp.StatusCode == 401 || resp.StatusCode == 403 {
			return fmt.Errorf("%w: bridge auth HTTP %d", domain.ErrUnauthorized, resp.StatusCode)
		}
		if resp.StatusCode >= 400 {
			return fmt.Errorf("%w: bridge HTTP %d", domain.ErrValidation, resp.StatusCode)
		}

		c.recordSuccess()
		if out != nil && len(body) > 0 {
			if err := json.Unmarshal(body, out); err != nil {
				return fmt.Errorf("decode bridge response %s: %w", path, err)
			}
		}
		return nil
	}
	return lastErr
}

func (c *Client) FetchProjects(ctx context.Context, cid string) ([]domain.Project, error) {
	var env struct {
		Data []domain.Project `json:"data"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects", cid, &env); err != nil {
		return nil, err
	}
	return env.Data, nil
}

func (c *Client) FetchDevices(ctx context.Context, projectID, cid string) ([]domain.Device, error) {
	var env struct {
		Data []domain.Device `json:"data"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects/"+projectID+"/devices", cid, &env); err != nil {
		return nil, err
	}
	return env.Data, nil
}

func (c *Client) FetchTelemetry(ctx context.Context, projectID, cid string) ([]domain.DeviceSnapshot, error) {
	var env struct {
		Data []domain.DeviceSnapshot `json:"data"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects/"+projectID+"/telemetry", cid, &env); err != nil {
		return nil, err
	}
	return env.Data, nil
}

func (c *Client) FetchTelemetryHistory(ctx context.Context, projectID, deviceID string, hours int, cid string) ([]domain.TelemetryReading, error) {
	if hours <= 0 {
		hours = 24
	}
	q := url.Values{}
	q.Set("hours", fmt.Sprintf("%d", hours))
	if strings.TrimSpace(deviceID) != "" {
		q.Set("device_id", strings.TrimSpace(deviceID))
	}
	var env struct {
		Data []domain.TelemetryReading `json:"data"`
	}
	path := "/api/v1/projects/" + projectID + "/telemetry/history?" + q.Encode()
	if err := c.doJSON(ctx, http.MethodGet, path, cid, &env); err != nil {
		return nil, err
	}
	return env.Data, nil
}

func (c *Client) FetchFields(ctx context.Context, projectID, cid string) ([]domain.FieldLocation, error) {
	var env struct {
		Data []domain.FieldLocation `json:"data"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects/"+projectID+"/fields", cid, &env); err != nil {
		return nil, err
	}
	return env.Data, nil
}

func (c *Client) FetchAssets(ctx context.Context, projectID, cid string) ([]domain.EquipmentAsset, error) {
	var env struct {
		Data []domain.EquipmentAsset `json:"data"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects/"+projectID+"/assets", cid, &env); err != nil {
		return nil, err
	}
	return env.Data, nil
}

func (c *Client) FetchAlertPolicies(ctx context.Context, projectID, cid string) ([]domain.AlertPolicy, error) {
	var env struct {
		Data []domain.AlertPolicy `json:"data"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects/"+projectID+"/alerts/policies", cid, &env); err != nil {
		return nil, err
	}
	return env.Data, nil
}

func (c *Client) FetchAlertHistory(ctx context.Context, projectID, cid string) ([]domain.AlertHistoryItem, error) {
	var env struct {
		Data []domain.AlertHistoryItem `json:"data"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects/"+projectID+"/alerts/history", cid, &env); err != nil {
		return nil, err
	}
	return env.Data, nil
}

func (c *Client) FetchProviders(ctx context.Context, projectID, cid string) ([]domain.ProviderConnection, error) {
	var env struct {
		Data []domain.ProviderConnection `json:"data"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects/"+projectID+"/providers", cid, &env); err != nil {
		return nil, err
	}
	return env.Data, nil
}

func (c *Client) FetchWeatherExchange(ctx context.Context, projectID, cid string) ([]domain.ExchangeTokenInfo, []domain.WeatherExchangeRow, error) {
	var env struct {
		Tokens []domain.ExchangeTokenInfo  `json:"tokens"`
		Data   []domain.WeatherExchangeRow `json:"data"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects/"+projectID+"/exchange/weather", cid, &env); err != nil {
		return nil, nil, err
	}
	return env.Tokens, env.Data, nil
}

func (c *Client) FetchWeatherForecast(ctx context.Context, projectID, cid string) (*domain.ProjectForecastBundle, error) {
	var bundle domain.ProjectForecastBundle
	if err := c.doJSON(ctx, http.MethodGet, "/api/v1/projects/"+projectID+"/forecast", cid, &bundle); err != nil {
		return nil, err
	}
	return &bundle, nil
}

func (c *Client) TriggerSync(ctx context.Context, cid string) error {
	return c.doJSON(ctx, http.MethodPost, "/api/v1/sync/trigger", cid, nil)
}

func (c *Client) CheckHealth(ctx context.Context) (string, error) {
	status, _, _, err := c.FetchHealthStatus(ctx)
	return status, err
}

func (c *Client) FetchHealthStatus(ctx context.Context) (string, string, string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/health/ready", nil)
	if err != nil {
		return "DOWN", "", err.Error(), err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "DOWN", "", err.Error(), err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	var parsed struct {
		Status    string `json:"status"`
		Mode      string `json:"mode"`
		LastError string `json:"last_error"`
	}
	_ = json.Unmarshal(body, &parsed)
	if parsed.Status == "" {
		if resp.StatusCode == http.StatusOK {
			parsed.Status = "READY"
		} else {
			parsed.Status = "DEGRADED"
		}
	}
	if resp.StatusCode != http.StatusOK {
		return parsed.Status, parsed.Mode, parsed.LastError, fmt.Errorf("bridge ready status %d", resp.StatusCode)
	}
	return parsed.Status, parsed.Mode, parsed.LastError, nil
}

// SubscribeStream connects to the Python bridge SSE endpoint and invokes onEvent per frame.
func (c *Client) SubscribeStream(ctx context.Context, onEvent func(BridgeSSEEvent)) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/stream", nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("X-API-Key", c.apiKey)

	streamClient := &http.Client{} // no overall timeout for long-lived SSE stream
	resp, err := streamClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("sse stream HTTP %d", resp.StatusCode)
	}

	scanner := bufio.NewScanner(resp.Body)
	var eventType, dataBuf string
	for scanner.Scan() {
		line := scanner.Text()
		if line == "" {
			if dataBuf != "" {
				if eventType == "" {
					eventType = "message"
				}
				onEvent(BridgeSSEEvent{EventType: eventType, Data: strings.TrimSpace(dataBuf)})
			}
			eventType = ""
			dataBuf = ""
			continue
		}
		if strings.HasPrefix(line, "event:") {
			eventType = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
		} else if strings.HasPrefix(line, "data:") {
			dataBuf += strings.TrimSpace(strings.TrimPrefix(line, "data:")) + "\n"
		}
	}
	return scanner.Err()
}
