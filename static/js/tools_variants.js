// Canon variants over the original badwater backing.  node tools_variants.js fixtures/badwater.mid outdir
const fs=require('fs'),path=require('path');
const T=require('./static/js/mccf_theory.js'),M=require('./static/js/mccf_midi.js'),W=require('./static/js/mccf_smf_writer.js');
const src=process.argv[2], outDir=process.argv[3]; fs.mkdirSync(outDir,{recursive:true});
const buf=fs.readFileSync(src), parsed=M.parseMidiFile(buf.buffer.slice(buf.byteOffset,buf.byteOffset+buf.byteLength));
const sha=T.sha256Hex(buf), THEME={tracks:[3],bars:[10,16]}, WIN={fromBar:8,toBar:25};
const theme=T.extractTheme(parsed,THEME), win=T.extractWindow(parsed,{...WIN,skipTracks:[3]});
const shift=(THEME.bars[0]-WIN.fromBar)*theme.barTicks, ki=T.keyInfo({tonic:'A',scale:'major'});
// original nylon-guitar settings, so the lead sounds as it does in the song
const lead={id:'lead',name:'Theme (nylon, original)',source:'theme',entryBar:1,program:24,channel:5,volume:127,pan:24,reverb:16,chorus:16};
const fol=(id,name,chain,entry,ch,pan)=>({id,name,source:'theme',chain,entryBar:entry,program:24,channel:ch,volume:127,pan,reverb:16,chorus:16});
const tr=(steps)=>({type:'transpose',params:{steps,mode:'diatonic'}});
const V=[
 ['A_third_below_2bar',   'Third below, enters 2 bars later',   [fol('f1','Follower: third below',[tr(-2)],3,6,100)]],
 ['B_sixth_below_2bar',   'Sixth below, enters 2 bars later',   [fol('f1','Follower: sixth below',[tr(-5)],3,6,100)]],
 ['C_octave_below_2bar',  'Octave below, enters 2 bars later',  [fol('f1','Follower: octave below',[tr(-7)],3,6,100)]],
 ['D_third_below_4bar',   'Third below, enters 4 bars later',   [fol('f1','Follower: third below',[tr(-2)],5,6,100)]],
 ['E_octave_below_4bar',  'Octave below, enters 4 bars later',  [fol('f1','Follower: octave below',[tr(-7)],5,6,100)]],
 ['F_closing_echo',       'Closing: last 3 bars echoed a third below, 1 bar later', [fol('f1','Echo: last 3 bars, third below',[{type:'fragment',params:{bars:[5,7]}},tr(-2)],6,6,100)]],
];
const DISS=new Set([1,2,6,10,11]);
function vertical(a,b){let tot=0,d=0;const pts=new Set([...a.map(n=>n.startTick),...b.map(n=>n.startTick)]);
  for(const t of pts){const x=a.find(n=>n.startTick<=t&&t<n.startTick+n.durTicks),y=b.find(n=>n.startTick<=t&&t<n.startTick+n.durTicks);if(x&&y){tot++;if(DISS.has(Math.abs(x.pitch-y.pitch)%12))d++;}}return [d,tot];}
const rows=[];
function emit(file,label,voices){
  const recipe=T.makeRecipe({file:path.basename(src),sha256:sha,tracks:THEME.tracks,bars:THEME.bars,key:{tonic:'A',scale:'major'},ruleSet:'chorale-strict',seed:1729,voices});
  const errs=T.validateRecipe(recipe); if(errs.length) throw new Error(file+': '+errs.join('; '));
  const arr=T.assemble(recipe,theme,{shiftTicks:shift}), merged=T.mergeBacking(arr,win);
  const o=W.writeSMF(merged,{name:'Conductor',comment:'MCCF '+T.ENGINE.name+' '+T.ENGINE.version+' '+label+' | recipe '+T.recipeDigest(recipe)+' | source '+sha.slice(0,12)+' | backing bars '+WIN.fromBar+'-'+WIN.toBar+' of badwater.mid'});
  fs.writeFileSync(path.join(outDir,file+'.mid'),o.bytes); fs.writeFileSync(path.join(outDir,file+'.recipe.json'),JSON.stringify(recipe,null,2)+'\n');
  const L=arr.tracks[0].notes; const ds=arr.tracks.slice(1).map(t=>vertical(L,t.notes));
  rows.push([file,label,ds.map(([d,t])=>d+'/'+t).join(' '),o.bytes.length,o.warnings.concat(arr.warnings)]);
}
emit('0_reference_original','Reference: the original, nylon guitar in place',[lead]);
V.forEach(([f,l,fs_])=>emit(f,l,[lead,...fs_]));
rows.forEach(r=>console.log(r[0].padEnd(24),r[2].padEnd(8),'dissonant/overlap',String(r[3]).padStart(6),'B',r[4].length?r[4]:''));
