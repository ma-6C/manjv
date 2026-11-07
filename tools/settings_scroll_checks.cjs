// Real wheel input is required: synthetic WheelEvents do not scroll Chromium.
module.exports=async function settingsScrollChecks(page,{dialog,panel,header,footer,nav,check,prefix}){
 const read=()=>page.evaluate(({dialog,panel,header,footer})=>{
  const p=document.querySelector(panel),d=document.querySelector(dialog),h=document.querySelector(header),f=document.querySelector(footer);
  const rect=e=>{const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height};};
  return {background:scrollY,backgroundMax:document.scrollingElement.scrollHeight-innerHeight,
   panel:p.scrollTop,panelMax:p.scrollHeight-p.clientHeight,panelHeight:p.clientHeight,
   dialog:rect(d),header:rect(h),footer:rect(f),viewport:innerHeight};
 },{dialog,panel,header,footer});
 const wheel=async(selector,delta)=>{if(selector)await page.locator(selector).hover();await page.mouse.wheel(0,delta);await page.waitForTimeout(200);return read();};
 await page.locator(panel).evaluate(el=>el.scrollTop=0);const before=await read();
 check(prefix+'_settings_have_real_scrollable_content',before.panelMax>20&&before.panelHeight>80);
 const down=await wheel(panel,500);
 check(prefix+'_wheel_scrolls_settings_and_keeps_background',down.panel>before.panel&&down.background===before.background);
 await wheel(panel,5000);const bottom=await wheel(panel,700);
 check(prefix+'_bottom_does_not_scroll_background',Math.abs(bottom.panel-bottom.panelMax)<2&&bottom.background===before.background);
 await wheel(panel,-5000);const top=await wheel(panel,-700);
 check(prefix+'_top_does_not_scroll_background',top.panel===0&&top.background===before.background);
 const fromHeader=await wheel(header,600),fromNav=await wheel(nav,600),fromFooter=await wheel(footer,600);
 await page.mouse.move(3,Math.floor(before.viewport/2));await page.mouse.wheel(0,600);await page.waitForTimeout(200);const backdrop=await read();
 check(prefix+'_header_nav_footer_and_backdrop_keep_background',[fromHeader,fromNav,fromFooter,backdrop].every(x=>x.background===before.background));
 check(prefix+'_title_and_footer_stay_visible',Math.abs(down.header.top-before.header.top)<1&&Math.abs(down.footer.bottom-before.footer.bottom)<1&&bottom.footer.bottom<=before.viewport+1&&bottom.dialog.top>=-1);
 return {before,down,bottom,top,backdrop};
};
