#coding=utf-8
#!/usr/bin/python

import os
import urllib
import re
import sys
from datetime import datetime

# 3rd-party libs must be in "lib" folder if wee in App Engine env.
dirname = os.path.dirname(__file__)
lib_dir = os.path.join(dirname, "lib")
sys.path.append(lib_dir)

import gdata.media
import gdata.youtube.service

from flask import Flask
from flask import request
from flask import redirect
from flask import render_template
from flask import url_for
from flask import flash
from flask import session
from flask import Response
from flask import jsonify

import wtforms
import wtforms.validators


class Config():
    DEBUG = False

    SECRET_KEY = ")(@#OKjs;xf89u02389u1jk23__=)"
    SESSION_COOKIE_NAME = "YT_DEMO_APP"


USER_FEED_URL = "http://gdata.youtube.com/feeds/api/users/%s/uploads"
CATEGORIES_URL = "http://gdata.youtube.com/schemas/2007/categories.cat"

# Change it
YT_ACCESS = {
    "email": "",
    "password": "",
    "developer_key": ""
}

YT_USERNAME = "UC0MSiA7rpU25cD9y07UsBYA"

# ----------------


xml = urllib.urlopen(CATEGORIES_URL).read()

terms = re.findall(r"term='(.+?)'", xml)
labels = re.findall(r"label='(.+?)'", xml)
labels = [l.replace("&amp;", "&") for l in labels]

CATEGORIES_CHOICES = zip(terms, labels)


class FormVideo(wtforms.Form):
    title = wtforms.TextField(
        label=u"Video title*",
        validators=[
            wtforms.validators.Required(message=u"Title is required field!")
        ]
    )
    description = wtforms.TextAreaField(
        label=u"Description"
    )
    category = wtforms.SelectField(
        label=u"Category",
        choices=CATEGORIES_CHOICES
    )
    tags = wtforms.TextField(
        label=u"Keywords",
        description=u"Comma separated strings, i.e. \"cats, funny\"."
    )


app = Flask(__name__)
app.config.from_object(Config)


@app.route("/upload", methods=["GET", "POST"])
def view_upload():

    if "GET" == request.method:
        form = FormVideo()
        return render_template("view_upload_prepare.html", form=form)

    if "POST" == request.method:
        form = FormVideo(request.form)
        if not form.validate():
            return render_template("view_upload_prepare.html", form=form)

        params = form.data
        group = gdata.media.Group(
            title=gdata.media.Title(text=params["title"]),
            description=gdata.media.Description(description_type='plain',
                                                text=params["description"]),
            keywords=gdata.media.Keywords(text=params["tags"]),
            category=gdata.media.Category(text=params["category"])
        )

        entry = gdata.youtube.YouTubeVideoEntry(media=group)

        try:
            yt = gdata.youtube.service.YouTubeService(**YT_ACCESS)
            yt.ssl = False
            yt.ProgrammaticLogin()
            response = yt.GetFormUploadToken(entry)

        except gdata.youtube.service.YouTubeError, e:
            flash(u"Error occured. Please try later.")
            return render_template("view_upload_prepare.html", form=form)


        post_url, token = response
        next_url = url_for("view_upload_callback", _external=True)

        # Falsh error security if https. I dnon't know why.
        post_url = post_url.replace("https", "http")

        # Wee provide two callback urls:
        # usal HTTP redirect and JSON response for AJAX.
        next_url = url_for("view_upload_callback", _external=True)
        next_url_ajax = url_for("view_upload_callback_ajax", _external=True)

        upload_url = "%s?nexturl=%s" % (post_url, next_url)
        upload_url_ajax = "%s?nexturl=%s" % (post_url, next_url_ajax)

        return render_template("view_upload_form.html",
                                upload_url=upload_url, token=token,
                                upload_url_ajax=upload_url_ajax, **params)


@app.route("/upload_callback")
def view_upload_callback():

    video_id = request.args.get("id")
    video_status = request.args.get("status")

    # Trivial check.
    if not (video_status == "200" and video_id):
        flash(u"Wrong URL params.", "error")
        return redirect(url_for("view_upload"))

    # Validate video with API.
    yt = gdata.youtube.service.YouTubeService(**YT_ACCESS)
    yt.ProgrammaticLogin()

    try:
        entry = yt.GetYouTubeVideoEntry(video_id=video_id)
    except gdata.youtube.service.RequestError, e:
        flash(u"Bad request.", "error")
        return redirect(url_for("view_upload"))

    flash(u"Upload successfull.", "success")
    url = url_for("view_video", video_id=video_id, _external=True)
    return redirect(url)


@app.route("/upload_callback_ajax")
def view_upload_callback_ajax():

    # This JSON will be returned.
    struct = {
        "success": False,
        "message": u"",
        "url": u""
    }

    video_id = request.args.get("id")
    video_status = request.args.get("status")

    # Trivial check.
    if not (video_status == "200" and video_id):
        struct["message"] = u"Wrong params."
        return jsonify(struct)

    # Validate video with API.
    yt = gdata.youtube.service.YouTubeService(**YT_ACCESS)
    yt.ProgrammaticLogin()

    try:
        entry = yt.GetYouTubeVideoEntry(video_id=video_id)
    except gdata.youtube.service.RequestError, e:
        struct["message"] = u"Wrong request."
        return jsonify(struct)

    struct["success"] = True
    struct["message"] = u"Upload successfull."
    struct["url"] = url_for("view_video", video_id=video_id, _external=True)

    return jsonify(struct)


@app.route("/v/<video_id>")
def view_video(video_id):
    yt = gdata.youtube.service.YouTubeService(**YT_ACCESS)
    yt.ProgrammaticLogin()

    try:
        entry = yt.GetYouTubeVideoEntry(video_id=video_id)
    except gdata.service.RequestError, e:
        flash(u"Video not found", "error")
        return redirect(url_for("view_frontpage"))

    upload_result = yt.CheckUploadStatus(entry)
    if upload_result:
        upload_status, upload_message = upload_result
    else:
        upload_status, upload_message = None, None

    return render_template("view_video.html", video_id=video_id, entry=entry,
                    upload_status=upload_status, upload_message=upload_message)


@app.route("/")
def view_frontpage():
    return render_template("view_frontpage.html")


@app.route("/videos")
def view_all_videos():
    yt = gdata.youtube.service.YouTubeService(**YT_ACCESS)
    yt.ProgrammaticLogin()

    uri = USER_FEED_URL % YT_USERNAME
    feed = yt.GetYouTubeVideoFeed(uri)
    return render_template("view_all_videos.html", feed=feed.entry)


@app.errorhandler(404)
def view_404(e):
    return render_template("view_404.html"), 404


@app.errorhandler(500)
def view_500(e):
    return render_template("view_500.html"), 500



def filter_video_id(url):
    """
    Gets video of id from Youtube entity's url.
    """
    return url.split("/")[-1]


def filter_video_duration(seconds):
    try:
        seconds = int(seconds)
    except:
        return "unknown"

    mins, secs = divmod(seconds, 60)
    return "%2d:%02d" % (mins, secs)


def filter_video_date(date, frmt):
    """
    Turns "2012-11-03T14:24:19.000Z" to formatted datetime.
    """
    args = map(int, re.findall(r"\d+", date))[:6]
    return datetime(*args).strftime(frmt)



# Register filter in Jinja env.
app.jinja_env.filters["filter_video_id"] = filter_video_id
app.jinja_env.filters["filter_video_date"] = filter_video_date
app.jinja_env.filters["filter_video_duration"] = filter_video_duration


if __name__ == "__main__":
    app.run(port=5000)
