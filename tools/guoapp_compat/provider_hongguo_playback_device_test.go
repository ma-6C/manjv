package core

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha512"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestHongguoPlaybackRegistrationEnvelope(t *testing.T) {
	body, err := hongguoPlaybackRegisterBody(1793199000123)
	if err != nil || len(body) < 54 || !bytes.Equal(body[:6], []byte{0x74, 0x63, 5, 16, 0, 0}) {
		t.Fatalf("invalid registration envelope: %v", err)
	}
	seed := sha512.Sum512(body[6:38])
	derived := sha512.Sum512(append(seed[:], hongguoURLConstants...))
	block, _ := aes.NewCipher(derived[:16])
	plain := append([]byte(nil), body[38:]...)
	cipher.NewCBCDecrypter(block, derived[16:32]).CryptBlocks(plain, plain)
	pad := int(plain[len(plain)-1])
	plain = plain[:len(plain)-pad]
	digest := sha512.Sum512(plain[64:])
	if !bytes.Equal(digest[:], plain[:64]) {
		t.Fatal("registration compression digest mismatch")
	}
	reader, err := gzip.NewReader(bytes.NewReader(plain[64:]))
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	var payload map[string]any
	if err := json.NewDecoder(reader).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	header := nestedMap(payload, "header")
	if mapString(header, "version_code") != "73932" || mapString(header, "app_version") != "7.3.9.32" || mapString(payload, "magic_tag") != "ss_app_log" {
		t.Fatal("registration identity/version mismatch")
	}
}

func TestHongguoPlaybackRegisteredIdentityReused(t *testing.T) {
	var registrations, playback atomic.Int32
	d := rankingTestDownloader(t, func(request *http.Request) (*http.Response, error) {
		if strings.Contains(request.URL.Path, "device_register") {
			registrations.Add(1)
			if request.Header.Get("User-Agent") != hongguoPlaybackRegisterUA || request.Header.Get("X-Ss-Stub") == "" {
				t.Error("registration headers missing")
			}
			return rankingHTTPResponse(request, 200, `{"device_id_str":"7611111111111111111","install_id_str":"7622222222222222222"}`), nil
		}
		playback.Add(1)
		if request.URL.Query().Get("device_id") != "7611111111111111111" || request.URL.Query().Get("iid") != "7622222222222222222" {
			t.Error("registered identity not used")
		}
		for _, key := range []string{"X-Argus", "X-Medusa", "X-Gorgon", "X-Khronos", "X-Ladon", "X-Helios"} {
			if request.Header.Get(key) == "" {
				t.Error("playback signature missing")
			}
		}
		if request.Header.Get("User-Agent") != hongguoPlaybackUA || request.URL.Query().Get("ts") == "" {
			t.Error("playback request identity mismatch")
		}
		_, _ = io.Copy(io.Discard, request.Body)
		return rankingHTTPResponse(request, 200, `{"code":0,"data":{"7690936226991311897":{"video_model":{"video_list":[{"main_url":"https://test.qznovelvod.com/video.mp4","video_meta":{"codec_type":"h264","vwidth":720,"vheight":1280}}]}}}}`), nil
	})
	for i := 0; i < 2; i++ {
		media, err := d.resolveHongguoAppMedia(context.Background(), "7690936226991311897")
		if err != nil || media.URL != "https://test.qznovelvod.com/video.mp4" || media.Quality != 720 {
			t.Fatalf("inline media failed: %+v %v", media, err)
		}
	}
	if registrations.Load() != 1 || playback.Load() != 2 {
		t.Fatal("registered identity was not reused")
	}
}

func TestHongguoPlaybackRegistrationFailureCooldown(t *testing.T) {
	var calls atomic.Int32
	d := rankingTestDownloader(t, func(request *http.Request) (*http.Response, error) {
		if calls.Add(1) == 1 {
			return rankingHTTPResponse(request, 200, `{"device_id":0,"install_id":0}`), nil
		}
		return rankingHTTPResponse(request, 200, `{"device_id_str":"7611111111111111111","install_id_str":"7622222222222222222"}`), nil
	})
	for i := 0; i < 2; i++ {
		if _, err := d.hongguoPlaybackDevice(context.Background()); err == nil {
			t.Fatal("invalid registration accepted")
		}
	}
	if calls.Load() != 1 {
		t.Fatal("registration failure caused repeated network calls")
	}
	d.hongguoClient().playback.retryAfter = time.Now().Add(-time.Second)
	if _, err := d.hongguoPlaybackDevice(context.Background()); err != nil || calls.Load() != 2 {
		t.Fatal("registration did not recover after cooldown", err)
	}
}
