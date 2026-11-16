"""Build portable source/light/full archives without private workspace data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
import argparse

ROOT=Path(__file__).resolve().parents[1]
NAMES={'full':'一歌一景-完整可播放-v7.zip','light':'一歌一景-轻量可播放演示-v7.zip','source':'一歌一景-页面源码-v7.zip'}


def package(kind,output):
    output=Path(output).resolve()
    if output.is_relative_to(ROOT):raise ValueError('Archive directory must be outside the source folder')
    output.mkdir(parents=True,exist_ok=True)
    target=output/NAMES[kind]
    if target.exists():raise FileExistsError(target)
    with ZipFile(target,'w') as archive:
        for file in sorted(ROOT.rglob('*')):
            relative=file.relative_to(ROOT)
            if not file.is_file() or any(part in ['data','__pycache__','.git','artifacts'] for part in relative.parts) or file.suffix in ['.zip','.pyc'] or file.name.startswith('.env'):continue
            if kind in ['light','source'] and relative.parts[0]=='视频':continue
            if kind=='source' and relative.parts[0]=='网页预览':continue
            archive.write(file,relative.as_posix(),compress_type=ZIP_STORED if file.suffix.lower()=='.mp4' else ZIP_DEFLATED,compresslevel=6)
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert not any(name.startswith('data/') for name in archive.namelist())
    print(f'{target.name}: {target.stat().st_size/1024/1024:.2f} MiB')
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind',choices=['all',*NAMES],default='all')
    parser.add_argument('--output',type=Path,default=ROOT.parent)
    args=parser.parse_args()
    for kind in NAMES if args.kind=='all' else [args.kind]:package(kind,args.output)
