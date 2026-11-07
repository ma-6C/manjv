"""Idempotent strict public-web and declared-duration bridge for the pinned core."""
from pathlib import Path
import re


REPLACEMENTS = {
    'provider_hongguo.go': [
        ('if pageErr == nil {\n\t\treturn media, nil\n\t}',
         'if pageErr == nil {\n\t\treturn media, nil\n\t}\n\tif errors.Is(pageErr, errHongguoProtectedWeb) {\n\t\treturn providerMedia{}, pageErr\n\t}'),
        ('d.resolveHongguoWebMedia(ctx, seriesID, videoID)',
         'd.resolveHongguoWebMedia(ctx, seriesID, videoID, chapterEpisodeNumber(task.Chapter, task.Index+1))'),
        ('resolveHongguoWebMedia(ctx context.Context, seriesID, videoID string) (providerMedia, error)',
         'resolveHongguoWebMedia(ctx context.Context, seriesID, videoID string, expectedEpisode ...int) (providerMedia, error)'),
        ('page := routerLoaderMap(parseRouterData(body), "player_", "player_page")',
         'page := hongguoPlayerPage(parseRouterData(body))'),
        ('info, _ := page["video_player_info"].(map[string]any)',
         'if page["protectedPlayback"] == true {\n\t\treturn hongguoPublicWebMedia(body, page, seriesID, videoID, expectedEpisode...)\n\t}\n\tinfo, _ := page["video_player_info"].(map[string]any)'),
        ('return providerMedia{}, fmt.Errorf("红果该集未提供公开播放地址，可能需要登录或 App 授权；不会将试看集冒充该集下载")',
         'return hongguoPublicWebMedia(body, page, seriesID, videoID, expectedEpisode...)'),
    ],
    'app_runtime.go': [
        ('type nativePlan struct {\n',
         'type nativePlan struct {\n\tExpectedDurationSeconds float64 `json:"expectedDurationSeconds,omitempty"`\n'),
    ],
    'app_playback_routes.go': [
        ('\t\toption.Variants = nil\n',
         '\t\tif option.Duration <= 0 {\n\t\t\toption.Duration = media.Duration\n\t\t}\n\t\toption.Variants = nil\n'),
        ('plan := nativePlan{\n',
         'plan := nativePlan{\n\t\tExpectedDurationSeconds: nativeExpectedDuration(media),\n'),
    ],
    'app_downloads.go': [
        ('type nativeDownloadJob struct {\n',
         'type nativeDownloadJob struct {\n\tExpectedDurationSeconds float64 `json:"expectedDurationSeconds,omitempty"`\n'),
        ('type nativeDownloadResult struct {\n',
         'type nativeDownloadResult struct {\n\texpectedDuration float64\n'),
        ('record.File, record.Key, record.ActualQuality = result.file, result.key, result.quality',
         'record.File, record.Key, record.ActualQuality = result.file, result.key, result.quality\n\t\trecord.ExpectedDurationSeconds = result.expectedDuration'),
        ('return nativePlan{URL: path, Key: record.Key, Local: true, Quality: record.ActualQuality,',
         'return nativePlan{URL: path, Key: record.Key, Local: true, Quality: record.ActualQuality, ExpectedDurationSeconds: record.ExpectedDurationSeconds,'),
    ],
    'app_download_transfer.go': [
        ('return nativeDownloadResult{file: entry, key: hex.EncodeToString(media.CENCKey), quality: bundle.quality}, nil',
         'return nativeDownloadResult{file: entry, key: hex.EncodeToString(media.CENCKey), quality: bundle.quality, expectedDuration: nativeExpectedDuration(media)}, nil'),
    ],
}


def apply(native):
    """Validate all anchors before writing; a second application is harmless."""
    native = Path(native)
    updated = {}
    for name, replacements in REPLACEMENTS.items():
        text = (native / name).read_text('utf-8')
        original_text = text
        for old, new in replacements:
            if re.sub(r'\s+', '', new) in re.sub(r'\s+', '', text):
                continue
            if text.count(old) != 1:
                raise ValueError(f'原生公开播放补丁锚点不匹配，请核对固定版本源码：{name}')
            text = text.replace(old, new, 1)
        if text != original_text:
            updated[name] = text
    for name, text in updated.items():
        (native / name).write_text(text, 'utf-8')
    return tuple(updated)
