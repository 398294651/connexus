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
            return obj.strftime('%Y-%m-%d')

        if isinstance(obj, ndb.Key):
            return obj.id()

        return json.JSONEncoder.default(self, obj)


def prettify_date(date):
    return None if not date else date.strftime('%Y-%m-%d')
