from analyze import evstats as _evstats

def eventstats(values,meta,obs,stocks):return _evstats(values,obs,stocks,**meta)
