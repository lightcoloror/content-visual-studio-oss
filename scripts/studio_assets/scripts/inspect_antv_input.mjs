#!/usr/bin/env node
// Existing AntV parseSyntax adapter; no renderer/browser implementation is copied.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

if(process.argv.includes('--help')){
  console.log('inspect_antv_input.mjs --module-root <existing infographic-cli> --input <local.ifgc>; alternatively --package-root <existing @antv/infographic>. No install, browser or rendering.');
  process.exit(0);
}
try{
  const args={};
  for(let i=2;i<process.argv.length;i+=2){
    const name=process.argv[i],value=process.argv[i+1];
    if(!['--module-root','--package-root','--input'].includes(name)||!value||value.startsWith('--')||Object.hasOwn(args,name.slice(2)))throw new Error('arguments must be unique --name value pairs');
    args[name.slice(2)]=value;
  }
  if(!args.input||Boolean(args['module-root'])===Boolean(args['package-root']))throw new Error('explicit input and exactly one runtime root required');
  const root=fs.realpathSync(path.resolve(args['package-root']??path.join(args['module-root'],'node_modules/@antv/infographic')));
  const metadata=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
  if(metadata.name!=='@antv/infographic')throw new Error('configured package must be @antv/infographic');
  // This is the same parser exported by AntV's top-level index; avoid importing
  // unrelated renderer/editor registries for a syntax-only operation.
  const {parseSyntax}=await import(pathToFileURL(path.join(root,'esm/syntax/index.js')).href);
  const parsed=parseSyntax(fs.readFileSync(path.resolve(args.input),'utf8'));
  process.stdout.write(JSON.stringify({template:parsed.options?.template??null,data:parsed.options?.data??{},errors:parsed.errors??[],warnings:parsed.warnings??[]}));
}catch(error){
  process.stderr.write(`${error instanceof Error?error.message:String(error)}\n`);process.exitCode=2;
}
