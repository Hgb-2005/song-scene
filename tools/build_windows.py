"""Reproducible Windows desktop build: use a clean venv and PyInstaller 6.22.3."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]


def build(output,work,iscc):
    output=Path(output).resolve();work=Path(work).resolve()
    if output.is_relative_to(ROOT) or work.is_relative_to(ROOT):raise ValueError('Build folders must be outside the checkout')
    output.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir','--name','SongScene',
             '--distpath',str(work/'dist'),'--workpath',str(work/'pyinstaller'),'--specpath',str(work),'--exclude-module','numpy','--exclude-module','PIL']
    for name in ['index.html','界面','封面','素材署名','网页预览','THIRD_PARTY_NOTICES.md']:
        command+=['--add-data',str(ROOT/name)+':'+('.' if (ROOT/name).is_file() else name)]
    command+=[str(ROOT/'launcher.py')]
    subprocess.run(command,cwd=ROOT,check=True)
    app=work/'dist/SongScene'
    for name in ['THIRD_PARTY_NOTICES.md','docs/V8-安装与使用.md']:
        shutil.copy2(ROOT/name,app/Path(name).name)
    shutil.copytree(ROOT/'desktop/licenses',app/'licenses',dirs_exist_ok=True)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():shutil.copy2(python_license,app/'PYTHON_LICENSE.txt')
    # Match the Tcl/Tk DLL license in this Python distribution.
    for lib in ['tcl8.6','tk8.6']:
        license_path=Path(sys.base_prefix)/'tcl'/lib/'license.terms'
        if license_path.exists():shutil.copy2(license_path,app/(lib+'-license.terms'))
    manifest={'version':'8.0.0','platform':'Windows 10/11 x64','python':sys.version.split()[0],
              'engine':'Fetched unchanged from upstream only when required; see desktop/engine.py',
              'files':{str(f.relative_to(app)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(app.rglob('*')) if f.is_file()}}
    (app/'build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    portable=output/'SongScene-v8-Windows-Portable.zip'
    with ZipFile(portable,'w',compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(app.rglob('*')):
            if file.is_file():archive.write(file,Path('SongScene')/file.relative_to(app))
    subprocess.run([str(iscc),'/Q','/DAppSource='+str(app),'/DOutputFolder='+str(output),str(ROOT/'desktop/installer.iss')],check=True)
    print(json.dumps({'portable':str(portable),'installer':str(output/'SongScene-v8-Windows-Setup.exe'),'application':str(app)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--work-dir',type=Path,required=True);parser.add_argument('--iscc',type=Path,required=True)
    args=parser.parse_args();build(args.output,args.work_dir,args.iscc)
