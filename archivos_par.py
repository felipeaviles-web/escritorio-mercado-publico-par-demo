"""Registro y verificación local de los archivos incorporados."""
import hashlib
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

EXTENSIONS={'.pdf','.dwg','.dxf','.xlsx','.xls','.doc','.docx','.zip','.rar','.7z','.txt','.csv','.jpg','.jpeg','.png'}


def clean(value, limit):
    return re.sub(r'\s+',' ',re.sub(r'[<>:"/\\|?*\x00-\x1f]',' ',str(value))).strip(' .')[:limit].rstrip(' .')


def inventory(folder):
    folder=Path(folder)
    if not folder.is_dir():return []
    result=[]
    for p in folder.rglob('*'):
        if p.is_symlink() or any(x.is_symlink() for x in p.parents if x!=folder.parent):continue
        if p.is_file() and p.suffix.lower() in EXTENSIONS and p.resolve().is_relative_to(folder.resolve()):
            result.append(p)
    return result


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def store_upload(stream, filename, target):
    """Guarda sin sobrescribir, con temporal unico y deduplicacion por SHA-256."""
    target=Path(target);target.mkdir(parents=True,exist_ok=True)
    name=clean(Path(filename).name,160)
    if not name or Path(name).suffix.lower() not in EXTENSIONS:
        raise ValueError('Extension no admitida: '+name)
    handle,tmpname=tempfile.mkstemp(prefix='.incorporacion_',suffix='.part',dir=target)
    tmp=Path(tmpname)
    try:
        with os.fdopen(handle,'wb') as out:shutil.copyfileobj(stream,out,1024*1024)
        if tmp.stat().st_size==0:raise ValueError('Archivo vacio: '+name)
        checksum=digest(tmp);original=target/name;dst=original;number=0
        while True:
            try:
                # Enlace atomico en el mismo volumen: nunca reemplaza un original.
                os.link(tmp,dst)
                break
            except FileExistsError:
                if dst.is_file() and not dst.is_symlink() and digest(dst)==checksum:
                    return {'archivo':dst.name,'nuevo':False,'sha256':checksum}
                number+=1
                suffix='_'+checksum[:8]+('' if number==1 else '_'+str(number))
                dst=original.with_name(original.stem+suffix+original.suffix)
        if digest(dst)!=checksum:raise RuntimeError('Copia no coincide: '+dst.name)
        return {'archivo':dst.name,'nuevo':True,'sha256':checksum}
    finally:
        tmp.unlink(missing_ok=True)


def verify_expediente(folder):
    """Comprobacion local, distinta del cotejo de completitud con el portal."""
    folder=Path(folder);files=inventory(folder);docs=0;errors=[];manifest=[]
    for p in files:
        name=str(p.relative_to(folder));checks=[]
        if not p.stat().st_size:errors.append('Archivo vacio: '+name)
        if p.suffix.lower()=='.zip':
            try:
                with zipfile.ZipFile(p) as z:
                    bad=z.testzip()
                    if bad:errors.append('ZIP dañado: '+name+' / '+bad)
                    docs+=sum(not x.is_dir() for x in z.infolist())
                    checks.append('CRC ZIP')
            except (zipfile.BadZipFile,OSError,RuntimeError,NotImplementedError):
                errors.append('ZIP no verificable: '+name)
        else:
            docs+=1
            if p.suffix.lower()=='.pdf':
                with p.open('rb') as f:
                    if f.read(5)!=b'%PDF-':errors.append('Encabezado PDF invalido: '+name)
                checks.append('Encabezado PDF; no valida documento completo')
            else:checks.append('Formato interno no validado')
        manifest.append({'archivo':name,'bytes':p.stat().st_size,'sha256':digest(p),'controles':checks})
    return {'archivos':len(files),'documentos_incluyendo_zip':docs,'errores':errors,
            'comprobacion_local_ok':bool(files) and not errors,
            'portal_completo_verificado':False,'manifiesto':manifest}
