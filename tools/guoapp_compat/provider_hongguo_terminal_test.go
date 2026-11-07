package core

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"testing"
)

func TestHongguoProtectedWebIsTerminalAcrossLegacyFallbacks(t *testing.T) {
	body, page := publicHongguoFixture()
	page["protectedPlayback"] = true
	page["video_player_info"] = map[string]any{"main_url": "https://media.example.test/legacy.mp4", "duration": 20}
	router, _ := json.Marshal(map[string]any{"loaderData": map[string]any{"player_(series_id)/(vid)/page": page}})
	body += "<script>window._ROUTER_DATA=" + string(router) + "</script>"
	webHits, backupHits := 0, 0
	downloader := sourceFixtureDownloader(t, func(request *http.Request) (*http.Response, error) {
		if request.URL.Hostname() == "hongguoduanju.com" {
			webHits++
			return sourceFixtureResponse(request, 200, body), nil
		}
		if request.URL.Hostname() == "djapi.999888456.xyz" {
			backupHits++
			return sourceFixtureResponse(request, 200, `{}`), nil
		}
		return sourceFixtureResponse(request, 200, `{}`), nil
	})
	media, err := downloader.resolveHongguoMedia(context.Background(), Task{DramaID: "hongguo:12345", Chapter: Chapter{VideoURL: "hongguo-cenc://23456", CurrentEpisode: rawEpisode(2)}})
	if !errors.Is(err, errHongguoProtectedWeb) || media.URL != "" || webHits != 1 || backupHits != 0 {
		t.Fatalf("protected decision was not terminal: media=%+v err=%v web=%d backup=%d", media, err, webHits, backupHits)
	}
	if !strings.Contains(err.Error(), "受保护") {
		t.Fatal("missing public diagnostic")
	}
}
