import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const [galleryRoot, outputRoot, chrome, playwrightPackage] = process.argv.slice(2);
const {chromium} = createRequire(path.resolve(playwrightPackage))('playwright');
fs.mkdirSync(outputRoot, {recursive:true});
const report = {schema_version:'handdraw-gallery-ui.v1', gallery_root:galleryRoot,
  cases:[], failures:[], blocked_external:[], browser_closed:false,
  clipboard_transport:'isolated in-page buffer; OS clipboard untouched',
  source:'real local HTML, real Chromium file navigation; only clipboard transport substituted'};
const browser = await chromium.launch({executablePath:chrome, headless:true, chromiumSandbox:true,
  ignoreDefaultArgs:['--enable-unsafe-swiftshader','--unsafely-disable-devtools-self-xss-warnings','--disable-ipc-flooding-protection'],
  args:['--disable-gpu','--disable-gpu-compositing','--disable-background-networking',
    '--disable-component-update','--renderer-process-limit=1','--num-raster-threads=1','--js-flags=--single-threaded'],
  env:{...process.env,TEMP:outputRoot,TMP:outputRoot}});
function check(row, name, ok, details=null) {
  row.checks.push({name,passed:!!ok,details});
  if(!ok) report.failures.push({case:row.name,name,details});
  fs.writeFileSync(path.join(outputRoot,'ui-report.json'),JSON.stringify(report,null,2));
}
try {
 for(const [device, viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
  const context=await browser.newContext({viewport,isMobile:device==='mobile',hasTouch:device==='mobile',locale:'zh-CN',serviceWorkers:'block'});
  await context.route('**/*', async route=>{
    const url=route.request().url();
    if(url.startsWith('file:')||url.startsWith('data:')||url.startsWith('blob:')) await route.continue();
    else {report.blocked_external.push(url);await route.abort('blockedbyclient');}
  });
  await context.addInitScript(()=>{
    window.__copied=[];window.__copyDenied=false;
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{
      if(window.__copyDenied) throw new DOMException('Denied by synthetic acceptance case','NotAllowedError');
      window.__copied.push(text);
    }}});
    const original=document.execCommand.bind(document);
    document.execCommand=(command,...args)=>command==='copy'?false:original(command,...args);
  });
  for(const kind of ['index','layouts','colors']) {
    const row={name:`${device}-${kind}`,viewport,checks:[],screenshots:[],page_errors:[]};report.cases.push(row);
    const page=await context.newPage();page.setDefaultTimeout(12000);
    page.on('pageerror',error=>row.page_errors.push(error.message));
    page.on('dialog', async dialog=>{row.manual_dialog={type:dialog.type(),message:dialog.message(),value:dialog.defaultValue()};await dialog.dismiss();});
    try {
      await page.goto(pathToFileURL(path.join(galleryRoot,`${kind}.html`)).href,{waitUntil:'load'});
      await page.evaluate(()=>{for(const image of document.images) image.loading='eager';});
      await page.waitForFunction(()=>[...document.images].every(i=>!i.getAttribute('src')||i.complete),{timeout:15000});
      const assets=await page.evaluate(()=>[...document.images].filter(i=>i.getAttribute('src')&&!i.naturalWidth).map(i=>i.getAttribute('src')));
      check(row,'local_assets_loaded',assets.length===0,assets);
      const initial=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
      check(row,'no_horizontal_overflow',initial.scroll<=initial.width,initial);
      const cardSelector=kind==='index'?'.style-card':kind==='layouts'?'.layout-card':'.color-card';
      const categorySelector=kind==='index'?'.filter[data-group="F"]':kind==='layouts'?'.filter[data-category="infographic"]':'.filter[data-category="green"]';
      await page.locator(categorySelector).click();
      await page.waitForTimeout(150);
      const visible=await page.locator(`${cardSelector}:visible`).count();
      const expected=await page.evaluate(({kind,cardSelector})=>[...document.querySelectorAll(cardSelector)].filter(e=>kind==='index'?e.dataset.group==='F':e.dataset.category===(kind==='layouts'?'infographic':'green')).length,{kind,cardSelector});
      check(row,'filter_exact_count',visible===expected&&visible>0,{visible,expected});
      await page.locator('.size-btn[data-size="1x"]').click();
      check(row,'size_switch',await page.locator('body').getAttribute('data-size')==='1x');
      const baseShot=path.join(outputRoot,`${row.name}-filtered.png`);await page.screenshot({path:baseShot});row.screenshots.push(baseShot);
      const card=page.locator(`${cardSelector}:visible`).first();
      const target=kind==='colors'?card.locator('.card-thumb-btn'):card;
      if(device==='mobile')await target.tap();else await target.click();
      await page.waitForFunction(()=>document.querySelector('#preview-image').complete&&document.querySelector('#preview-image').naturalWidth>0);
      check(row,'selection_opens_preview',await page.locator('#preview').evaluate(e=>e.open));
      const copySelector=kind==='index'?'#copy-cmd':kind==='layouts'?'#copy':'#dialog-copy-btn';
      await page.locator(copySelector).click();
      await page.waitForTimeout(100);
      const copied=await page.evaluate(()=>window.__copied.at(-1));
      check(row,'copy_payload_present',typeof copied==='string'&&copied.length>0,copied);
      if(kind==='layouts'){
        const expectedPrompt=await card.getAttribute('data-prompt-zh');
        check(row,'layout_export_matches_source',copied===expectedPrompt);
      }
      const dialogBox=await page.locator('#preview').boundingBox();
      check(row,'preview_fits_width',dialogBox.x>=-1&&dialogBox.x+dialogBox.width<=viewport.width+1,dialogBox);
      const modalShot=path.join(outputRoot,`${row.name}-selected.png`);await page.screenshot({path:modalShot});row.screenshots.push(modalShot);
      // Reproduce denial; success must not be reported if both transports fail.
      await page.evaluate(()=>{window.__copyDenied=true;});
      await page.locator(copySelector).click();await page.waitForTimeout(100);
      const label=await page.locator(copySelector).textContent();
      const fallback=await page.locator('#handdraw-copy-fallback').count();
      check(row,'denied_copy_not_false_success',!!row.manual_dialog||fallback>0||!/已复制|Copied/i.test(label),{label,manual_dialog:row.manual_dialog??null,fallback});
      if(fallback){
        check(row,'manual_export_preserves_payload',await page.locator('#handdraw-copy-fallback textarea').inputValue()===copied);
        const fallbackBox=await page.locator('#handdraw-copy-fallback').boundingBox();
        check(row,'manual_export_fits_viewport',fallbackBox.x>=0&&fallbackBox.y>=0&&fallbackBox.x+fallbackBox.width<=viewport.width+1&&fallbackBox.y+fallbackBox.height<=viewport.height+1,fallbackBox);
        const shot=path.join(outputRoot,`${row.name}-copy-fallback.png`);await page.screenshot({path:shot});row.screenshots.push(shot);
        await page.locator('#handdraw-copy-fallback button').click();
      }
      await page.evaluate(()=>{window.__copyDenied=false;});
      await page.keyboard.press('Escape');
      check(row,'preview_closes',!(await page.locator('#preview').evaluate(e=>e.open)));
      await page.locator('#lang-btn').click();
      check(row,'language_switch',await page.locator('html').getAttribute('lang')==='en');
      await page.locator('#lang-btn').click();
      check(row,'no_page_errors',row.page_errors.length===0,row.page_errors);
    } catch(error){check(row,'interaction_completed',false,error.message);}
    finally {await page.close();}
  }
  await context.close();
 }
} finally {await browser.close();report.browser_closed=true;fs.writeFileSync(path.join(outputRoot,'ui-report.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({cases:report.cases.length,failures:report.failures,browser_closed:report.browser_closed}));
if(report.failures.length)process.exitCode=2;
