package service

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/bridgeclient"
)

// SyncWorker continuously synchronizes AxisStream data via periodic polling + SSE stream.
type SyncWorker struct {
	svc      *ERPService
	bridge   BridgeClient
	interval time.Duration
	log      *slog.Logger
}

func NewSyncWorker(svc *ERPService, bridge BridgeClient, interval time.Duration, log *slog.Logger) *SyncWorker {
	return &SyncWorker{svc: svc, bridge: bridge, interval: interval, log: log}
}

func (w *SyncWorker) Start(ctx context.Context) {
	// Initial sync immediately on boot
	_ = w.svc.SyncOnce(ctx, fmt.Sprintf("boot-%d", time.Now().UnixNano()))

	go w.listenSSE(ctx)

	ticker := time.NewTicker(w.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			cid := fmt.Sprintf("poll-%d", time.Now().UnixNano())
			if err := w.svc.SyncOnce(ctx, cid); err != nil {
				w.log.Warn("Periodic bridge sync failed", "correlation_id", cid, "error", err.Error())
			}
		}
	}
}

func (w *SyncWorker) listenSSE(ctx context.Context) {
	for {
		if ctx.Err() != nil {
			return
		}
		err := w.bridge.SubscribeStream(ctx, func(ev bridgeclient.BridgeSSEEvent) {
			if ev.EventType == "telemetry_update" {
				cid := fmt.Sprintf("sse-%d", time.Now().UnixNano())
				_ = w.svc.SyncOnce(ctx, cid)
			}
		})
		if ctx.Err() != nil {
			return
		}
		if err != nil {
			w.log.Debug("Bridge SSE stream disconnected, reconnecting", "error", err.Error())
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(3 * time.Second):
		}
	}
}
