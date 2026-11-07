package core

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"golang.org/x/net/html"
)

var errHongguoProtectedWeb = errors.New("红果受保护网页不能作为整集来源")

func nativeExpectedDuration(media providerMedia) float64 {
	if media.Duration > 0 {
		return media.Duration.Seconds()
	}
	return 0
}

func hongguoPlayerPage(data map[string]any) map[string]any {
	return routerLoaderMap(data, "player_(series_id)/(vid)/page", "player_(series_id)/page", "player_page")
}

func hongguoPublicURL(raw string) (*url.URL, bool) {
	address, err := url.Parse(raw)
	if err != nil || raw == "" {
		return nil, false
	}
	base, _ := url.Parse(hongguoBaseURL)
	address = base.ResolveReference(address)
	if address.Scheme != "https" || address.Host != base.Host || address.User != nil || address.Opaque != "" {
		return nil, false
	}
	return address, true
}

func hongguoPublicPlayerIdentity(raw, seriesID, videoID string, number int) bool {
	address, ok := hongguoPublicURL(raw)
	if !ok || address.RawQuery != "" || address.Fragment != "" {
		return false
	}
	return address.Path == "/player/"+seriesID+"/"+videoID || number == 1 && address.Path == "/player/"+seriesID
}

func hongguoPublicSeriesIdentity(raw, seriesID string) bool {
	address, ok := hongguoPublicURL(raw)
	return ok && address.Path == "/detail" && address.Query().Get("series_id") == seriesID &&
		len(address.Query()) == 1 && address.Fragment == "series"
}

func hongguoPublicSchema(root *html.Node) []map[string]any {
	var objects []map[string]any
	var collect func(any)
	collect = func(value any) {
		switch row := value.(type) {
		case map[string]any:
			objects = append(objects, row)
			if graph, ok := row["@graph"].([]any); ok {
				for _, entry := range graph {
					collect(entry)
				}
			}
		case []any:
			for _, entry := range row {
				collect(entry)
			}
		}
	}
	for _, script := range providerHTMLNodes(root, func(n *html.Node) bool {
		return n.Type == html.ElementNode && n.Data == "script" && providerHTMLAttr(n, "type") == "application/ld+json"
	}) {
		var value any
		var raw strings.Builder
		for child := script.FirstChild; child != nil; child = child.NextSibling {
			if child.Type == html.TextNode {
				raw.WriteString(child.Data)
			}
		}
		decoder := json.NewDecoder(strings.NewReader(raw.String()))
		decoder.UseNumber()
		if decoder.Decode(&value) == nil {
			collect(value)
		}
	}
	return objects
}

func hongguoPublicLocked(root *html.Node, number int) bool {
	classPrefix := func(n *html.Node, prefixes ...string) bool {
		for _, c := range strings.Fields(providerHTMLAttr(n, "class")) {
			for _, prefix := range prefixes {
				if strings.HasPrefix(c, prefix) {
					return true
				}
			}
		}
		return false
	}
	for _, cell := range providerHTMLNodes(root, func(n *html.Node) bool {
		return n.Type == html.ElementNode && classPrefix(n, "pc-episode-item-", "pc-episode-cell-")
	}) {
		labels := providerHTMLNodes(cell, func(n *html.Node) bool { return classPrefix(n, "pc-episode-cell-text-", "pc-episode-text-") })
		matches := false
		for _, label := range labels {
			if strings.TrimSpace(providerHTMLText(label)) == strconv.Itoa(number) {
				matches = true
			}
		}
		if !matches {
			continue
		}
		for _, node := range providerHTMLNodes(cell, func(n *html.Node) bool { return n.Type == html.ElementNode }) {
			hint := providerHTMLAttr(node, "class") + " " + providerHTMLAttr(node, "aria-label") + " " + providerHTMLAttr(node, "title") + " " + providerHTMLAttr(node, "data-state") + " " + providerHTMLAttr(node, "data-status") + " " + providerHTMLAttr(node, "data-lucide")
			if regexp.MustCompile(`(?i)(?:^|[\s_-])lock(?:ed)?(?:$|[\s_-])|锁定|需解锁|已锁`).MatchString(hint) {
				return true
			}
		}
	}
	return false
}

func hongguoPublicWebMedia(body string, page map[string]any, seriesID, videoID string, expectedEpisode ...int) (providerMedia, error) {
	if page["protectedPlayback"] == true {
		return providerMedia{}, fmt.Errorf("%w：公开视频可能仅供试看，请使用平台授权导出的完整素材", errHongguoProtectedWeb)
	}
	fail := func() (providerMedia, error) {
		return providerMedia{}, fmt.Errorf("红果该集没有通过剧集身份、公开状态和网页视频声明核对；未使用其他集或受限媒体")
	}
	seo, _ := page["publicVideoSeo"].(map[string]any)
	if seo["available"] != true || mapString(page, "series_id") != seriesID || mapString(page, "vid") != videoID ||
		mapString(seo, "seriesId") != seriesID || mapString(seo, "itemId") != videoID {
		return fail()
	}
	detail, _ := page["seriesDetail"].(map[string]any)
	if mapString(detail, "series_id") != seriesID {
		return fail()
	}
	number := 0
	for i, value := range anyList(detail["vid_list"]) {
		if strings.TrimSpace(fmt.Sprint(value)) == videoID {
			if number != 0 {
				return fail()
			}
			number = i + 1
		}
	}
	if number == 0 {
		return fail()
	}
	if len(expectedEpisode) > 0 && expectedEpisode[0] > 0 && number != expectedEpisode[0] {
		return fail()
	}
	if raw, ok := detail["accessible_episode_cnt"]; ok {
		limit, err := strconv.Atoi(fmt.Sprint(raw))
		if err != nil || limit < number {
			return fail()
		}
	}
	document, err := html.Parse(strings.NewReader(body))
	if err != nil || hongguoPublicLocked(document, number) {
		return fail()
	}
	declared := map[string]bool{}
	for _, video := range providerHTMLNodes(document, func(n *html.Node) bool { return n.Type == html.ElementNode && n.Data == "video" }) {
		if address, ok := hongguoPublicURL(providerHTMLAttr(video, "src")); ok {
			declared[address.String()] = true
		}
	}
	objects := hongguoPublicSchema(document)
	for _, episode := range objects {
		if mapString(episode, "@type") != "TVEpisode" || mapString(episode, "episodeNumber") != strconv.Itoa(number) ||
			!hongguoPublicPlayerIdentity(mapString(episode, "url"), seriesID, videoID, number) {
			continue
		}
		series, _ := episode["partOfSeries"].(map[string]any)
		if !hongguoPublicSeriesIdentity(mapString(series, "@id"), seriesID) {
			continue
		}
		link, _ := episode["video"].(map[string]any)
		videoRef, episodeRef := mapString(link, "@id"), mapString(episode, "@id")
		if videoRef == "" || episodeRef == "" {
			continue
		}
		for _, object := range objects {
			if mapString(object, "@type") != "VideoObject" || mapString(object, "@id") != videoRef ||
				!hongguoPublicPlayerIdentity(mapString(object, "url"), seriesID, videoID, number) {
				continue
			}
			about, _ := object["about"].(map[string]any)
			if mapString(about, "@id") != episodeRef {
				continue
			}
			address, ok := hongguoPublicURL(mapString(object, "contentUrl"))
			if !ok || address.RawQuery != "" || address.Fragment != "" || !declared[address.String()] ||
				!regexp.MustCompile(`^/video/public/`+regexp.QuoteMeta(videoID)+`/(?:360|480|720|1080)p\.mp4$`).MatchString(address.Path) {
				continue
			}
			duration, err := strconv.ParseFloat(mapString(seo, "durationSeconds"), 64)
			if err != nil || math.IsNaN(duration) || math.IsInf(duration, 0) || duration <= 0 || duration > 24*60*60 {
				return fail()
			}
			return providerMedia{URL: address.String(), Referer: hongguoBaseURL + "/", Duration: time.Duration(duration * float64(time.Second))}, nil
		}
	}
	return fail()
}
