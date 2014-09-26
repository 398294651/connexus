import datetime
import operator

from google.appengine.ext import ndb

from utils import ModelUtils


class Image(ndb.Model):
    """Models an image which is linked via Stream
    """
    data = ndb.BlobProperty()
    comment = ndb.StringProperty()
    date = ndb.DateTimeProperty(auto_now_add=True, required=True)


class Stream(ModelUtils, ndb.Model):
    """Models a Stream which contains many images
    """
    image_ids = ndb.KeyProperty(repeated=True, kind=Image)
    tags = ndb.StringProperty(repeated=True)
    cover_url = ndb.StringProperty()
    view_count = ndb.IntegerProperty(default=0)
    date = ndb.DateTimeProperty(auto_now_add=True, required=True)

    def check_tags(self, query):
        for tag in self.tags:
            if query in tag:
                return True
        return False


class User(ModelUtils, ndb.Model):
    owned_ids = ndb.KeyProperty(repeated=True, kind=Stream)
    subscribed_ids = ndb.KeyProperty(repeated=True, kind=Stream)
    date = ndb.DateTimeProperty(auto_now_add=True, required=True)


class View(ndb.Model):
    stream_id = ndb.KeyProperty(kind=Stream)
    date = ndb.DateTimeProperty(auto_now_add=True, required=True)


class Leaderboard(ndb.Model):
    stream_id = ndb.KeyProperty(kind=Stream)
    view_count = ndb.IntegerProperty()
    interval = ndb.IntegerProperty(default=0)

    @classmethod
    def refresh(duration=5):
        date_limit = datetime.datetime.now() - datetime.timedelta(
            minutes=duration)
        views = View.query(View.date > date_limit).fetch()
        stream_freq = {}
        for view in views:
            stream_freq[view.stream_id] = stream_freq.get(
                view.stream_id, 0) + 1

        sorted_streams = sorted(
            stream_freq.items(), key=operator.itemgetter(1), reverse=True)

        ndb.delete_multi(Leaderboard.query().fetch(keys_only=True))

        for stream in sorted_streams:
            Leaderboard(stream_id=stream[0], view_count=stream[1],
                        interval=duration).put()
