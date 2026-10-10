let pass = 0, fail = 0, group = '';
exports.group = g => { group = g; console.log('\n# ' + g); };
exports.ok = (cond, msg) => { if (cond) pass++; else { fail++; console.log('  FAIL [' + group + '] ' + msg); } };
exports.eq = (a, b, msg) => exports.ok(JSON.stringify(a) === JSON.stringify(b), msg + '  got ' + JSON.stringify(a).slice(0,200) + ' want ' + JSON.stringify(b).slice(0,200));
exports.done = () => { console.log('\n' + pass + ' passed, ' + fail + ' failed'); process.exit(fail ? 1 : 0); };
