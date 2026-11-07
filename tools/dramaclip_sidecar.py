"""Manju's narrow RPC extension around an unmodified, pinned DramaClip service.

ASR/SRT and final encoding stay in Manju's established workers. DramaClip owns
semantic scoring, cross-episode story selection and original-audio planning.
Transient LLM proxy configuration is memory-only, never settings.update/SQLite.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def install():
    # The pinned upstream commit imports an absent optional TTS module. Fused
    # original-audio mode never synthesizes narration; keep that route disabled
    # with an explicit failure rather than inventing a successful normalization.
    import importlib.util
    import types
    if importlib.util.find_spec('dramaclip.engines.tts.level_fix') is None:
        unavailable = types.ModuleType('dramaclip.engines.tts.level_fix')
        def reject_tts(*_args, **_kwargs):
            raise RuntimeError('本地融合模式保留原声，不提供 DramaClip TTS；上游 level_fix 模块未随源码提供')
        unavailable.normalize_dry_level = reject_tts
        sys.modules[unavailable.__name__] = unavailable
    import dramaclip.service_app as application
    from dramaclip.api import narration_plans
    from dramaclip.engines.analysis.models import AsrSegment, AudioFeatures, SceneInfo
    from dramaclip.engines.semantic import conflict, genre, ranker
    from dramaclip.engines.semantic.llm_client import client_for
    from dramaclip.infra.storage.repos import analysis, episodes, projects
    import threading
    last_angle_error = threading.local()
    original_angles = narration_plans._angle_variants

    def strict_angles(*args, **kwargs):
        try: return original_angles(*args, **kwargs)
        except Exception as exc:
            last_angle_error.value = str(exc)
            raise

    narration_plans._angle_variants = strict_angles

    def refuse_fallback(*_args, **_kwargs):
        raise ValueError('DramaClip 跨集选线失败，已停止；不会以随机或单集规则结果冒充 AI 高光：' +
                         getattr(last_angle_error, 'value', '上游选题未返回合格故事线'))

    narration_plans._deterministic_variants = refuse_fallback

    def build(context, shutdown):
        # Register only the actual fused feature surface. The full upstream
        # router eagerly imports OCR/ASR/TTS/cloud/export extras unrelated to
        # this workflow, even though Manju already supplies those workers.
        from dramaclip import PROTOCOL_VERSION, __version__
        from dramaclip.api import jobs, narration, system
        from dramaclip.transport.rpc import Router
        router = Router()
        system.register(router, service_version=__version__, protocol_version=PROTOCOL_VERSION,
                        shutdown=shutdown, data_dir=context.data_dir)
        jobs.register(router, context)
        narration.register(router, context)

        def configure(params):
            # Never persist even the ephemeral local proxy credential.
            from urllib.parse import urlparse
            base = str(params.get('base_url', ''))
            parsed = urlparse(base)
            if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1':
                raise ValueError('Manju LLM bridge must use loopback HTTP')
            context.settings.update({'llm.base_url': base, 'llm.api_key': str(params['token']),
                                     'llm.model': 'manju-text', 'analysis.ocr_enabled': '0',
                                     'vision.model': '', 'narration.retell_check': '0'})
            return {'ok': True, 'credentialStorage': 'memory-only'}

        def import_project(params):
            rows = params.get('sources')
            if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
                raise ValueError('Expected selected local sources')
            for row in rows:
                path = Path(row['path'])
                stat = path.stat()
                if stat.st_size != row['stat']['bytes'] or stat.st_mtime_ns != row['stat']['mtimeNs']:
                    raise ValueError('源视频已改变：' + path.name)
            prior = projects.get(context.conn, str(params.get('project_id', '')))
            if prior:
                current = episodes.list_by_project(context.conn, str(prior['id']))
                if len(current) != len(rows) or any(ep['source_path'] != row['path'] for ep, row in zip(current, rows)):
                    raise ValueError('Saved DramaClip episode list differs from selected sources')
                return {'project': prior, 'episodes': current}
            project = projects.create(context.conn, str(params['name']), str(Path(rows[0]['path']).parent))
            episodes.replace_all(context.conn, project['id'], [
                {'episode_number': i + 1, 'source_path': row['path'], 'duration': row['duration'],
                 'name': row.get('name', Path(row['path']).stem), 'has_audio': row.get('audio', False)}
                for i, row in enumerate(rows)])
            return {'project': project, 'episodes': episodes.list_by_project(context.conn, project['id'])}

        def analyse_transcript(params):
            episode = episodes.get(context.conn, str(params['episode_id']))
            if episode is None:
                raise ValueError('Episode not found')
            cues = [AsrSegment.model_validate(c) for c in params['cues']]
            duration = float(episode['duration'])
            if not cues or any(c.start < 0 or c.end <= c.start or c.end > duration + .15 for c in cues):
                raise ValueError('Transcription has invalid timestamps')
            # Transcript windows preserve complete utterances. The source of these
            # windows is explicit in the returned report; no visual claim is made.
            scenes = []
            first, end = cues[0].start, cues[0].end
            for cue in cues[1:]:
                if cue.end - first > 10 and end - first >= 2:
                    scenes.append(SceneInfo(start=first, end=end))
                    first = cue.start
                end = max(end, cue.end)
            scenes.append(SceneInfo(start=first, end=end))
            client = client_for(context.settings)
            # Upstream's public semantic pipeline silently falls back to keywords.
            # This fused engine explicitly requires successful model scoring.
            scores = conflict._score_with_llm(cues, scenes, client)
            if len(scores) != len(scenes) or any(not score.reason.strip() for score in scores):
                raise ValueError('DramaClip 冲突模型没有覆盖全部台词窗口或缺少选段理由')
            raw_genre = client.chat_json(genre._SYSTEM_PROMPT, ''.join(c.text for c in cues)[:3000])
            detected = raw_genre.get('genre') if isinstance(raw_genre, dict) else None
            if detected not in genre.GENRES:
                raise ValueError('DramaClip 题材模型未返回有效分类')
            highlights = ranker.rank_highlights(scores, AudioFeatures(), cues)
            eid = str(episode['id'])
            analysis.upsert(context.conn, eid,
                asr_segments=json.dumps([c.model_dump() for c in cues], ensure_ascii=False),
                scene_data=json.dumps([s.model_dump() for s in scenes]), audio_features='{}',
                conflict_scores=json.dumps([s.model_dump() for s in scores], ensure_ascii=False),
                highlights=json.dumps([h.model_dump() for h in highlights], ensure_ascii=False), genre=detected)
            episodes.mark_done(context.conn, eid)
            record = analysis.get(context.conn, eid)
            return {'episode_id': eid, 'analysis_id': record['id'], 'genre': detected,
                    'sceneCount': len(scenes), 'basis': 'timed-transcript-windows'}

        router.register('manju.configure', configure)
        router.register('manju.import', import_project)
        router.register('manju.analyse_transcript', analyse_transcript)
        return router

    application.build_router = build


if __name__ == '__main__':
    source = os.environ.get('MANJU_DRAMACLIP_SOURCE', '')
    if source:
        sys.path.insert(0, source)
    install()
    from dramaclip.__main__ import main
    sys.exit(main())
