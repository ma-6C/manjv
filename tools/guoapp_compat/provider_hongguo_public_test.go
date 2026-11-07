package core

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

func TestHongguoProtectedPageCannotUseLegacyAddress(t *testing.T) {
	body, page := publicHongguoFixture()
	page["protectedPlayback"] = true
	page["video_player_info"] = map[string]any{"main_url": "https://media.example.test/legacy-full.mp4", "duration": 20}
	router, _ := json.Marshal(map[string]any{"loaderData": map[string]any{"player_(series_id)/(vid)/page": page}})
	body += "<script>window._ROUTER_DATA=" + string(router) + "</script>"
	downloader := sourceFixtureDownloader(t, func(request *http.Request) (*http.Response, error) {
		if request.URL.Path != "/player/12345/23456" {
			t.Fatal("unexpected page request", request.URL)
		}
		return sourceFixtureResponse(request, 200, body), nil
	})
	media, err := downloader.resolveHongguoWebMedia(context.Background(), "12345", "23456", 2)
	if err == nil || media.URL != "" || !strings.Contains(err.Error(), "受保护") {
		t.Fatalf("protected page escaped through legacy branch: %+v %v", media, err)
	}
}

func publicHongguoFixture() (string, map[string]any) {
	page := map[string]any{"series_id": "12345", "vid": "23456",
		"publicVideoSeo": map[string]any{"available": true, "seriesId": "12345", "itemId": "23456", "durationSeconds": 20},
		"seriesDetail":   map[string]any{"series_id": "12345", "vid_list": []any{"11111", "23456"}, "accessible_episode_cnt": 2}}
	body := `<video src="/video/public/23456/360p.mp4"></video><script type="application/ld+json">{"@graph":[{"@type":"TVEpisode","@id":"https://hongguoduanju.com/player/12345/23456#episode","url":"https://hongguoduanju.com/player/12345/23456","episodeNumber":2,"partOfSeries":{"@id":"https://hongguoduanju.com/detail?series_id=12345#series"},"video":{"@id":"https://hongguoduanju.com/player/12345/23456#video"}},{"@type":"VideoObject","@id":"https://hongguoduanju.com/player/12345/23456#video","url":"https://hongguoduanju.com/player/12345/23456","contentUrl":"https://hongguoduanju.com/video/public/23456/360p.mp4","about":{"@id":"https://hongguoduanju.com/player/12345/23456#episode"}}]}</script>`
	return body, page
}

func TestHongguoPublicWebRequiresCrossCheckedDeclarations(t *testing.T) {
	body, page := publicHongguoFixture()
	if addresses := hongguoMediaAddresses(nil); len(addresses) != 0 {
		t.Fatal(addresses)
	}
	media, err := hongguoPublicWebMedia(body, page, "12345", "23456", 2)
	if err != nil || media.URL != "https://hongguoduanju.com/video/public/23456/360p.mp4" || media.CENCKey != nil || media.HLSKey != nil || media.Duration.Seconds() != 20 {
		t.Fatalf("%+v %v", media, err)
	}
	for _, name := range []string{"wrong-request-series", "wrong-request-vid", "wrong-task-episode", "protected-preview", "unavailable", "seo-series", "seo-item", "page-series", "page-vid", "missing-index", "duplicate-index", "out-of-web-scope", "missing-video", "different-video", "untrusted-media-host", "wrong-media-id", "wrong-episode", "wrong-series-ref", "wrong-video-ref", "wrong-about", "no-jsonld", "locked"} {
		t.Run(name, func(t *testing.T) {
			raw, p := publicHongguoFixture()
			sid, vid, number := "12345", "23456", 2
			seo := p["publicVideoSeo"].(map[string]any)
			detail := p["seriesDetail"].(map[string]any)
			switch name {
			case "wrong-request-series":
				sid = "34567"
			case "wrong-request-vid":
				vid = "11111"
			case "wrong-task-episode":
				number = 31
			case "protected-preview":
				p["protectedPlayback"] = true
			case "unavailable":
				seo["available"] = false
			case "seo-series":
				seo["seriesId"] = "34567"
			case "seo-item":
				seo["itemId"] = "11111"
			case "page-series":
				p["series_id"] = "34567"
			case "page-vid":
				p["vid"] = "11111"
			case "missing-index":
				detail["vid_list"] = []any{"11111"}
			case "duplicate-index":
				detail["vid_list"] = []any{"23456", "23456"}
			case "out-of-web-scope":
				detail["accessible_episode_cnt"] = 1
			case "missing-video":
				raw = strings.ReplaceAll(raw, `<video src="/video/public/23456/360p.mp4"></video>`, "")
			case "different-video":
				raw = strings.Replace(raw, `src="/video/public/23456/360p.mp4"`, `src="/video/public/11111/360p.mp4"`, 1)
			case "untrusted-media-host":
				raw = strings.ReplaceAll(raw, "/video/public/23456/360p.mp4", "//evil.example/video/public/23456/360p.mp4")
			case "wrong-media-id":
				raw = strings.ReplaceAll(raw, "/video/public/23456/360p.mp4", "/video/public/11111/360p.mp4")
			case "wrong-episode":
				raw = strings.ReplaceAll(raw, `"episodeNumber":2`, `"episodeNumber":1`)
			case "wrong-series-ref":
				raw = strings.ReplaceAll(raw, "series_id=12345#series", "series_id=34567#series")
			case "wrong-video-ref":
				raw = strings.Replace(raw, `"video":{"@id":"https://hongguoduanju.com/player/12345/23456#video"}`, `"video":{"@id":"https://hongguoduanju.com/player/12345/11111#video"}`, 1)
			case "wrong-about":
				raw = strings.Replace(raw, `"about":{"@id":"https://hongguoduanju.com/player/12345/23456#episode"}`, `"about":{"@id":"https://hongguoduanju.com/player/12345/11111#episode"}`, 1)
			case "no-jsonld":
				raw = `<video src="/video/public/23456/360p.mp4"></video>`
			case "locked":
				raw += `<div class="pc-episode-cell-abc"><div class="pc-episode-cell-text-abc">2</div><span aria-label="locked"></span></div>`
			}
			if media, err := hongguoPublicWebMedia(raw, p, sid, vid, number); err == nil {
				t.Fatalf("accepted unverified media: %+v", media)
			}
		})
	}
}

func TestHongguoPublicSavedOfficialSamplesAreProtected(t *testing.T) {
	root := os.Getenv("MANJU_PUBLIC_FIXTURE_ROOT")
	if root == "" {
		t.Skip("official saved sample path not provided")
	}
	vids := []string{"7697855411688311833", "7697855365819419673", "7697855263528733721"}
	for index, vid := range vids {
		name := "hongguo-player.html"
		if index > 0 {
			name = fmt.Sprintf("hongguo-player-%d.html", index+1)
		}
		raw, err := os.ReadFile(filepath.Join(root, name))
		if err != nil {
			t.Fatal(err)
		}
		page := hongguoPlayerPage(parseRouterData(string(raw)))
		if len(page) == 0 || len(hongguoMediaAddresses(nestedMap(page, "video_player_info"))) != 0 {
			t.Fatal("fixture did not reproduce missing native playback data")
		}
		media, err := hongguoPublicWebMedia(string(raw), page, "7697852455970671678", vid, index+1)
		if err == nil || media.URL != "" || !strings.Contains(err.Error(), "受保护") {
			t.Fatalf("protected sample accepted as full episode: %+v %v", media, err)
		}
		if _, err = hongguoPublicWebMedia(string(raw), page, "7697852455970671678", vid, index+2); err == nil {
			t.Fatal("accepted wrong task episode")
		}
		t.Logf("official saved protected sample %d rejected as full episode vid=%s", index+1, vid)
	}
}

func TestHongguoPublicRouteSelectsPageBeforeLayout(t *testing.T) {
	_, page := publicHongguoFixture()
	loader := map[string]any{"player_(series_id)/(vid)/layout": map[string]any{"layoutOnly": true}, "player_(series_id)/(vid)/page": page}
	data := map[string]any{"loaderData": loader}
	raw, _ := json.Marshal(data)
	actual := hongguoPlayerPage(parseRouterData("window._ROUTER_DATA = " + string(raw)))
	if mapString(actual, "vid") != "23456" {
		t.Fatalf("selected layout instead of page: %+v", actual)
	}
}

func TestHongguoPublicCurrentOfficialPages(t *testing.T) {
	root := os.Getenv("MANJU_CURRENT_PUBLIC_FIXTURE_ROOT")
	if root == "" {
		t.Skip("current network samples not supplied")
	}
	files, err := filepath.Glob(filepath.Join(root, "public_*.html"))
	if err != nil || len(files) == 0 {
		t.Fatal("current HTTP samples missing", err)
	}
	for _, file := range files {
		ids := regexp.MustCompile(`public_(\d+)_(\d+)\.html$`).FindStringSubmatch(filepath.Base(file))
		if len(ids) != 3 {
			continue
		}
		raw, err := os.ReadFile(file)
		if err != nil {
			t.Fatal(err)
		}
		page := hongguoPlayerPage(parseRouterData(string(raw)))
		media, err := hongguoPublicWebMedia(string(raw), page, ids[1], ids[2], 1)
		if err == nil || media.URL != "" || !strings.Contains(err.Error(), "受保护") {
			t.Fatalf("current protected preview accepted as full episode: %s %+v %v", file, media, err)
		}
		t.Logf("current official protected HTTP sample rejected as full episode series=%s vid=%s bytes=%d", ids[1], ids[2], len(raw))
	}
}
