import json
import os
import requests
from urlparse import urlparse

import jinja2
import webapp2
from google.appengine.ext import db
from google.appengine.api import images, users

from models import Image, Stream, Leaderboard, View, User
from utils import MyEncoder

DEFAULT_COVER = "http://college-social.com/content \
        /uploads/2014/03/not-found.png"

PATH = os.path.dirname(__file__)
JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader([PATH, PATH + '/templates']),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


def populate_user():
    user = users.get_current_user()
    if user:
        meta = {'logged_in': True,
                'nickname': user.nickname(),
                'header_url': users.create_logout_url('/')}

        if not User.get_by_id(user.nickname()):
            User(id=user.nickname()).put()
    else:
        meta = {'logged_in': False,
                'header_url': users.create_login_url('/')}
    return meta


class HandleUser(webapp2.RequestHandler):
    def get(self):
        if not populate_user()['logged_in']:
            self.redirect('/')
        user = User.get_by_id(populate_user()['nickname'])
        if not user:
            return self.response.out.write("Not found!")
        self.response.headers['Content-Type'] = 'application/json'
        user_dict = user.to_dict()
        return self.response.out.write(json.dumps(user_dict, cls=MyEncoder))


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
        if self.request.get('trending') == 'true':
            return self.show_trending()
        streams = Stream.query().order(Stream.date).fetch()
        streams = [x.to_dict() for x in streams]
        return self.response.out.write(json.dumps(streams, cls=MyEncoder))

    def get(self):
        self.response.headers['Content-Type'] = 'application/json'
        stream_name = self.request.get('stream_name')
        if not stream_name:
            return self.show_all_streams()
        stream = Stream.get_by_id(stream_name)
        if not stream:
            return self.error(404)
        """
        for image in stream.image_ids:
            out = self.response.out
            out.write('<div><img src="image?image_id=%s"></img>' %
                      image.get().key.id())
        """
        # Increment View Count
        stream.view_count += 1
        stream.put()
        View(stream_id=stream.key).put()
        return self.response.out.write(json.dumps(stream.to_dict(),
                                                  cls=MyEncoder))

    def post(self):
        req = self.request
        if not populate_user()['logged_in']:
            self.redirect('/')
        user_id = populate_user()['nickname']
        stream_name = req.get('name')
        stream_tags = req.get('tags').split(',')
        stream_cover = req.get('cover') or DEFAULT_COVER
        if Stream.get_by_id(stream_name):
            return self.response.out.write('Sorry! Stream already exists.')
        stream = Stream(id=stream_name, tags=stream_tags,
                        cover_url=stream_cover).put()
        user = User.get_by_id(user_id)
        user.owned_ids.append(stream)
        user.put()
        self.redirect('/manage')


class HandleSearch(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('search.html')
        self.response.write(template.render(populate_user()))

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
        self.redirect('/view?stream_name='+stream_id)


class HandleTrendingUI(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('trending.html')
        self.response.write(template.render(populate_user()))


class HandleManageUserUI(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('manage.html')
        self.response.write(template.render(populate_user()))


class HandleCreateStreamUI(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('create.html')
        self.response.write(template.render(populate_user()))


class HandleViewStreamUI(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('view.html')
        data = populate_user()
        name = self.request.get('stream_name')
        if not name:
            # TODO: Handle this case
            return self.redirect('/')
        domain = '{uri.scheme}://{uri.netloc}'.format(
            uri=urlparse(self.request.url))
        response = requests.get(domain + '/stream',
                                params={'stream_name': name})
        data['stream_name'] = name
        if response.status_code == requests.codes.OK:
            data['image_ids'] = response.json()['image_ids']
        self.response.write(template.render(data))


class HandleLogin(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('index.html')
        self.response.write(template.render(populate_user()))


app = webapp2.WSGIApplication([
    ('/', HandleLogin),
    ('/manage', HandleManageUserUI),
    ('/create', HandleCreateStreamUI),
    ('/view', HandleViewStreamUI),
    ('/trending', HandleTrendingUI),

    ('/user', HandleUser),
    ('/stream', HandleStream),
    ('/image', HandleImage),
    ('/search', HandleSearch),
    ('/cron', HandleCron),
    ('/subscribe', HandleSubsrciption)
])
