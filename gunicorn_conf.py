bind = "0.0.0.0:5000"
workers = 1                # важно: один воркер, чтобы не было двойной инициализации
worker_class = "gthread"
threads = 8
timeout = 60
keepalive = 2

accesslog = "-"            # будем видеть каждый HTTP-запрос
errorlog  = "-"
loglevel  = "info"
