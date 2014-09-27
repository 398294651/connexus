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

    def last_image_date(self):
        dates = [image.get().date for image in self.image_ids]
        if len(dates) == 0:
            return None
        return sorted(dates, reverse=True)[0]

    def image_count(self):
        return len(self.image_ids)


class User(ModelUtils, ndb.Model):
    owned_ids = ndb.KeyProperty(repeated=True, kind=Stream)
    subscribed_ids = ndb.KeyProperty(repeated=True, kind=Stream)
    date = ndb.DateTimeProperty(auto_now_add=True, required=True)

    def is_subscribed(self, stream_name):
        return stream_name in [x.id() for x in self.subscribed_ids]

    def is_owned(self, stream_name):
        return stream_name in [x.id() for x in self.owned_ids]

    def owned_id_details(self):
        return [{'name': stream.id(),
                 'last_date': stream.get().last_image_date(),
                 'image_count': stream.get().image_count()}
                for stream in self.owned_ids]

    def subscribed_id_details(self):
        return [{'name': stream.id(),
                 'last_date': stream.get().last_image_date(),
                 'view_count': stream.get().view_count,
                 'image_count': stream.get().image_count()}
                for stream in self.subscribed_ids]


class View(ndb.Model):
    stream_id = ndb.KeyProperty(kind=Stream)
    date = ndb.DateTimeProperty(auto_now_add=True, required=True)


class Leaderboard(ndb.Model):
    stream_id = ndb.KeyProperty(kind=Stream)
    view_count = ndb.IntegerProperty()
    interval = ndb.IntegerProperty(default=0)

    @classmethod
    def refresh(cls, duration=5):
        duration = int(duration)
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
            if stream[0].get():
                Leaderboard(stream_id=stream[0], view_count=stream[1],
                            interval=duration).put()
