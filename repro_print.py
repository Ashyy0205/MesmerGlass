import json, tempfile, subprocess, sys, os
sample={"version":1,"name":"CLI Pack","text":{"items":[{"msg":"Focus","secs":5}]},"pulse":{"stages":[{"mode":"wave","intensity":0.25,"secs":10}],"fallback":"idle"}}
d=tempfile.mkdtemp()
p=os.path.join(d,'pack.json')
open(p,'w',encoding='utf-8').write(json.dumps(sample))
r=subprocess.run([sys.executable,'-m','mesmerglass','session','--load',p,'--print'], capture_output=True, text=True)
print('PATH',p)
print('RC',r.returncode)
print('STDOUT>>'+r.stdout+'<<')
print('STDERR>>'+r.stderr+'<<')