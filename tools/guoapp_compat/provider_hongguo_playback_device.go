package core

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/md5"
	"crypto/rand"
	"crypto/sha512"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"sync"
	"time"
)

const hongguoPlaybackRegisterURL = "https://log5-applog-lf.fqnovel.com/service/2/device_register/?tt_data=a&cronet_version=8d40f833_2026-03-03&ttnet_version=4.2.243.31-douyin&use_store_region_cookie=1"
const hongguoPlaybackRegisterUA = "com.phoenix.read/73932 (Linux; U; Android 16; zh_CN; 25053RT47C; Build/BP2A.250605.031.A3)"
const hongguoPlaybackUA = "com.phoenix.read/71532 (Linux; U; Android 9; SM-N9860; Build/PQ3A.190705.10241111;tt-ok/3.12.13.20)"

type hongguoPlaybackIdentity struct {
	deviceID string
	iid      string
}

type hongguoPlaybackRegistration struct {
	mu         sync.Mutex
	identity   hongguoPlaybackIdentity
	retryAfter time.Time
}

func hongguoPlaybackRegisterBody(now int64) ([]byte, error) {
	header := map[string]any{
		"display_name": "红果免费短剧", "update_version_code": 73932, "manifest_version_code": 73932,
		"app_version_minor": "7.3.9.32", "aid": 8662, "channel": "update_64", "package": "com.phoenix.read",
		"app_version": "7.3.9.32", "version_code": 73932, "sdk_version": "3.7.0-rc.34-fanqie-xiaoshuo",
		"sdk_target_version": 29, "git_hash": "3a88f4e", "os": "Android", "os_version": "16", "os_api": 36,
		"device_model": "25053RT47C", "device_brand": "Redmi", "device_manufacturer": "Redmi",
		"cpu_abi": "arm64-v8a", "release_build": "b5e187f", "density_dpi": 520, "display_density": "mdpi",
		"resolution": "1280x2772", "language": "zh", "timezone": 8, "access": "wifi", "not_request_sender": 0,
		"carrier": "CHINA MOBILE", "mcc_mnc": "46000", "rom": "eng.root.20231116.160340",
		"rom_version": "W528JS release-keys", "cdid": uuidLike(),
		"sig_hash": "56a962410c494bbaf0b58dba20cae56f", "openudid": randomHex(8),
		"clientudid": uuidLike(), "ipv6_list": []string{}, "region": "CN", "tz_name": "Asia/Shanghai",
		"tz_offset": 28800, "sim_region": "cn", "sim_serial_number": []string{}, "oaid_may_support": false,
		"req_id": uuidLike(), "device_platform": "android", "pre_installed_channel": "",
		"apk_first_install_time": now, "is_system_app": 0, "sdk_flavor": "china", "guest_mode": 0,
		"custom": map[string]any{"account_region_src": "fallback", "account_region": "cn", "host_bit": 64, "dragon_device_type": "phone"},
	}
	payload, err := json.Marshal(map[string]any{"magic_tag": "ss_app_log", "header": header, "_gen_time": now})
	if err != nil {
		return nil, err
	}
	var compressed bytes.Buffer
	zipper := gzip.NewWriter(&compressed)
	if _, err := zipper.Write(payload); err != nil {
		return nil, err
	}
	if err := zipper.Close(); err != nil {
		return nil, err
	}
	random := make([]byte, 32)
	if _, err := rand.Read(random); err != nil {
		return nil, err
	}
	seed := sha512.Sum512(random)
	derived := sha512.Sum512(append(seed[:], hongguoURLConstants...))
	block, err := aes.NewCipher(derived[:16])
	if err != nil {
		return nil, err
	}
	digest := sha512.Sum512(compressed.Bytes())
	plain := hongguoCommentPad(append(digest[:], compressed.Bytes()...))
	cipher.NewCBCEncrypter(block, derived[16:32]).CryptBlocks(plain, plain)
	return append(append([]byte{0x74, 0x63, 0x05, 0x10, 0, 0}, random...), plain...), nil
}

func (downloader *Downloader) hongguoPlaybackDevice(ctx context.Context) (hongguoPlaybackIdentity, error) {
	state := &downloader.hongguoClient().playback
	state.mu.Lock()
	defer state.mu.Unlock()
	if err := ctx.Err(); err != nil {
		return hongguoPlaybackIdentity{}, err
	}
	if state.identity.deviceID != "" && state.identity.iid != "" {
		return state.identity, nil
	}
	if time.Now().Before(state.retryAfter) {
		return hongguoPlaybackIdentity{}, errors.New("匿名播放设备注册暂不可用，请一分钟后重试")
	}
	identity, err := downloader.registerHongguoPlaybackDevice(ctx)
	if err != nil {
		if ctx.Err() == nil {
			state.retryAfter = time.Now().Add(time.Minute)
		}
		return hongguoPlaybackIdentity{}, err
	}
	state.identity = identity
	state.retryAfter = time.Time{}
	return identity, nil
}

func (downloader *Downloader) registerHongguoPlaybackDevice(ctx context.Context) (hongguoPlaybackIdentity, error) {
	now := time.Now().UnixMilli()
	body, err := hongguoPlaybackRegisterBody(now)
	if err != nil {
		return hongguoPlaybackIdentity{}, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, hongguoPlaybackRegisterURL, bytes.NewReader(body))
	if err != nil {
		return hongguoPlaybackIdentity{}, err
	}
	request.Header.Set("User-Agent", hongguoPlaybackRegisterUA)
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Content-Type", "application/octet-stream;tt-data=a")
	request.Header.Set("log-encode-type", "gzip")
	request.Header.Set("x-ss-dp", "8662")
	request.Header.Set("x-ss-req-ticket", strconv.FormatInt(now, 10))
	request.Header.Set("x-vc-bdturing-sdk-version", "4.0.3.cn")
	request.Header.Set("lc", "101")
	request.Header.Set("sdk-version", "2")
	request.Header.Set("passport-sdk-version", "5051452")
	request.Header.Set("x-neptune", "-8|50:51:59:30:40:47:49:39")
	request.Header.Set("x-ss-stub", fmt.Sprintf("%X", md5.Sum(body)))
	response, err := downloader.doPreparedCatalogRequest(request, 8*time.Second, nil)
	if err != nil {
		return hongguoPlaybackIdentity{}, fmt.Errorf("匿名播放设备注册失败：%w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return hongguoPlaybackIdentity{}, fmt.Errorf("匿名播放设备注册 HTTP %d", response.StatusCode)
	}
	if response.Request != nil && response.Request.URL.Hostname() != request.URL.Hostname() {
		return hongguoPlaybackIdentity{}, errors.New("匿名播放设备注册地址发生变化")
	}
	content, err := io.ReadAll(io.LimitReader(response.Body, (64<<10)+1))
	if err != nil || len(content) == 0 || len(content) > 64<<10 {
		return hongguoPlaybackIdentity{}, errors.New("匿名播放设备注册响应无效")
	}
	var result map[string]any
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.UseNumber()
	if decoder.Decode(&result) != nil {
		return hongguoPlaybackIdentity{}, errors.New("匿名播放设备注册格式异常")
	}
	code := mapString(result, "code", "Code")
	device := mapString(result, "device_id_str", "device_id")
	iid := mapString(result, "install_id_str", "install_id")
	if code != "" && code != "0" || !hongguoNumericID.MatchString(device) || !hongguoNumericID.MatchString(iid) || device == "0" || iid == "0" {
		return hongguoPlaybackIdentity{}, errors.New("匿名播放设备注册未返回有效身份")
	}
	return hongguoPlaybackIdentity{deviceID: device, iid: iid}, nil
}
