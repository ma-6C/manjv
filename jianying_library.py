"""Register real local media in Jianying's bin as well as on its timeline."""
from pathlib import Path
import json
import time
import uuid

GROUP_TYPES=(0,1,2,3,6,7,8)
VERSION=1


def write(folder,data,meta):
    folder=Path(folder).resolve()
    now=int(time.time()*1000)
    rows=[];by_path={}
    # The bin's All view should start with the two full-length stems.
    audios=data.get('materials',{}).get('audios',[])
    audios=sorted(audios,key=lambda m:({'人声.wav':0,'背景声.wav':1}.get(Path(m.get('path','')).name,2)))
    for group,materials in ((1,audios),(0,data.get('materials',{}).get('videos',[]))):
        for material in materials:
            path=Path(material['path']).resolve()
            if not path.is_relative_to(folder) or not path.is_file():raise ValueError('素材库媒体未复制到当前工程：'+path.name)
            if path in by_path:
                material['local_material_id']=by_path[path]['id']
                continue
            duration=material.get('duration',0)
            if type(duration) is not int or duration<=0:raise ValueError('素材库媒体时长无效：'+path.name)
            relative='./'+path.relative_to(folder).as_posix()
            mid=str(uuid.uuid5(uuid.UUID(data['id']),relative)).upper()
            # Current builds sort at second precision before their name tie
            # breaker. Give each bin position a distinct import ordering value.
            stamp=now//1000-len(rows)
            item={'create_time':now//1000,'duration':duration,'extra_info':path.name,
                  'file_Path':relative,'id':mid,'import_time':stamp,'import_time_ms':stamp*1000,
                  'item_source':1,'md5':'','metetype':'video' if group==0 else 'music',
                  'roughcut_time_range':{'start':0,'duration':duration},
                  'sub_time_range':{'start':-1,'duration':-1},'type':1}
            if group==0:item.update(width=int(material['width']),height=int(material['height']))
            material['local_material_id']=mid
            by_path[path]=item;rows.append((group,item))
    meta['draft_materials']=[{'type':kind,'value':[item for group,item in rows if group==kind]} for kind in GROUP_TYPES]
    virtual={'draft_materials':[],'draft_virtual_store':[
        {'type':0,'value':[{'creation_time':0,'display_name':'','filter_type':0,'id':'',
            'import_time':0,'import_time_us':0,'material_color_tag':'','sort_sub_type':0,
            'sort_type':0,'subdraft_filter_type':0}]},
        {'type':1,'value':[{'child_id':item['id'],'parent_id':''} for _,item in rows]},
        {'type':2,'value':[]}]}
    (folder/'draft_virtual_store.json').write_text(json.dumps(virtual,ensure_ascii=False,indent=2),'utf-8')
    return {'version':VERSION,'videos':sum(group==0 for group,_ in rows),'audios':sum(group==1 for group,_ in rows),
            'files':[{'id':item['id'],'relative':item['file_Path'][2:],'name':item['extra_info'],
                      'durationUs':item['duration']} for _,item in rows]}


def validate(folder,data,meta,index):
    folder=Path(folder).resolve();library=index.get('library')
    if not library:return
    expected={item['relative']:item for item in library['files']}
    inventory={item['relative'] for item in index['assets']}
    rows=[]
    groups=meta.get('draft_materials')
    if not isinstance(groups,list) or [x.get('type') for x in groups]!=list(GROUP_TYPES):raise ValueError('剪映素材库分组登记不完整')
    for group in groups:
        for item in group.get('value',[]):
            raw=item.get('file_Path','')
            if not isinstance(raw,str) or not raw.startswith('./'):raise ValueError('剪映素材库媒体路径无效')
            relative=raw[2:];path=(folder/relative).resolve()
            if relative not in expected or relative not in inventory or not path.is_relative_to(folder) or not path.is_file():
                raise ValueError('剪映素材库媒体缺失或未登记：'+path.name)
            entry=expected[relative]
            if item.get('id')!=entry['id'] or item.get('duration')!=entry['durationUs']:raise ValueError('剪映素材库条目与媒体清单不一致')
            rows.append(item)
    if len(rows)!=len(expected) or len({x['file_Path'] for x in rows})!=len(rows):raise ValueError('剪映素材库存在缺项或重复项')
    if len([x for x in rows if x['metetype']=='video'])!=library['videos']:raise ValueError('剪映素材库视频数量不一致')
    if len([x for x in rows if x['metetype']=='music'])!=library['audios']:raise ValueError('剪映素材库音频数量不一致')
    ids={x['id'] for x in rows}
    for group in ('videos','audios'):
        for item in data.get('materials',{}).get(group,[]):
            if item.get('local_material_id') not in ids:raise ValueError('时间线素材未关联剪映素材库')
    virtual=json.loads((folder/'draft_virtual_store.json').read_text('utf-8'))
    linked=[x['child_id'] for group in virtual['draft_virtual_store'] if group['type']==1 for x in group['value']]
    if len(linked)!=len(ids) or set(linked)!=ids:raise ValueError('剪映素材库列表索引不完整')
