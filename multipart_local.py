"""Carga multipart local en flujo, sin cgi ni dependencias de terceros."""
import tempfile
from email.message import Message
from email.parser import BytesParser
from email import policy
from pathlib import Path

MAX_UPLOAD=1024*1024*1024


class Reader:
    def __init__(self,stream,length):
        self.stream=stream;self.left=length;self.buffer=b''

    def fill(self):
        if not self.left:raise ValueError('Carga multipart incompleta')
        block=self.stream.read(min(65536,self.left))
        if not block:raise ValueError('Carga interrumpida')
        self.left-=len(block);self.buffer+=block

    def line(self):
        while b'\r\n' not in self.buffer:
            if len(self.buffer)>65536:raise ValueError('Cabecera demasiado larga')
            self.fill()
        line,self.buffer=self.buffer.split(b'\r\n',1)
        return line

    def body(self,out,marker):
        while True:
            pos=self.buffer.find(marker)
            if pos>=0:
                end=pos+len(marker)
                while len(self.buffer)<end+2:self.fill()
                suffix=self.buffer[end:end+2]
                if suffix in (b'--',b'\r\n'):
                    out.write(self.buffer[:pos]);self.buffer=self.buffer[end+2:]
                    return suffix==b'--'
                out.write(self.buffer[:pos+2]);self.buffer=self.buffer[pos+2:]
            elif len(self.buffer)>len(marker)+2:
                keep=len(marker)+2;out.write(self.buffer[:-keep]);self.buffer=self.buffer[-keep:]
            else:self.fill()


def read_uploads(stream,content_type,length,folder):
    """Devuelve (nombre, temporal). El llamador limpia temporales al terminar."""
    if not 0<length<=MAX_UPLOAD:raise ValueError('Tamaño de carga no permitido')
    header=Message();header['content-type']=content_type or ''
    boundary=header.get_param('boundary')
    if header.get_content_type()!='multipart/form-data' or not boundary or len(boundary)>70:
        raise ValueError('Formulario multipart invalido')
    try:boundary=boundary.encode('ascii')
    except UnicodeEncodeError:raise ValueError('Separador multipart invalido')
    if b'\r' in boundary or b'\n' in boundary:raise ValueError('Separador multipart invalido')
    reader=Reader(stream,length);paths=[];uploads=[]
    try:
        if reader.line()!=b'--'+boundary:raise ValueError('Inicio multipart invalido')
        while True:
            headers=[];total=0
            while True:
                line=reader.line()
                if not line:break
                total+=len(line)
                if total>65536:raise ValueError('Cabeceras demasiado largas')
                headers.append(line)
            message=BytesParser(policy=policy.default).parsebytes(b'\r\n'.join(headers)+b'\r\n\r\n')
            name=message.get_param('name',header='content-disposition');filename=message.get_filename()
            with tempfile.NamedTemporaryFile(prefix='.carga_',suffix='.part',dir=folder,delete=False) as out:
                path=Path(out.name);paths.append(path)
                last=reader.body(out,b'\r\n--'+boundary)
            if name=='archivos' and filename:uploads.append((filename,path))
            if last:break
        while reader.left:reader.fill();reader.buffer=b''
        for path in paths:
            if not any(p==path for _,p in uploads):path.unlink(missing_ok=True)
        return uploads
    except Exception:
        for path in paths:path.unlink(missing_ok=True)
        raise
