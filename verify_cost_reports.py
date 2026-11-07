"""Report arithmetic, actual media scope and template compatibility; no models."""
import copy,csv,hashlib,io,json,os,tempfile,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from lxml import etree as ET
import cost_reports as reports

ROOT=Path(__file__).resolve().parent
W=reports.W
def content(path):
    with zipfile.ZipFile(path) as z:
        root=ET.fromstring(z.read('word/document.xml'))
        return '\n'.join(''.join(p.itertext()) for p in root.iter(W+'p'))
def config():return {'costRows':[{'name':'演员报酬','amount':3000},{'name':'制作与剪辑','amount':6000},{'name':'AI服务','amount':1000}],**reports.DEFAULTS,'costTemplate':''}

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='cost-report-');self.home=Path(self.temp.name)
        self.project={'id':'fixture','name':'成本报告核验剧集','videos':[{'path':'fixture.mp4','duration':61.5}]}
    def tearDown(self):self.temp.cleanup()
    def test_real_amounts_actor_ratio_and_media_totals(self):
        cfg=config();info=reports.generate(self.project,cfg,[{'duration':61.5},{'duration':60}],'final',self.home)
        text=content(self.home/'成本报告.docx')
        for expected in [self.project['name'],'2集，共2分2秒','1万元','30.00%','报审机构','法定代表人或总编辑']:self.assertIn(expected,text)
        self.assertEqual(info['source'],'final');self.assertEqual(info['actorAmount'],3000)
        self.assertNotIn('{{',text);self.assertNotIn('35 %',text);self.assertNotIn('符合《关于',text)
        with (self.home/'成本比例表.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
        self.assertEqual(rows[-1],['合计','10000.00','100.00%'])
    def test_explicit_actor_classification_overrides_names(self):
        cfg=config();cfg['costRows']=[{'name':'演员报酬','amount':100,'actor':False},{'name':'配音费用','amount':20,'actor':True}]
        facts=reports.facts(self.project,cfg,self.project['videos'],'original')
        self.assertEqual(facts['actorAmount'],20);self.assertEqual(facts['values']['{{演员片酬占比}}'],'16.67%')
    def test_signature_fields_and_date_are_filled(self):
        cfg=config()|{'costOrganization':'示例制作单位','costRepresentative':'示例负责人','costReportDate':'2026-10-31'}
        reports.generate(self.project,cfg,self.project['videos'],'original',self.home);text=content(self.home/'成本报告.docx')
        for expected in ['示例制作单位','示例负责人','2026年10月31日']:self.assertIn(expected,text)
    def test_currency_rounds_each_row_before_adding(self):
        cfg=config();cfg['costRows']=[{'name':'制作','amount':0.105},{'name':'演员报酬','amount':0.105}]
        facts=reports.facts(self.project,cfg,self.project['videos'],'original')
        self.assertEqual(str(facts['total']),'0.22');self.assertEqual(facts['values']['{{总投资万元}}'],'0.000022')
    def test_invalid_inputs_leave_old_reports_unchanged(self):
        path=self.home/'成本报告.docx';path.write_bytes(b'previous')
        for change in [{'costRows':[{'name':'x','amount':float('nan')}]},{'costRows':[{'name':'x','amount':-1}]},{'costReportDate':'2026-02-31'},{'costRows':[{'name':'x','amount':1,'actor':'yes'}]},{'costTemplate':'missing.docx'}]:
            with self.assertRaises(ValueError):reports.generate(self.project,config()|change,self.project['videos'],'original',self.home)
            self.assertEqual(path.read_bytes(),b'previous');self.assertFalse((self.home/'成本比例表.csv').exists())
    def test_missing_media_does_not_invent_episode_totals(self):
        for videos in [[],[{'duration':0}],[{'duration':float('nan')}],[{}]]:
            with self.assertRaises(ValueError):reports.facts(self.project,config(),videos,'original')
    def test_old_three_token_template_is_preserved_and_gets_summary(self):
        from docx import Document
        p=self.home/'legacy.docx';doc=Document();doc.add_paragraph('原模板 {{剧名}} {{总成本}} {{日期}}');doc.save(p)
        old=hashlib.sha256(p.read_bytes()).hexdigest();reports.generate(self.project,config()|{'costTemplate':str(p)},self.project['videos'],'original',self.home)
        text=content(self.home/'成本报告.docx');self.assertIn('原模板 成本报告核验剧集 10000.00',text);self.assertIn('成本配置比例情况报告',text)
        self.assertEqual(old,hashlib.sha256(p.read_bytes()).hexdigest())
    def test_builtin_never_contains_reference_project_or_amount(self):
        text=content(ROOT/'assets/cost-report.docx')
        self.assertNotIn('7701696277871856664',text);self.assertNotIn('8万元',text);self.assertNotIn('35 %',text)
    def test_report_name_drops_only_provider_directory_suffix(self):
        self.assertEqual(reports.report_title({'name':'剧名__7701696277871856664'}),'剧名')
        self.assertEqual(reports.report_title({'name':'剧名1000万'}),'剧名1000万')
    def test_server_uses_current_final_media_and_preserves_scope(self):
        os.environ['MANJU_DATA']=str(self.home/'data')
        import server
        final=[{'path':'final-a.mp4'},{'path':'final-b.mp4'}];cfg=config()
        with patch.object(server,'final_videos',return_value=final),patch.object(server,'video_entries',return_value=[{'duration':20},{'duration':30}]) as media,patch.object(server,'project_dir',return_value=self.home),patch.object(server,'register') as register,patch.object(server,'log') as log:
            server.costs(self.project,cfg,'fixture-job')
        media.assert_called_once_with(['final-a.mp4','final-b.mp4']);self.assertIn('2集，共50秒',content(self.home/'成本报告.docx'));self.assertEqual(register.call_count,2)
        self.assertIn('当前成片 2集',log.call_args[0][0])

if __name__=='__main__':unittest.main(verbosity=2)
