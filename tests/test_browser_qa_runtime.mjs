import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {assetRoot,allowedAssetUrl,integerArgument,protectOutput,loadBrowserPackage,
  puppeteerOfflinePage,playwrightOfflineContext} from '../scripts/browser_qa_runtime.mjs';
const root=path.resolve(process.env.CONTENT_STUDIO_BROWSER_TEST_ROOT ?? 'outputs/browser-unit');
fs.mkdirSync(root,{recursive:true});
const assets=path.join(root,'assets');fs.mkdirSync(assets,{recursive:true});
const input=path.join(assets,'synthetic.html');fs.writeFileSync(input,'<!doctype html><p>Synthetic only</p>');
const outside=path.join(root,'outside.txt');fs.writeFileSync(outside,'SYNTHETIC OUTSIDE');
let count=0;const check=(name,fn)=>{fn();count++;console.log('PASS '+name);};
check('explicit/default asset roots',()=>{assert.equal(assetRoot(input),fs.realpathSync(assets));assert.throws(()=>assetRoot(outside,assets));});
check('local file admitted, outside refused',()=>{assert.equal(allowedAssetUrl(pathToFileURL(input).href,assets),true);assert.equal(allowedAssetUrl(pathToFileURL(outside).href,assets),false);});
check('nonlocal/loopback/WebSocket URLs refused',()=>{for(const u of ['https://example.invalid/x','http://127.0.0.1/x','ws://example.invalid/x','not-a-url'])assert.equal(allowedAssetUrl(u,assets),false);});
check('embedded static resources admitted',()=>{for(const u of ['data:image/svg+xml,<svg/>','blob:null/synthetic','about:blank'])assert.equal(allowedAssetUrl(u,assets),true);});
check('integer parsing rejects numeric prefixes/fractions/negative/overflow',()=>{assert.equal(integerArgument('0','index'),0);for(const v of ['1junk','1.5','-1','',2**54])assert.throws(()=>integerArgument(v,'index'));});
check('output cannot overwrite input',()=>{assert.throws(()=>protectOutput(input,[input]));protectOutput(path.join(root,'new.png'),[input]);});
check('output cannot alias input through a hardlink',()=>{const alias=path.join(root,'input-hardlink');fs.linkSync(input,alias);assert.throws(()=>protectOutput(alias,[input]));});
check('unrelated existing output does not match protected input',()=>{protectOutput(outside,[input]);});
check('wrong package metadata rejected before import',()=>{const pkg=path.join(root,'package.json');fs.writeFileSync(pkg,JSON.stringify({name:'unapproved-runtime'}));assert.throws(()=>loadBrowserPackage(pkg,['playwright']),/configured package/);});
{
  let listener;const calls=[];
  const page={setJavaScriptEnabled:async v=>calls.push(['js',v]),setOfflineMode:async v=>calls.push(['offline',v]),
    setRequestInterception:async v=>calls.push(['intercept',v]),on:(name,fn)=>{assert.equal(name,'request');listener=fn;}};
  const blocked=await puppeteerOfflinePage(page,assets);
  let aborted=false,continued=false;
  await listener({url:()=> 'https://example.invalid/?secret=not-recorded',abort:async()=>{aborted=true;},continue:async()=>{continued=true;}});
  check('Puppeteer interception aborts remote and strips query evidence',()=>{assert.equal(aborted,true);assert.equal(continued,false);assert.deepEqual(blocked,['https://example.invalid']);assert.deepEqual(calls,[['js',false],['offline',true],['intercept',true]]);});
}
{
  let route,config;const browser={newContext:async options=>{config=options;return {route:async(_,fn)=>{route=fn;}};}};
  const blocked=[];await playwrightOfflineContext(browser,assets,blocked,{viewport:{width:100,height:100}});
  let aborted=false;await route({request:()=>({url:()=> 'http://127.0.0.1/never-contact'}),abort:async()=>{aborted=true;},continue:async()=>assert.fail('must not continue')});
  check('Playwright context blocks scripts/workers/downloads/network',()=>{assert.equal(aborted,true);assert.equal(config.javaScriptEnabled,false);assert.equal(config.offline,true);assert.equal(config.serviceWorkers,'block');assert.equal(config.acceptDownloads,false);});
}
// CLI syntax/help are run by the host tool, separately from this no-child test.
console.log(JSON.stringify({passed:count,skipped:0,native_browser_started:false}));
