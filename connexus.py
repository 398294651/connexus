import cgi
import datetime
import json
import urllib
from time import mktime

import webapp2
from google.appengine.ext import ndb, db
from google.appengine.api import images, users


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


class Image(ndb.Model):
    """Models an image which is linked via Stream
    """
    data = ndb.BlobProperty()
    comment = ndb.StringProperty()
    date = ndb.DateTimeProperty(auto_now_add=True, required=True)


DEFAULT_COVER = "http://college-social.com/content \
        /uploads/2014/03/not-found.png"


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


class User(ndb.Model):
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
        views = main.View.query(main.View.date > date_limit).fetch()
        stream_freq = {}
        for view in views:
            stream_freq[view.stream_id] = stream_freq.get(
                view.stream_id, 0) + 1

        sorted_streams = sorted(
            stream_freq.items(), key=operator.itemgetter(1), reverse=True)

        ndb.delete_multi(main.Leaderboard.query().fetch(keys_only=True))

        for stream in sorted_streams:
            main.Leaderboard(stream_id=stream[0], view_count=stream[1],
                             interval=duration).put()


class HandleUser(webapp2.RequestHandler):
    def get(self, user_id):
        user = User.get_by_id(user_id)
        if not user:
            return self.response.out.write("Not found!")
        self.response.headers['Content-Type'] = 'application/json'
        user_dict = user.to_dict()
        return self.response.out.write(json.dumps(user_dict, cls=MyEncoder))
        """
        return self.response.out.write("Welcome %s, You have %s owned and %s \
                                        subscribed streams" % (user.key.id(),
                                       len(user.owned), len(user.subscribed)))
        """


class HandleCron(webapp2.RequestHandler):
    def post(self):
        duration = self.request.get('duration')
        Leaderboard.refresh(duration)
        # TODO: Change cron timings


class HandleSubsrciption(webapp2.RequestHandler):
    def post(self):
        user_id = self.request.get('user_id')
        stream_id = self.request.get('stream_id')
        user = User.get_by_id(user_id)
        if not user:
            return self.response.out.write("Not Found!")
        user.subscribed_ids.append(Stream.get_by_id(stream_id).key)
        user.put()


class HandleStream(webapp2.RequestHandler):
    def show_trending(self):
        count = int(self.request.get('count', 5))
        leaders = Leaderboard.query().order(
            -Leaderboard.view_count).fetch(count)
        stream_list = []
        for leader in leaders:
            stream_dict = leader.stream_id.get().to_dict()
            stream_dict.update(leader.to_dict())
            stream_list.append(stream_dict)
        return self.response.out.write(json.dumps(stream_list, cls=MyEncoder))

    def show_all_streams(self):
        self.response.headers['Content-Type'] = 'application/json'
        if self.request.get('trending') == 'true':
            return self.show_trending()
        streams = Stream.query().order(Stream.date).fetch()
        streams = [x.to_dict() for x in streams]
        return self.response.out.write(json.dumps(streams, cls=MyEncoder))

    def get(self):
        stream_name = self.request.get('stream_name')
        if not stream_name:
            return self.show_all_streams()
        stream = Stream.get_by_id(stream_name)
        if not stream:
            return self.response.out.write("404")
        for image in stream.image_ids:
            out = self.response.out
            out.write('<div><img src="image?image_id=%s"></img>' %
                      image.get().key.id())
        # Increment View Count
        stream.view_count += 1
        stream.put()
        View(stream_id=stream.key).put()

    def post(self):
        req = self.request
        user_id = req.get('user_id')
        stream_name = req.get('name')
        stream_tags = req.get('tags').split(',')
        stream_cover = req.get('cover') or DEFAULT_COVER
        if not user_id:
            return self.response.out.write('Sorry! Authenticate first.')
        if Stream.get_by_id(stream_name):
            return self.response.out.write('Sorry! Stream already exists.')
        stream = Stream(id=stream_name, tags=stream_tags,
                        cover_url=stream_cover).put()
        user = User.get_by_id(user_id)
        user.owned_ids.append(stream)
        user.put()
        return self.response.out.write('Success creating... %s' % stream.id())


class HandleSearch(webapp2.RequestHandler):
    def post(self):
        query = self.request.get('query')
        self.response.headers['Content-Type'] = 'application/json'
        stream_list = []
        for stream in Stream.query().fetch():
            if query in stream.key.id() or stream.check_tags(query):
                stream_dict = stream.to_dict()
                stream_list.append(stream_dict)
        return self.response.out.write(json.dumps(stream_list, cls=MyEncoder))


class HandleImage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'image/png'
        self.response.out.write(Image.get_by_id(int(
            self.request.get('image_id'))).data)

    def post(self):
        stream_id = self.request.get('stream_id')
        if not Stream.get_by_id(stream_id):
            return self.response.out.write('Stream id %s not found!' %
                                           stream_id)
        stream = Stream.get_by_id(stream_id)

        avatar = images.resize(self.request.get('img'), 320, 320)
        image = Image(data=db.Blob(avatar),
                      comment=self.request.get('comment')).put()
        stream.image_ids.append(image)
        stream.put()
        return self.response.out.write('Success!')


class HandleLogin(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            greeting = ('Welcome, %s! (<a href="%s">sign out</a>)' %
                        (user.nickname(), users.create_logout_url('/')))
        else:
            greeting = ('<a href="%s">Sign in or register</a>.' %
                        users.create_login_url('/'))

        self.response.out.write('<html><body>%s</body></html>' % greeting)


app = webapp2.WSGIApplication([
    ('/', HandleLogin),
    ('/users/(\w+)', HandleUser),
    ('/stream', HandleStream),
    ('/image', HandleImage),
    ('/search', HandleSearch),
    ('/cron', HandleCron),
    ('/subscribe', HandleSubsrciption)
])
