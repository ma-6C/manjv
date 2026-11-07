package core

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"testing"
)

func TestHongguoSignedOfficialHostFallback(t *testing.T) {
	hosts := []string{}
	registrations := 0
	d := rankingTestDownloader(t, func(r *http.Request) (*http.Response, error) {
		if strings.Contains(r.URL.Path, "device_register") {
			registrations++
			return rankingHTTPResponse(r, 200, fmt.Sprintf(`{"device_id_str":"761111111111111111%d","install_id_str":"762222222222222222%d"}`, registrations, registrations)), nil
		}
		hosts = append(hosts, r.URL.Hostname())
		if r.URL.Query().Get("device_id") != fmt.Sprintf("761111111111111111%d", len(hosts)) {
			t.Error("refreshed identity missing on failover")
		}
		if r.Header.Get("X-Medusa") == "" {
			t.Error("signature missing on failover")
		}
		if len(hosts) == 1 {
			return rankingHTTPResponse(r, 200, ""), nil
		}
		return rankingHTTPResponse(r, 200, `{"code":0,"data":{"7690936226991311897":{"video_model":{"video_list":[]}}}}`), nil
	})
	if _, err := d.hongguoPlayerPost(context.Background(), "7690936226991311897"); err != nil {
		t.Fatal(err)
	}
	if registrations != 2 || len(hosts) != 2 || hosts[0] != "api5-normal-sinfonlineb.fqnovel.com" || hosts[1] != "api5-normal-hl.fqnovel.com" {
		t.Fatal("unexpected failover", hosts)
	}
}

func TestHongguoSignedDoesNotRetryAccessOrRateLimit(t *testing.T) {
	for _, status := range []int{http.StatusForbidden, http.StatusTooManyRequests} {
		calls := 0
		d := rankingTestDownloader(t, func(r *http.Request) (*http.Response, error) {
			if strings.Contains(r.URL.Path, "device_register") {
				return rankingHTTPResponse(r, 200, `{"device_id_str":"7611111111111111111","install_id_str":"7622222222222222222"}`), nil
			}
			calls++
			return rankingHTTPResponse(r, status, ""), nil
		})
		if _, err := d.hongguoPlayerPost(context.Background(), "7690936226991311897"); err == nil || calls != 1 {
			t.Fatalf("status %d calls=%d error=%v", status, calls, err)
		}
	}
}
