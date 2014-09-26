import datetime
import json
from time import mktime

from google.appengine.ext import ndb


class ModelUtils(object):
    def to_dict(self):
        result = super(ModelUtils, self).to_dict()
        result['id'] = self.key.id()
        return result


class MyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return int(mktime(obj.timetuple()))

        if isinstance(obj, ndb.Key):
            return obj.id()

        return json.JSONEncoder.default(self, obj)
