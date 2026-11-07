"""Reference-style cost declarations from actual entered costs and media totals."""
from pathlib import Path
from datetime import date
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
import csv,io,re,uuid,zipfile
from lxml import etree as ET

DEFAULTS={'costOrganization':'','costRepresentative':'','costReportDate':''}
ACTOR_NAMES={'演员报酬','演员片酬','演员总片酬','演员费用'}
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

def actor_cost(row):
    return row.get('actor',str(row.get('name','')).strip() in ACTOR_NAMES)

def report_title(project):
    # The provider appends its numeric identity to download directory names.
    # It is not part of the drama's human-readable name in the declaration.
    return re.sub(r'__\d{15,22}$','',project['name']).strip() or project['name']

def validate(cfg):
    for key,limit in [('costOrganization',100),('costRepresentative',80),('costReportDate',10)]:
        value=cfg.get(key,'')
        if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):raise ValueError('成本报告署名或日期格式无效')
    value=cfg.get('costReportDate','')
    if value:
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError()
            date.fromisoformat(value)
        except ValueError:raise ValueError('成本报告日期无效，请选择有效日期') from None
    rows=cfg.get('costRows')
    if not isinstance(rows,list) or len(rows)>100:raise ValueError('成本项目最多100项')
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('name'),str) or not row['name'].strip() or len(row['name'])>100:raise ValueError('成本项目名称须为1至100字')
        if 'actor' in row and type(row['actor']) is not bool:raise ValueError('演员片酬标记无效')
        try:
            value=Decimal(str(row['amount']))
            if not value.is_finite() or value<0 or value>Decimal('1000000000000'):raise ValueError()
        except (InvalidOperation,KeyError,ValueError):raise ValueError('成本金额须为有效非负数') from None
    return cfg

def facts(project,cfg,videos,source):
    validate(cfg)
    rows=[{**r,'amount':Decimal(str(r['amount'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)} for r in cfg['costRows']]
    total=sum((r['amount'] for r in rows),Decimal('0'))
    if total<=0:raise ValueError('成本合计为0，请填写实际成本后生成')
    if not videos:raise ValueError('没有可统计的视频，请先导入本剧视频或完成分集制作')
    seconds=Decimal('0')
    for video in videos:
        try:
            duration=Decimal(str(video['duration']))
            if not duration.is_finite() or duration<=0:raise ValueError()
            seconds+=duration
        except (KeyError,InvalidOperation,ValueError):raise ValueError('视频时长无效，请重新读取本剧素材后生成成本报告') from None
    actors=sum((r['amount'] for r in rows if actor_cost(r)),Decimal('0'))
    reported_seconds=max(1,int(seconds.quantize(Decimal('1'),rounding=ROUND_HALF_UP)))
    hours,remaining=divmod(reported_seconds,3600);minutes,secs=divmod(remaining,60)
    duration_text=(f'{hours}小时' if hours else '')+(f'{minutes}分' if minutes else '')+(f'{secs}秒' if secs or not (hours or minutes) else '钟' if not hours else '')
    day=date.fromisoformat(cfg['costReportDate']) if cfg.get('costReportDate') else date.today()
    investment=format(total/Decimal(10000),'f').rstrip('0').rstrip('.') if total%10000 else str(total//10000)
    return {'rows':rows,'total':total,'actorAmount':actors,'actorRatio':actors/total,'count':len(videos),
            'seconds':seconds,'duration':duration_text,'source':source,
            'values':{'{{剧名}}':report_title(project),'{{集数}}':str(len(videos)),'{{总时长}}':duration_text,
                '{{总成本}}':f'{total:.2f}','{{总投资万元}}':investment,'{{演员片酬占比}}':f'{actors/total:.2%}',
                '{{报审机构}}':cfg.get('costOrganization','').strip() or '________________',
                '{{代表人}}':cfg.get('costRepresentative','').strip() or '________________',
                '{{日期}}':day.isoformat(),'{{日期中文}}':f'{day.year}年{day.month}月{day.day}日'}}

def _fill(source,values):
    output=io.BytesIO()
    with zipfile.ZipFile(source) as src,zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as target:
        for item in src.infolist():
            data=src.read(item)
            if item.filename.startswith('word/') and item.filename.endswith('.xml'):
                root=ET.fromstring(data);changed=False
                for paragraph in root.iter(W+'p'):
                    nodes=list(paragraph.iter(W+'t'));old=''.join(n.text or '' for n in nodes);text=old
                    for key,value in values.items():text=text.replace(key,value)
                    if text!=old and nodes:
                        changed=True
                        nodes[0].text=text
                        for n in nodes[1:]:n.text=''
                if changed:data=ET.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
            target.writestr(item,data)
    output.seek(0)
    return output

def generate(project,cfg,videos,source,out):
    info=facts(project,cfg,videos,source)
    builtin=Path(__file__).resolve().parent/'assets/cost-report.docx'
    template=Path(cfg['costTemplate']).expanduser() if cfg.get('costTemplate','').strip() else builtin
    if not template.is_file() or template.suffix.lower()!='.docx':raise ValueError('Word模板不存在或不是.docx文件')
    with zipfile.ZipFile(template) as z:template_text=z.read('word/document.xml').decode('utf-8')
    # Full declaration templates fill in place. Older three-token templates keep
    # their existing front matter and receive the new declaration on a new page.
    complete=all(key in template_text for key in ['{{集数}}','{{总时长}}','{{总投资万元}}','{{演员片酬占比}}'])
    data=_fill(template,info['values'])
    if not complete:
        from docx import Document
        from copy import deepcopy
        doc=Document(data);report=Document(_fill(builtin,info['values']));doc.add_page_break()
        for el in report.element.body:
            if el.tag!=W+'sectPr':doc.element.body.insert(len(doc.element.body)-1,deepcopy(el))
        data=io.BytesIO();doc.save(data);data.seek(0)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    report=out/'成本报告.docx';table=out/'成本比例表.csv';token=uuid.uuid4().hex
    temporary=out/('.cost-'+token+'.docx');csvtemp=out/('.cost-'+token+'.csv')
    try:
        temporary.write_bytes(data.getvalue())
        with csvtemp.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f);writer.writerow(['项目','金额（元）','占比'])
            for row in info['rows']:writer.writerow([row['name'],f'{row["amount"]:.2f}',f'{row["amount"]/info["total"]:.2%}'])
            writer.writerow(['合计',f'{info["total"]:.2f}','100.00%'])
        temporary.replace(report);csvtemp.replace(table)
    finally:temporary.unlink(missing_ok=True);csvtemp.unlink(missing_ok=True)
    return {'files':[table,report],**info}
