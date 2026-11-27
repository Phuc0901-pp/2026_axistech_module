package realtime

import (
	"testing"
	"time"
)

func TestGUT020_MultiClientFanOut(t *testing.T) {
	hub := NewHub(4)
	c1, u1 := hub.Subscribe()
	c2, u2 := hub.Subscribe()
	defer u1()
	defer u2()

	hub.Broadcast(Event{Type: "sync_update", Payload: map[string]int{"n": 1}})
	for idx, ch := range []chan Event{c1, c2} {
		select {
		case ev := <-ch:
			if ev.Type != "sync_update" {
				t.Fatalf("client %d got wrong event %s", idx, ev.Type)
			}
		case <-time.After(time.Second):
			t.Fatalf("client %d timed out", idx)
		}
	}
}

func TestGUT021_UnsubscribeCleanup(t *testing.T) {
	hub := NewHub(2)
	_, unsub := hub.Subscribe()
	if hub.SubscriberCount() != 1 {
		t.Fatalf("expected 1 subscriber")
	}
	unsub()
	unsub() // idempotent
	if hub.SubscriberCount() != 0 {
		t.Fatalf("expected 0 subscribers after cleanup")
	}
}

func TestGUT022_SlowConsumerNonBlockingDrop(t *testing.T) {
	hub := NewHub(1)
	_, unsub := hub.Subscribe()
	defer unsub()

	// Fill buffer=1 and send 5 more without reading; Broadcast must not block
	done := make(chan struct{})
	go func() {
		for i := 0; i < 6; i++ {
			hub.Broadcast(Event{Type: "tick", Payload: i})
		}
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("Broadcast blocked on slow subscriber")
	}
}
