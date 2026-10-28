package core

import (
	"bytes"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha512"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	hongguoMultiBaseURL     = "https://api5-normal-sinfonlineb.fqnovel.com"
	hongguoMultiPath        = "/novel/player/multi_video_model/v1/"
	hongguoMultiVersionCode = "71332"
	hongguoMultiVersionName = "7.1.3.32"
	hongguoMultiUserAgent   = "com.phoenix.read/71332 (Linux; U; Android 16; zh_CN; 25053RT47C; Build/BP2A.250605.031.A3; Cronet/TTNetVersion:04657795 2026-01-23 QuicVersion:c67e9834 2025-09-08)"
)

var hongguoVodDomains = []string{"qznovelvod.com", "fqnovelvod.com", "douyinvod.com"}

var hongguoAPIDomains = []string{"fqnovel.com", "snssdk.com"}

var hongguoURLConstants = hgUnhexMust(
	"4dd4c2e6b83162090e52b3c7a6733ba41cb2462b829ab58a196b39db57177524" +
		"f49baf7f08e8d68d26a72e37c1a95a2f1f05a51892aef2949732b62a38aadd58")

type hongguoMultiBizParam struct {
	DetailPageVersion      int  `json:"detail_page_version"`
	DeviceLevel            int  `json:"device_level"`
	DisableDiggStat        bool `json:"disable_digg_stat"`
	NeedAllVideoDefinition bool `json:"need_all_video_definition"`
	NeedMP4Align           bool `json:"need_mp4_align"`
	UseOsPlayer            bool `json:"use_os_player"`
	UseServerDNS           bool `json:"use_server_dns"`
	VideoPlatform          int  `json:"video_platform"`
}

type hongguoMultiPayload struct {
	BizParam        hongguoMultiBizParam `json:"biz_param"`
	MixedVideoIDMap map[string][]string  `json:"mixed_video_id_map"`
}

func hongguoPyEncode(raw string) string {
	var out strings.Builder
	for i := 0; i < len(raw); i++ {
		b := raw[i]
		switch {
		case b >= 'A' && b <= 'Z', b >= 'a' && b <= 'z', b >= '0' && b <= '9',
			b == '-', b == '_', b == '.', b == '~':
			out.WriteByte(b)
		default:
			const hexDigits = "0123456789ABCDEF"
			out.WriteByte('%')
			out.WriteByte(hexDigits[b>>4])
			out.WriteByte(hexDigits[b&0x0f])
		}
	}
	return out.String()
}

func hongguoPlayerLocalID() string {
	raw := make([]byte, 6)
	if _, err := rand.Read(raw); err != nil {
		panic("hongguo: local id")
	}
	value := uint64(0)
	for _, b := range raw {
		value = value<<8 | uint64(b)
	}
	return strconv.FormatUint(1_000_000_000_000_000+value, 10)
}

func hongguoDeviceQuery(khronos int64, rticket int64, iid, deviceID string) string {
	fields := [][2]string{
		{"ac", "wifi"},
		{"channel", "update_64"},
		{"aid", "8662"},
		{"app_name", "novelread"},
		{"version_code", hongguoMultiVersionCode},
		{"version_name", hongguoMultiVersionName},
		{"device_platform", "android"},
		{"os", "android"},
		{"ssmix", "a"},
		{"device_type", "25053RT47C"},
		{"device_brand", "Redmi"},
		{"language", "zh"},
		{"os_api", "36"},
		{"os_version", "16"},
		{"manifest_version_code", hongguoMultiVersionCode},
		{"resolution", "1280*2772"},
		{"dpi", "520"},
		{"update_version_code", hongguoMultiVersionCode},
		{"host_abi", "arm64-v8a"},
		{"dragon_device_type", "phone"},
		{"pv_player", hongguoMultiVersionCode},
		{"compliance_status", "0"},
		{"need_personal_recommend", "1"},
		{"player_so_load", "1"},
		{"is_android_pad_screen", "0"},
		{"iid", iid},
		{"device_id", deviceID},
		{"ts", strconv.FormatInt(khronos, 10)},
		{"_rticket", strconv.FormatInt(rticket, 10)},
	}
	var parts []string
	for _, field := range fields {
		parts = append(parts, hongguoPyEncode(field[0])+"="+hongguoPyEncode(field[1]))
	}
	return strings.Join(parts, "&")
}

func (downloader *Downloader) hongguoPlayerPost(ctx context.Context, videoID string) (map[string]any, error) {
	payload := hongguoMultiPayload{
		BizParam: hongguoMultiBizParam{
			DetailPageVersion:      0,
			DeviceLevel:            3,
			DisableDiggStat:        false,
			NeedAllVideoDefinition: true,
			NeedMP4Align:           false,
			UseOsPlayer:            false,
			UseServerDNS:           false,
			VideoPlatform:          1024,
		},
		MixedVideoIDMap: map[string][]string{"1004": {videoID}},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	khronos := time.Now().Unix()
	iid, deviceID := hongguoPlayerLocalID(), hongguoPlayerLocalID()

	var query string
	var ticket int64
	ticketBase := time.Now().UnixMilli()
	for offset := int64(0); offset < 32; offset++ {
		ticket = ticketBase + offset
		query = hongguoDeviceQuery(khronos, ticket, iid, deviceID)
		if hgBranchOf(query, body, uint32(khronos)) != 1 {
			break
		}
	}
	fullURL := hongguoMultiBaseURL + hongguoMultiPath + "?" + query

	request, err := http.NewRequestWithContext(ctx, http.MethodPost, fullURL, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("User-Agent", hongguoMultiUserAgent)
	request.Header.Set("Accept", "application/json; charset=utf-8,application/x-protobuf")
	request.Header.Set("Content-Type", "application/json; charset=UTF-8")
	request.Header.Set("x-xs-from-web", "0")
	request.Header.Set("x-ss-req-ticket", strconv.FormatInt(ticket, 10))
	request.Header.Set("x-tt-request-tag", "t=0;n=0")
	request.Header.Set("sdk-version", "2")
	request.Header.Set("passport-sdk-version", "50561")
	request.Header.Set("x-vc-bdturing-sdk-version", "3.7.2.cn")
	request.Header.Set("x-ss-stub", hgMd5HexUpper(body))
	request.Header.Set("x-tt-dt", "")
	for key, value := range hongguoPureSign(fullURL, body, uint32(khronos)) {
		request.Header.Set(key, value)
	}

	response, err := downloader.doPreparedCatalogRequest(request, 20*time.Second, nil)
	if err != nil {
		return nil, err
	}
	content, readErr := io.ReadAll(io.LimitReader(response.Body, providerMaxBodyBytes+1))
	response.Body.Close()
	if readErr != nil {
		return nil, readErr
	}
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("红果 App 接口 HTTP %d", response.StatusCode)
	}
	if len(content) > providerMaxBodyBytes {
		return nil, errors.New("红果 App 接口响应过大")
	}
	if len(content) == 0 {
		return nil, errors.New("红果 App 接口未返回有效数据")
	}
	var result map[string]any
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.UseNumber()
	if err := decoder.Decode(&result); err != nil {
		return nil, errors.New("红果 App 接口返回格式异常")
	}
	if code := firstNonEmpty(mapString(result, "code", "Code", "status_code"), mapString(nestedMap(result, "BaseResp"), "StatusCode")); code != "" && code != "0" {
		message := firstNonEmpty(mapString(result, "message", "msg"), mapString(nestedMap(result, "BaseResp"), "StatusMessage"))
		if message != "" {
			return nil, fmt.Errorf("红果 App 接口暂不可用（%s）：%s", truncate(code, 20), truncate(message, 120))
		}
		return nil, fmt.Errorf("红果 App 接口暂不可用（%s）", truncate(code, 20))
	}
	data := nestedMap(result, "data")
	entry := nestedMap(data, videoID)
	if len(entry) == 0 {
		return nil, errors.New("红果 App 接口未返回所选分集")
	}
	return entry, nil
}

func (downloader *Downloader) hongguoPlayerFollowFallback(ctx context.Context, fallback string) (map[string]any, error) {
	fallback = hongguoCleanMediaURL(fallback)
	if !hongguoCheckedURL(fallback, hongguoAPIDomains) {
		return nil, errors.New("红果 App 片源地址不在允许的域名")
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, fallback, nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("User-Agent", hongguoMultiUserAgent)
	response, err := downloader.doPreparedCatalogRequest(request, 20*time.Second, nil)
	if err != nil {
		return nil, err
	}
	content, readErr := io.ReadAll(io.LimitReader(response.Body, providerMaxBodyBytes+1))
	response.Body.Close()
	if readErr != nil {
		return nil, readErr
	}
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("红果 App 片源接口 HTTP %d", response.StatusCode)
	}
	if len(content) == 0 || len(content) > providerMaxBodyBytes {
		return nil, errors.New("红果 App 片源接口未返回有效数据")
	}
	var result map[string]any
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.UseNumber()
	if err := decoder.Decode(&result); err != nil {
		return nil, errors.New("红果 App 片源接口返回格式异常")
	}
	videoInfo := nestedMap(result, "video_info")
	info := nestedMap(videoInfo, "data")
	if len(info) == 0 {
		return nil, errors.New("红果 App 片源接口未返回片源模型")
	}
	return info, nil
}

func hongguoCleanMediaURL(value string) string {
	value = strings.ReplaceAll(value, `\/`, `/`)
	value = strings.ReplaceAll(value, `\u0026`, `&`)
	value = strings.ReplaceAll(value, `&amp;`, `&`)
	return value
}

func hongguoCheckedURL(value string, domains []string) bool {
	parsed, err := url.Parse(value)
	if err != nil {
		return false
	}
	if parsed.Scheme != "https" || parsed.User != nil {
		return false
	}
	if port := parsed.Port(); port != "" && port != "443" {
		return false
	}
	host := strings.ToLower(parsed.Hostname())
	for _, domain := range domains {
		if host == domain || strings.HasSuffix(host, "."+domain) {
			return true
		}
	}
	return false
}

func hongguoDecryptSpadeURL(value string, seed []byte) (string, error) {
	raw, err := decodeHongguoBase64(value)
	if err != nil {
		return "", err
	}
	if len(raw) < 5 {
		return "", errors.New("红果媒体地址密文过短")
	}
	if raw[0] != 0xa8 || raw[2] != 0x01 || raw[3] != 0x00 {
		return "", errors.New("红果媒体地址密文头格式错误")
	}
	cipherLength := len(raw) - 4
	if cipherLength == 0 || cipherLength%16 != 0 {
		return "", errors.New("红果媒体地址密文无完整块")
	}
	h1 := sha512.Sum512(seed)
	h2 := sha512.Sum512(append(h1[:], hongguoURLConstants...))
	block, err := aes.NewCipher(h2[:16])
	if err != nil {
		return "", err
	}
	plain := make([]byte, cipherLength)
	cipher.NewCBCDecrypter(block, h2[16:32]).CryptBlocks(plain, raw[4:4+cipherLength])
	end := len(plain)
	if end > 0 {
		pad := int(plain[end-1])
		if pad >= 1 && pad <= 16 && pad <= end {
			end -= pad
		}
	}
	for end > 0 && plain[end-1] == 0 {
		end--
	}
	return string(plain[:end]), nil
}

type hongguoFallbackRow struct {
	item      map[string]any
	codecRank int
	quality   string
	pixels    int
	shortSide int
	size      int64
}

func hongguoCodecRank(codec string) int {
	switch codec {
	case "h264", "avc", "avc1":
		return 0
	case "hevc", "h265", "hvc1", "hev1", "bytevc1":
		return 1
	}
	return 2
}

func hongguoQualityPixels(value string) int {
	digits := ""
	for i := 0; i < len(value); i++ {
		if value[i] >= '0' && value[i] <= '9' {
			digits += string(value[i])
		} else if digits != "" {
			break
		}
	}
	if digits == "" {
		return 0
	}
	number, err := strconv.Atoi(digits)
	if err != nil {
		return 0
	}
	return number
}

func hongguoFallbackRows(videoList map[string]any) []hongguoFallbackRow {
	var rows []hongguoFallbackRow
	for _, value := range videoList {
		item, ok := value.(map[string]any)
		if !ok || len(item) == 0 {
			continue
		}
		meta := nestedMap(item, "video_meta")
		codec := strings.ToLower(firstNonEmpty(mapString(item, "codec_type"), mapString(meta, "codec_type")))
		quality := firstNonEmpty(
			mapString(item, "quality_desc"),
			mapString(item, "definition"),
			mapString(item, "height"),
			mapString(item, "vheight"),
			mapString(meta, "definition"),
		)
		width, height := 0, 0
		for _, pair := range [4][2]string{
			{"vwidth", "vheight"},
			{"width", "height"},
		} {
			if w, _ := strconv.Atoi(mapString(item, pair[0])); w > 0 {
				if h, _ := strconv.Atoi(mapString(item, pair[1])); h > 0 {
					width, height = w, h
					break
				}
			}
		}
		if width == 0 || height == 0 {
			for _, pair := range [4][2]string{
				{"vwidth", "vheight"},
				{"width", "height"},
			} {
				if w, _ := strconv.Atoi(mapString(meta, pair[0])); w > 0 {
					if h, _ := strconv.Atoi(mapString(meta, pair[1])); h > 0 {
						width, height = w, h
						break
					}
				}
			}
		}
		size, _ := strconv.ParseInt(mapString(meta, "size"), 10, 64)
		if size == 0 {
			size, _ = strconv.ParseInt(mapString(item, "size"), 10, 64)
		}
		shortSide := width
		if height < shortSide {
			shortSide = height
		}
		rows = append(rows, hongguoFallbackRow{
			item: item, codecRank: hongguoCodecRank(codec), quality: quality,
			pixels: hongguoQualityPixels(quality), shortSide: shortSide, size: size,
		})
	}
	sort.SliceStable(rows, func(i, j int) bool {
		if rows[i].codecRank != rows[j].codecRank {
			return rows[i].codecRank < rows[j].codecRank
		}
		return rows[i].pixels > rows[j].pixels
	})
	return rows
}

func hongguoMediaURLCandidates(item map[string]any) []string {
	var out []string
	add := func(value any) {
		if address, ok := value.(string); ok {
			if address = strings.TrimSpace(address); address != "" {
				out = append(out, address)
			}
		}
	}
	add(item["main_url"])
	add(item["backup_url"])
	if list, ok := item["backup_url_list"].([]any); ok {
		for _, value := range list {
			add(value)
		}
	}
	return out
}

func selectHongguoFallbackMedia(info map[string]any) (providerMedia, error) {
	videoList, ok := info["video_list"].(map[string]any)
	if !ok || len(videoList) == 0 {
		return providerMedia{}, errors.New("红果 App 片源接口未返回播放列表")
	}
	var seed []byte
	if encoded := mapString(info, "key_seed"); encoded != "" {
		decoded, err := decodeHongguoBase64(encoded)
		if err != nil {
			return providerMedia{}, errors.New("红果媒体地址密钥无效")
		}
		seed = decoded
	}
	var keyErr error
	var choices []providerMedia
	seen := map[string]bool{}
	duration, _ := strconv.ParseFloat(mapString(info, "video_duration", "duration"), 64)
	rows := hongguoFallbackRows(videoList)
	for _, row := range rows {
		if row.codecRank >= 2 {
			continue
		}
		spade := firstNonEmpty(mapString(row.item, "spade_a"), mapString(nestedMap(row.item, "encrypt_info"), "spade_a"))
		var cencKey []byte
		if spade != "" {
			key, err := hongguoContentKey(spade)
			if err != nil {
				keyErr = err
				continue
			}
			cencKey = key
		}
		for _, candidate := range hongguoMediaURLCandidates(row.item) {
			media := hongguoCleanMediaURL(candidate)
			if seed != nil && !isProviderHTTPMediaURL(media) {
				decrypted, err := hongguoDecryptSpadeURL(media, seed)
				if err != nil {
					continue
				}
				media = hongguoCleanMediaURL(decrypted)
			}
			if !hongguoCheckedURL(media, hongguoVodDomains) || seen[media] {
				continue
			}
			quality := row.shortSide
			if pixels := hongguoQualityPixels(row.quality); pixels > 0 {
				quality = pixels
			}
			seen[media] = true
			choices = append(choices, providerMedia{
				URL:      media,
				CENCKey:  cencKey,
				Quality:  quality,
				Referer:  "https://novel.snssdk.com/",
				Duration: time.Duration(duration * float64(time.Second)),
			})
		}
	}
	if len(choices) > 0 {
		selected := choices[0]
		selected.Variants = choices
		return selected, nil
	}
	if keyErr != nil {
		return providerMedia{}, fmt.Errorf("红果 App 媒体密钥不可用: %w", keyErr)
	}
	return providerMedia{}, errors.New("红果 App 未返回兼容的媒体，已跳过不支持的编码")
}

func (downloader *Downloader) resolveHongguoAppMedia(ctx context.Context, videoID string) (providerMedia, error) {
	if !hongguoNumericID.MatchString(videoID) {
		return providerMedia{}, errors.New("红果视频 ID 无效")
	}
	entry, err := downloader.hongguoPlayerPost(ctx, videoID)
	if err != nil {
		return providerMedia{}, err
	}
	model, err := hongguoVideoModel(entry)
	if err != nil {
		return providerMedia{}, err
	}
	if hongguoHasVideoList(model["video_list"]) {
		return selectHongguoAppMedia(model)
	}
	fallback := hongguoParseFallback(model["fallback_api"])
	if fallback == "" {
		return providerMedia{}, errors.New("红果 App 接口未返回本集片源地址")
	}
	info, err := downloader.hongguoPlayerFollowFallback(ctx, fallback)
	if err != nil {
		return providerMedia{}, err
	}
	if reported := mapString(info, "vid", "video_id"); reported != "" && reported != videoID {
		return providerMedia{}, errors.New("红果 App 片源接口返回了其他分集")
	}
	return selectHongguoFallbackMedia(info)
}

func hongguoParseFallback(value any) string {
	for depth := 0; depth < 5; depth++ {
		switch typed := value.(type) {
		case string:
			text := strings.TrimSpace(typed)
			if strings.HasPrefix(text, "{") || strings.HasPrefix(text, "[") {
				var parsed any
				if json.Unmarshal([]byte(text), &parsed) != nil {
					return ""
				}
				value = parsed
				continue
			}
			return text
		case []any:
			if len(typed) == 0 {
				return ""
			}
			value = typed[0]
		case map[string]any:
			value = typed["fallback_api"]
		default:
			return ""
		}
	}
	return ""
}
