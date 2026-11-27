package realtime

import (
	"encoding/json"
	"sync"
	"time"
)

// Event represents a real-time SSE event pushed to ERP Dashboard clients.
type Event struct {
	Type         string    `json:"type"`
	TimestampUTC time.Time `json:"timestamp_utc"`
	Payload      any       `json:"payload"`
}

// Hub is a thread-safe SSE broadcast broker with slow-consumer drop protection.
type Hub struct {
	mu          sync.RWMutex
	subscribers map[chan Event]struct{}
	bufferSize  int
}

func NewHub(bufferSize int) *Hub {
	if bufferSize < 1 {
		bufferSize = 16
	}
	return &Hub{
		subscribers: make(map[chan Event]struct{}),
		bufferSize:  bufferSize,
	}
}

func (h *Hub) Subscribe() (chan Event, func()) {
	ch := make(chan Event, h.bufferSize)
	h.mu.Lock()
	h.subscribers[ch] = struct{}{}
	h.mu.Unlock()

	unsub := func() {
		h.mu.Lock()
		if _, ok := h.subscribers[ch]; ok {
			delete(h.subscribers, ch)
			close(ch)
		}
		h.mu.Unlock()
	}
	return ch, unsub
}

func (h *Hub) SubscriberCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.subscribers)
}

func (h *Hub) Broadcast(ev Event) {
	if ev.TimestampUTC.IsZero() {
		ev.TimestampUTC = time.Now().UTC()
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	for ch := range h.subscribers {
		select {
		case ch <- ev:
		default:
			// Slow consumer: drop oldest or skip without blocking other clients
		}
	}
}

func (ev Event) FormatSSE() string {
	b, _ := json.Marshal(ev)
	return "event: " + ev.Type + "\ndata: " + string(b) + "\n\n"
}
