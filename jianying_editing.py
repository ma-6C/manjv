"""Measured audio spans, local material selection, and real editable effects."""
from pathlib import Path
import array
import hashlib
import math
import os
import sys
import wave
import uuid


PROFILES={
    'clean':{'scale':1.02,'contrast':.02,'saturation':.02,'brightness':.005},
    'cinema':{'scale':1.035,'contrast':.06,'saturation':-.025,'brightness':-.01},
    'energetic':{'scale':1.05,'contrast':.045,'saturation':.05,'brightness':.01},
}
AUDIO_EXT={'.mp3','.wav','.m4a','.aac','.flac','.ogg','.opus','.wma'}
MOODS={'tense':('紧张','悬疑','追逐','战斗','危机','tense','battle','suspense'),
       'warm':('温馨','治愈','温暖','甜蜜','warm','love','gentle'),
       'sad':('悲伤','离别','伤感','sad','piano'),
       'bright':('欢快','轻松','搞笑','快乐','bright','happy')}


def library_files(root):
    if not root:return []
    base=Path(root).expanduser().resolve()
    if not base.is_dir():raise ValueError('本地音乐或音效素材库不存在')
    result=[]
    def ordinary(path):
        st=path.lstat()
        return not path.is_symlink() and not getattr(st,'st_file_attributes',0)&0x400
    for directory,dirs,files in os.walk(base,followlinks=False):
        current=Path(directory)
        dirs[:]=sorted(d for d in dirs if ordinary(current/d))
        if len(current.relative_to(base).parts)>=5:dirs.clear()
        for name in sorted(files):
            path=current/name
            if path.suffix.lower() in AUDIO_EXT and ordinary(path) and path.stat().st_size>0:result.append(path)
            if len(result)>3000:raise ValueError('音频素材库超过3000个文件，请选择更小的子目录')
    return result


def select_materials(files,name,mood,count=1):
    if not files:return []
    if mood=='auto':mood=next((k for k,words in MOODS.items() if any(w in name.lower() for w in words)),'bright')
    words=MOODS.get(mood,())
    def rank(path):
        return (-sum(w in str(path).lower() for w in words),hashlib.sha256((name+str(path)).encode()).hexdigest())
    return sorted(files,key=rank)[:count]


def activity(path,event):
    """20ms RMS windows with hangover, in source microseconds; no speech labels."""
    values=[]
    with wave.open(str(path),'rb') as src:
        if src.getsampwidth()!=2:return []
        rate=src.getframerate();channels=src.getnchannels();step=max(1,round(rate*.02))
        while block:=src.readframes(step):
            if event.is_set():raise InterruptedError('音频时间校准已停止')
            samples=array.array('h',block)
            if sys.byteorder!='little':samples.byteswap()
            values.append(math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))/32768)
    if not values:return []
    # Use a lower noise quantile, bounded away from the active voice level.
    noise=sorted(values)[len(values)//5];peak=max(values)
    threshold=max(.004,min(peak*.25,noise*2.5))
    spans=[];start=None;last=0
    for i,rms in enumerate(values):
        if rms>=threshold:
            if start is None:start=max(0,i-3)
            last=i
        elif start is not None and i-last>8:
            if last-start>=3:spans.append((start*20000,min(len(values)*20000,(last+5)*20000)))
            start=None
    if start is not None:spans.append((start*20000,min(len(values)*20000,(last+5)*20000)))
    merged=[]
    for a,b in spans:
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(merged[-1][1],b))
        else:merged.append((a,b))
    return merged


def mapped_intervals(a,b,cuts):
    for cut in cuts:
        s=cut['sourceStart'];n=cut.get('sourceDuration',cut['duration']);e=s+n
        left=max(a,s);right=min(b,e)
        if right<=left:continue
        target_a=cut['start']+round((left-s)*cut['duration']/n)
        target_b=cut['start']+round((right-s)*cut['duration']/n)
        if target_b>target_a:yield target_a,target_b-target_a,left,right-left


def captions(cues,spans,cuts):
    result=[]
    for cue in cues:
        a,b=cue['start'],cue['end']
        hits=[(max(a,x),min(b,y)) for x,y in spans if min(b,y)>max(a,x)]
        if hits:a=max(a,hits[0][0]-40000);b=min(b,hits[-1][1]+60000)
        for target,length,_,_ in mapped_intervals(a,b,cuts):
            if result and result[-1]['text']==cue['text'] and target<=result[-1]['end']+1000:
                result[-1]['end']=target+length
            else:result.append({'start':target,'end':target+length,'text':cue['text']})
    return result


def style_video(draft,clip,index,cuts,opts):
    if opts['timelineMode']!='detailed':return
    profile=PROFILES[opts['editProfile']]
    for key in ('contrast','saturation','brightness'):
        if opts['colorAdjust']:clip.add_keyframe(getattr(draft.KeyframeProperty,key),0,profile[key])
    if opts['cameraMotion']:
        a,b=(1.,profile['scale']) if index%2==0 else (profile['scale'],1.)
        clip.add_keyframe(draft.KeyframeProperty.uniform_scale,0,a)
        clip.add_keyframe(draft.KeyframeProperty.uniform_scale,max(1,cuts[index]['duration']-1),b)
    if opts['transition']=='dissolve' and index<len(cuts)-1:
        length=min(300000,cuts[index]['duration']//4,cuts[index+1]['duration']//4)
        if length>=10000:clip.add_transition(draft.TransitionType.叠化,duration=length)


def layers(draft,script,duration,cuts,opts):
    report={'filterSegments':0,'effectSegments':0,'overlaySegments':0,'adjustedSegments':0,'transitionSegments':0,'resourceWarnings':[]}
    if opts['timelineMode']!='detailed':return report
    report['adjustedSegments']=len(cuts) if opts['colorAdjust'] else 0
    report['transitionSegments']=sum(min(300000,a['duration']//4,b['duration']//4)>=10000 for a,b in zip(cuts,cuts[1:])) if opts['transition']=='dissolve' else 0
    if opts['filterStyle']=='cinema':
        script.append_tracks([draft.TrackSpec(draft.TrackType.filter,'质感电影')])
        script.add_filter(draft.FilterType.质感电影,draft.Timerange(0,duration),'质感电影',opts['filterIntensity'])
        report['filterSegments']=1
    if opts['visualEffect']:
        script.append_tracks([draft.TrackSpec(draft.TrackType.effect,'画面效果')])
        effect=getattr(draft.VideoSceneEffectType,opts['visualEffect'],None)
        if effect is None:raise ValueError('当前草稿组件不支持所选画面特效')
        script.add_effect(effect,draft.Timerange(0,duration),'画面效果');report['effectSegments']=1
    if opts['overlayText']:
        script.append_tracks([draft.TrackSpec(draft.TrackType.text,'角标')])
        text=draft.TextSegment(opts['overlayText'],draft.Timerange(0,duration),
             style=draft.TextStyle(size=4,color=(1,1,1)),border=draft.TextBorder(width=12),
             clip_settings=draft.ClipSettings(transform_x=.55,transform_y=.85))
        script.add_segment(text,'角标');report['overlaySegments']=1
    if report['filterSegments'] or report['effectSegments'] or report['transitionSegments']:
        report['resourceWarnings'].append('滤镜、特效和转场使用剪映资源编号；是否已下载以及当前剪映版本是否可用，需要在编辑器中核对')
    return report


def append_adjustment_track(data,duration,enabled=True):
    """Write the neutral native adjust structure observed in draft_info.json.

    An editable adjustment layer is distinct from grading the video. The
    reference's LUT path is empty and HSL values are zero; retain those neutral
    values rather than claiming that a visible yellow strip proves grading.
    """
    if not enabled:return 0
    if type(duration) is not int or duration<=0:raise ValueError('调节轨时长无效')
    if any(t.get('type')=='adjust' for t in data['tracks']):raise ValueError('草稿已有独立调节轨，未重复添加')
    material_id,lut_id,hsl_id,segment_id,track_id=(str(uuid.uuid4()) for _ in range(5))
    materials=data['materials']
    materials.setdefault('placeholders',[]).append({'id':material_id,'material_resource_id':'','name':'调节1','type':'adjust'})
    materials.setdefault('effects',[]).append({
        'adjust_params':[],'algorithm_artifact_path':'','apply_target_type':0,'bloom_params':None,
        'category_id':'','category_name':'','color_match_info':{'source_feature_path':'','target_feature_path':'','target_image_path':''},
        'effect_id':'','enable_skin_tone_correction':False,'exclusion_group':[],'face_adjust_params':[],
        'formula_id':'','id':lut_id,'intensity_key':'','multi_language_current':'','name':'','panel_id':'',
        'path':'','platform':'all','request_id':'','resource_id':'','source_platform':0,'sub_type':'none',
        'time_range':None,'type':'lut','value':1.,'version':''})
    materials.setdefault('hsl',[]).append({'hsl_color_type':1,'hue':0,'id':hsl_id,'interacting':True,
        'lightness':0,'path':'','saturation':0,'type':'hsl','version':'1'})
    segment={'caption_info':None,'cartoon':False,'clip':None,'common_keyframes':[],
        'enable_adjust':True,'enable_color_correct_adjust':False,'enable_color_curves':True,
        'enable_color_match_adjust':False,'enable_color_wheels':True,'enable_lut':True,
        'enable_smart_color_adjust':False,'extra_material_refs':[lut_id,hsl_id],'group_id':'',
        'hdr_settings':None,'id':segment_id,'intensifies_audio':False,'is_placeholder':False,
        'is_tone_modify':False,'keyframe_refs':[],'last_nonzero_volume':1.,'material_id':material_id,
        'render_index':len(data['tracks']),'responsive_layout':{'enable':False,'horizontal_pos_layout':0,
            'size_layout':0,'target_follow':'','vertical_pos_layout':0},
        'reverse':False,'source_timerange':None,'speed':1.,'target_timerange':{'duration':duration,'start':0},
        'template_id':'','template_scene':'default','track_attribute':0,'track_render_index':0,
        'uniform_scale':None,'visible':True,'volume':1.}
    data['tracks'].append({'attribute':0,'flag':0,'id':track_id,'is_default_name':False,
        'name':'调节','segments':[segment],'type':'adjust'})
    return 1
