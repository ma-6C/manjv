"""Ordered episode selection shared by source adapters and tests."""
import re

def normalize(value,total=10000,order='chosen'):
    if isinstance(value,str):
        rows=[]
        for part in re.split(r'[,，、\s]+',value.strip()):
            if not part:continue
            m=re.fullmatch(r'(\d+)(?:[-–~](\d+))?',part)
            if not m:raise ValueError('集号格式有误，例如 1,3,8,12-15')
            first=int(m[1]);last=int(m[2] or m[1])
            if first<1 or last<first or last>total:raise ValueError(f'集数范围应在 1 至 {total} 之间')
            rows.extend(range(first,last+1))
        value=rows
    if not isinstance(value,list) or not value or len(value)>10000:raise ValueError('请选择有效的集数')
    if any(type(n) is not int or not 1<=n<=total for n in value):raise ValueError('集数超出范围或格式无效')
    if order not in ('chosen','number'):raise ValueError('集数处理顺序无效')
    result=list(dict.fromkeys(value))
    return sorted(result) if order=='number' else result
