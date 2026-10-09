"""Never serialize message text, exception, request, SQL or task args into routine logs."""
import json
import logging
from gunicorn.glogging import Logger


class SafeFormatter(logging.Formatter):
    def format(self,record):
        entry={'level':record.levelname,'event':'request.complete' if record.name=='jahez.request' else 'service.event'}
        for key in ('status','duration_ms'):
            value=getattr(record,key,None)
            if type(value) is int:entry[key]=value
        method=getattr(record,'method','')
        if method in ('GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'):entry['method']=method
        route=getattr(record,'route','')
        if route in ('public','admin','webhook','health','other'):entry['route']=route
        request_id=getattr(record,'request_id','')
        import re
        if isinstance(request_id,str) and re.fullmatch('[0-9a-f]{16}',request_id):entry['request_id']=request_id
        return json.dumps(entry,separators=(',',':'))


class SafeGunicornLogger(Logger):
    def setup(self,cfg):
        super().setup(cfg)
        for handler in self.error_log.handlers:handler.setFormatter(SafeFormatter())
    def error(self,msg,*args,**kwargs):
        self.error_log.error('Server error; inspect request correlation and service health.')
    def warning(self,msg,*args,**kwargs):
        self.error_log.warning('Server warning; inspect service health.')
    def critical(self,msg,*args,**kwargs):
        self.error_log.critical('Server critical error; inspect service health.')
