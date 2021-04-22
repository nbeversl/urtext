import datetime
from pytz import timezone

default_date = timezone('UTC').localize(datetime.datetime(1970,1,1))

class UrtextTimestamp:
    def __init__(self, dt_string):
        if not dt_string:
            dt_string = ''
        self.datetime = date_from_timestamp(dt_string)
        self.string = dt_string
        if self.datetime == None:
            self.datetime = default_date


def date_from_timestamp(datestamp_string):
    d = None
    try:
        d = parse(datestamp_string)
    except:
        pass
        #print('No date for '+datestamp_string)
    if d and d.tzinfo == None:
         d = timezone('UTC').localize(d) 
    return d