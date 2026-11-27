package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/api"
	"github.com/tanbaocorp/axisstream-erp/internal/bridgeclient"
	"github.com/tanbaocorp/axisstream-erp/internal/config"
	"github.com/tanbaocorp/axisstream-erp/internal/logger"
	"github.com/tanbaocorp/axisstream-erp/internal/realtime"
	"github.com/tanbaocorp/axisstream-erp/internal/repository"
	"github.com/tanbaocorp/axisstream-erp/internal/service"
)

func main() {
	cfg, err := config.LoadFromEnv()
	if err != nil {
		fmt.Fprintf(os.Stderr, "config error: %v\n", err)
		os.Exit(1)
	}
	log := logger.NewJSONLogger(os.Stdout, cfg.LogLevel)
	log.Info("Starting AxisTech ISO ERP Platform", "config", cfg.String())

	store, err := repository.NewEncryptedStore(cfg.DataFilePath, cfg.EncryptionKey)
	if err != nil {
		log.Error("Failed to initialize repository store", "error", err.Error())
		os.Exit(1)
	}

	hub := realtime.NewHub(64)
	bridge := bridgeclient.New(cfg.BridgeBaseURL, cfg.BridgeAPIKey)
	svc := service.NewERPService(store, bridge, hub, log)
	svc.ConfigureSecurityPolicy(cfg.RateLimitRPM, cfg.RequireAPIKey)
	worker := service.NewSyncWorker(svc, bridge, time.Duration(cfg.SyncIntervalSec)*time.Second, log)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	go worker.Start(ctx)

	handler := api.NewHandler(svc, store, hub, log)
	router := api.NewRouterWithOptions(handler, log, api.RouterSecurityOptions{
		RateLimitRPM:  cfg.RateLimitRPM,
		RequireAPIKey: cfg.RequireAPIKey,
		APIKey:        cfg.ERPAPIKey,
	})

	srv := &http.Server{
		Addr:              fmt.Sprintf(":%d", cfg.Port),
		Handler:           router,
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		log.Info("ERP HTTP Server listening", "port", cfg.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("HTTP server error", "error", err.Error())
			stop()
		}
	}()

	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdownCtx)
	log.Info("ERP HTTP Server stopped cleanly")
}
