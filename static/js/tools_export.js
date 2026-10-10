const fs=require('fs'),path=require('path');
const T=require('./static/js/mccf_theory.js'),M=require('./static/js/mccf_midi.js'),W=require('./static/js/mccf_smf_writer.js');
const src=process.argv[2], out=process.argv[3];
const buf=fs.readFileSync(src);const parsed=M.parseMidiFile(buf.buffer.slice(buf.byteOffset,buf.byteOffset+buf.byteLength));
const recipe=T.makeRecipe({file:path.basename(src),sha256:T.sha256Hex(buf),tracks:[3],bars:[10,16],key:{tonic:'A',scale:'major'},ruleSet:'chorale-strict',seed:1729,
 voices:[{id:'lead',name:'Theme (nylon guitar)',source:'theme',entryBar:1,program:24,channel:5,volume:110},
   {id:'ri',name:'Retrograde-inversion (kalimba)',source:'theme',entryBar:1,program:108,channel:6,volume:100,chain:[{type:'retrogradeInversion'}]}]
  .concat(T.makeCanon({voices:2,offsetBars:2,steps:-4,program:24,firstChannel:7,volume:90,name:'Canon below'}))});
const errs=T.validateRecipe(recipe); if(errs.length){console.error(errs);process.exit(1);}
const theme=T.extractTheme(parsed,recipe.source);const arr=T.assemble(recipe,theme);
const o=W.writeSMF(arr,{name:'Conductor',comment:'MCCF '+T.ENGINE.name+' '+T.ENGINE.version+' recipe '+T.recipeDigest(recipe)});
fs.writeFileSync(out+'.mid',o.bytes);fs.writeFileSync(out+'.recipe.json',JSON.stringify(recipe,null,2)+'\n');
console.log('wrote',out+'.mid',o.bytes.length,'bytes; warnings:',o.warnings.concat(arr.warnings));
console.log('theme:',T.describeFingerprint(T.fingerprint(theme.notes,theme.length,theme.ppq,theme.barTicks)));
arr.tracks.forEach(t=>{const f=T.fingerprint(t.notes,t.lengthTicks,theme.ppq,theme.barTicks);console.log(' ',t.name.padEnd(34),'ch',t.channel+1,'prog',t.program,'| first note tick',t.notes[0].startTick,'|',t.noteCount,'notes, range',f.lowest+'-'+f.highest);});
