package core

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestNativeExpectedDurationSurvivesPlaybackRoutes(t *testing.T) {
	engine, err := newNativeEngine(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(engine.downloads.close)
	media := providerMedia{URL: "https://primary.example.test/public.mp4", Duration: 167138 * time.Millisecond, Quality: 720,
		Variants: []providerMedia{{URL: "https://backup.example.test/public.mp4", Quality: 720}}}
	choice := nativePlaybackChoices(media, 0)
	if len(choice.media) != 2 || choice.media[1].Duration != media.Duration {
		t.Fatal("backup route lost declared duration")
	}
	first, err := engine.nativeOpenPlayback(context.Background(), choice)
	if err != nil {
		t.Fatal(err)
	}
	if first.ExpectedDurationSeconds != 167.138 {
		t.Fatal("online plan lost declared duration", first.ExpectedDurationSeconds)
	}
	next, err := engine.nativeNextPlayback(context.Background(), first.Session)
	if err != nil {
		t.Fatal(err)
	}
	if next.ExpectedDurationSeconds != 167.138 {
		t.Fatal("alternate plan lost declared duration")
	}
	engine.nativeReleasePlayback(next.Session)
	engine.stream.server.Close()
	encoded, _ := json.Marshal(next)
	if !strings.Contains(string(encoded), `"expectedDurationSeconds":167.138`) {
		t.Fatal("duration missing from JSON plan", string(encoded))
	}
}

func TestNativeExpectedDurationPersistsThroughDownloadAndRestart(t *testing.T) {
	payload := bytes.Repeat([]byte("synthetic-duration-bridge"), 100)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("ETag", `"duration-fixture"`)
		http.ServeContent(w, r, "media.mp4", time.Time{}, bytes.NewReader(payload))
	}))
	t.Cleanup(upstream.Close)
	manager := downloadTestManager(t)
	manager.resolve = func(context.Context, nativeDownloadJob) (providerMedia, error) {
		return providerMedia{URL: upstream.URL + "/media.mp4", Duration: 12345 * time.Millisecond, Quality: 720}, nil
	}
	input := downloadTestInput(1)
	if _, err := manager.enqueue(input); err != nil {
		t.Fatal(err)
	}
	jobs := waitDownloads(t, manager, func(rows []nativeDownloadJob) bool { return len(rows) == 1 && rows[0].State == "completed" })
	if jobs[0].ExpectedDurationSeconds != 12.345 {
		t.Fatal("download record lost declared duration")
	}
	manager.close()
	reopened := newNativeDownloads(manager.engine)
	t.Cleanup(reopened.close)
	plan, found, err := reopened.localPlan(input.Drama.ID, 1)
	if err != nil || !found || !plan.Local || plan.ExpectedDurationSeconds != 12.345 {
		t.Fatalf("local plan after restart: %+v %v", plan, err)
	}
	encoded, _ := json.Marshal(plan)
	if !strings.Contains(string(encoded), `"expectedDurationSeconds":12.345`) {
		t.Fatal("local plan JSON missing declared duration")
	}
}

func TestNativeExpectedDurationDoesNotInventMissingDeclarations(t *testing.T) {
	if nativeExpectedDuration(providerMedia{}) != 0 || nativeExpectedDuration(providerMedia{Duration: -time.Second}) != 0 {
		t.Fatal("invented source duration")
	}
	encoded, _ := json.Marshal(nativePlan{})
	if strings.Contains(string(encoded), "expectedDurationSeconds") {
		t.Fatal("missing duration must remain absent")
	}
	encoded, _ = json.Marshal(nativeDownloadJob{})
	if strings.Contains(string(encoded), "expectedDurationSeconds") {
		t.Fatal("legacy records must remain compatible")
	}
}
