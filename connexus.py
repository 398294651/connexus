import datetime
import json
import os
import requests
from urlparse import urlparse

import jinja2
import webapp2
from google.appengine.ext import db
from google.appengine.api import images, users, mail

from models import Image, Stream, Leaderboard, View, User, Meta
from utils import MyEncoder

DEFAULT_COVER = "http://college-social.com/content" + \
    "/uploads/2014/03/not-found.png"

PATH = os.path.dirname(__file__)
JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader([PATH, PATH + '/templates']),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)
IMG_CNT = 8
IMG_OFF = 0
SEARCH_COUNT = 5
LEADERBOARD_UPDATE_DURATION = 60
SENDER = "conneksus@appspot.gserviceaccount.com"
EMAIL_RCVR = ["sreesurendran55@gmail.com", "prat0318@gmail.com",
              "ragha@utexas.edu", "natviv@cs.utexas.edu"]


def domain(url):
    return '{uri.scheme}://{uri.netloc}'.format(
        uri=urlparse(url))


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


def send_subscribtion_invite_email(stream_add_subscribers_email_list,
                                   stream_email_body, stream_name,
                                   request_url):
    stream_link = domain(request_url) + '/view?stream_name=' + stream_name
    # TODO: de-duplicate email addresses
    for add in stream_add_subscribers_email_list:
        mail.send_mail(sender=SENDER,
                       to=add, subject="Invite for " + stream_name,
                       body=stream_email_body + '\n' + stream_link)
    return


class HandleUser(webapp2.RequestHandler):
    def get(self):
        user = User.get_by_id(self.request.get('user_id'))
        if not user:
            return self.response.out.write("Not found!")
        self.response.headers['Content-Type'] = 'application/json'
        user_dict = user.to_dict()
        user_dict['owned_id_details'] = user.owned_id_details()
        user_dict['subscribed_id_details'] = user.subscribed_id_details()
        return self.response.out.write(json.dumps(user_dict, cls=MyEncoder))


def email_trends():
    leaders = Leaderboard.query().order(
        -Leaderboard.view_count).fetch(3)
    if not leaders:
        Leaderboard.refresh(LEADERBOARD_UPDATE_DURATION)
        leaders = Leaderboard.query().order(
            -Leaderboard.view_count).fetch(3)

    message = "Current leaders are: \n\t"
    for leader in leaders:
        message += leader.stream_id.id() + ", "
    return message


class HandleLeaderboard(webapp2.RequestHandler):
    def get(self):
        Leaderboard.refresh(LEADERBOARD_UPDATE_DURATION)


class HandleEmailCron(webapp2.RequestHandler):
    def get(self):
        time = datetime.datetime.time(datetime.datetime.now())
        meta = Meta.get_by_id('meta')
        if meta:
            duration = meta.email_duration
            if ((duration == 5) or
                (duration == 60 and time.minute == 0) or (
                    duration == 1440 and time.hour == 0 and time.minute == 0)):
                    for to in EMAIL_RCVR:
                        mail.send_mail(sender=SENDER,
                                       to=to, subject="[APT] Trending updates",
                                       body=email_trends())

    def post(self):
        duration = self.request.get('duration')
        meta = Meta.get_by_id('meta')
        if not meta:
            meta = Meta(id='meta')
        meta.email_duration = int(duration)
        meta.put()
        return self.redirect('/trending?duration='+duration)


class HandleSubsrciption(webapp2.RequestHandler):
    def post(self):
        if not populate_user()['logged_in']:
            return self.redirect('/')
        user_id = populate_user()['nickname']
        stream_id = self.request.get('stream_name')
        user = User.get_by_id(user_id)
        if not user:
            return self.response.out.write("Not Found!")
        user.subscribed_ids.append(Stream.get_by_id(stream_id).key)
        user.put()
        return self.redirect('/view?stream_name='+stream_id)


class HandleUnsubsrciption(webapp2.RequestHandler):
    def post(self):
        if not populate_user()['logged_in']:
            return self.redirect('/')
        user_id = populate_user()['nickname']
        stream_id = self.request.get('stream_name')
        user = User.get_by_id(user_id)
        if not user:
            return self.response.out.write("Not Found!")
        user.subscribed_ids = [sub for sub in user.subscribed_ids
                               if stream_id != sub.id()]
        user.put()
        return self.redirect('/view?stream_name='+stream_id)


class HandleStream(webapp2.RequestHandler):
    def show_trending(self):
        count = int(self.request.get('count', 3))
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

        # Increment View Count
        stream.view_count += 1
        stream.put()
        View(stream_id=stream.key).put()

        return self.response.out.write(json.dumps(stream.to_dict(),
                                                  cls=MyEncoder))

    def post(self):
        req = self.request
        data = populate_user()
        if not data['logged_in']:
            return self.redirect('/')
        user_id = data['nickname']
        stream_name = req.get('name')
        stream_tags = req.get('tags').split(',')
        stream_cover = req.get('cover') or DEFAULT_COVER
        stream_add_subscribers_email_list = req.get(
            'email_list').split(',')
        stream_email_body = req.get('email_body')
        if Stream.get_by_id(stream_name):
            data['msg'] = 'Sorry! Stream already exists.'
            template = JINJA_ENVIRONMENT.get_template('error.html')
            return self.response.write(template.render(data))
        stream = Stream(id=stream_name, tags=stream_tags,
                        cover_url=stream_cover).put()
        user = User.get_by_id(user_id)
        user.owned_ids.append(stream)
        user.put()
        # on successful insert, send email
        if(Stream.get_by_id(stream_name)):
            send_subscribtion_invite_email(stream_add_subscribers_email_list,
                                           stream_email_body, stream_name,
                                           self.request.url)
        return self.redirect('/manage')


class HandleSearch(webapp2.RequestHandler):
    def get(self):
        query = self.request.get('query')
        stream_list = []
        if query:
            for stream in Stream.query().fetch():
                if query in stream.key.id() or stream.check_tags(query):
                    stream_dict = stream.to_dict()
                    stream_list.append(stream_dict)
        data = populate_user()
        data['results'] = stream_list[:SEARCH_COUNT]
        data['results_count'] = len(stream_list)
        data['query'] = query
        template = JINJA_ENVIRONMENT.get_template('search.html')
        self.response.write(template.render(data))


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
        return self.redirect('/view?stream_name='+stream_id)


class HandleTrendingUI(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('trending.html')
        data = populate_user()
        data['streams'] = requests.get(
            domain(self.request.url) + '/stream?trending=true').json()
        data['duration'] = self.request.get('duration')
        return self.response.write(template.render(data))


class HandleManageUserUI(webapp2.RequestHandler):
    def get(self):
        if not populate_user()['logged_in']:
            return self.redirect('/')
        data = populate_user()
        data.update(requests.get(domain(self.request.url) + '/user',
                    params={'user_id': data['nickname']}).json())
        template = JINJA_ENVIRONMENT.get_template('manage.html')
        return self.response.write(template.render(data))


class HandleCreateStreamUI(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('create.html')
        self.response.write(template.render(populate_user()))


class HandleViewStreamUI(webapp2.RequestHandler):
    def process(self, image_arr, data):
        # reverse to show new first
        print image_arr
        data['image_ids'] = list(reversed(
            image_arr))[data['offset']:(data['offset'] + data['count'])]

    def get(self):
        data = populate_user()
        data['domain_url'] = domain(self.request.url)
        name = self.request.get('stream_name')
        if not name:
            template = JINJA_ENVIRONMENT.get_template('view_all.html')
            response = requests.get(
                domain(self.request.url) + '/stream').json()
            data['streams'] = response
            return self.response.write(template.render(data))
        response = requests.get(domain(self.request.url) + '/stream',
                                params={'stream_name': name})
        if data['logged_in']:
            user_id = data['nickname']
            data['is_subscribed'] = User.get_by_id(user_id).is_subscribed(name)
            data['is_owned'] = User.get_by_id(user_id).is_owned(name)
        data['stream_name'] = name
        data['offset'] = int(self.request.get('offset', IMG_OFF))
        data['count'] = int(self.request.get('count', IMG_CNT))
        if response.status_code == requests.codes.OK:
            image_ids = response.json()['image_ids']
            data['more'] = len(image_ids) > (data['offset'] + data['count'])
            data['prev'] = data['offset'] > 0
            self.process(image_ids, data)
        template = JINJA_ENVIRONMENT.get_template('view.html')
        self.response.write(template.render(data))


class HandleDeleteMulti(webapp2.RequestHandler):
    def post(self):
        body = json.loads(self.request.body)
        user_id = body['user_id']
        if not user_id or not User.get_by_id(user_id):
            return self.redirect('/')
        user = User.get_by_id(user_id)
        stream_ids = body['stream_ids']
        for stream_id in stream_ids:
            stream = Stream.get_by_id(stream_id)
            if not stream:
                continue
            stream_key = stream.key
            if user.is_owned(stream_id):
                stream_key.delete()
        user.owned_ids = [sub for sub in user.owned_ids
                          if sub.id() not in stream_ids]
        user.put()
        Leaderboard.refresh()


class HandleUnsubsrciptionMulti(webapp2.RequestHandler):
    def post(self):
        body = json.loads(self.request.body)
        user_id = body['user_id']
        if not user_id or not User.get_by_id(user_id):
            return self.redirect('/')
        user = User.get_by_id(user_id)
        stream_ids = body['stream_ids']
        user.subscribed_ids = [sub for sub in user.subscribed_ids
                               if sub.id() not in stream_ids]
        user.put()


class HandleLogin(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('index.html')
        self.response.write(template.render(populate_user()))


class HandleSocialUI(webapp2.RequestHandler):
    def get(self):
        template = JINJA_ENVIRONMENT.get_template('social.html')
        self.response.write(template.render(populate_user()))

class HandleFacebookLoginSuccessful(webapp2.RequestHandler):
    def get(self):
        print self.request.referer
        if self.request.referer != domain(self.request.url) + '/social':
            return self.redirect('/social')
        template = JINJA_ENVIRONMENT.get_template('facebook_login_successful.html')
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
    ('/cron', HandleEmailCron),
    ('/update_leaderboard', HandleLeaderboard),
    ('/delete_stream', HandleDeleteMulti),
    ('/subscribe', HandleSubsrciption),
    ('/unsubscribe', HandleUnsubsrciption),
    ('/unsubscribe_many', HandleUnsubsrciptionMulti),
    ('/error',HandleErrorUI),
    ('/social',HandleSocialUI),
    ('/facebook_login_successful',HandleFacebookLoginSuccessful)
])
