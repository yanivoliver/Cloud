import hashlib
import uuid
import os

from flask import Flask, request, Response, jsonify, make_response
from pymongo import MongoClient
from collections import namedtuple
from time import time
from functools import wraps
from azure.storage import BlobService


app = Flask(__name__)
AuthTuple = namedtuple('AuthTuple', ('username', 'timestamp'))

token_to_auth = {} # maps a token to the username and timestamp

DB_ADDRESS = 'zorki.cloudapp.net'
DB_PORT = 27017

SESSION_TIMEOUT = 30 * 60

ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'tif']
UPLOAD_FOLDER = '/Users/zohar/GitHub/Gallery/images'
ACCOUNT_NAME = 'cloudgallery'
ACCOUNT_KEY = 'WOfbtZx/P2LGtg4wdorJN0iXe1/9ShQFi7Rk1LRrm/nLwYRLsv09zvcct+N/xiCsSYBBQ/xnsdg8C4d2sHZ57w=='
CONTAINER_NAME = 'images'


def connect_to_db():
    client = MongoClient(DB_ADDRESS, DB_PORT)
    gallery_db = client.gallery
    return gallery_db


def requires_token(func):
    @wraps(func)
    def f(*args, **kwargs):
        json = request.json
        if json:
            token = json.get("token", None)
        if not json or not token or token not in token_to_auth:
            return jsonify({'error': "you are off limits!!!"})
        else:
            # make sure the token is valid
            auth_tup = token_to_auth[token]
            if time() - auth_tup.timestamp > SESSION_TIMEOUT:
                # session timeout
                return jsonify({'error': "session timed-out!"})

            kwargs["username"] = auth_tup.username
            return func(*args, **kwargs)

    return f


def set_token(username):
    token_to_return = 'zohar'#uuid.uuid4().hex
    token_to_auth[token_to_return] = AuthTuple(username=username, timestamp=time())
    return token_to_return


@app.route('/login', methods=['GET'])
def login():
    auth_details = request.authorization
    if not auth_details:
        return jsonify({'error':"no auth details"}) # TODO update error

    gallery_db = connect_to_db()
    auth_collection = gallery_db.auth_collection

    record = auth_collection.find_one({'username': auth_details.username,
                                       'password': hashlib.sha1(auth_details.password).hexdigest()})
    if record:
        return jsonify({'token': set_token(auth_details.username)})
    else:
        return jsonify({'error': "you are off limits!!!"})


@app.route('/register', methods=['GET'])
def register():
    json = request.json
    if not json:
        return jsonify({'error': 'no data passed'})

    username = json.get("username", None)
    password = json.get("password", None)
    if not (username and password):
        return jsonify({'error': "missing username or password"})

    gallery_db = connect_to_db()
    if gallery_db.auth_collection.count({"username": username}) > 0:
        return jsonify({'error': 'username already in use'})

    gallery_db.auth_collection.insert_one({"username": username,
                                           "password": hashlib.sha1(password).hexdigest()})

    return jsonify({'token': set_token(username)})


@app.route('/album/<album_name>', methods=['GET'])
@requires_token
def get_album(album_name, username):
    # returns an album object
    gallery_db = connect_to_db()
    albums = gallery_db.albums
    album_doc = albums.find_one({"name": album_name})
    if not album_doc:
        return jsonify({'error': 'no such album'})

    print album_doc
    if not (username in album_doc['read'] or username in album_doc['write']):
        return jsonify({'error': 'no permissions to album'})

    return jsonify({'name': album_name, 'author': album_doc['author'], 'images': album_doc['images']})


@app.route('/album/<album_name>', methods=['POST'])
@requires_token
def post_album(album_name, username):
    # posts a new album
    # fields to save: name, author, date and read permission and write permission
    gallery_db = connect_to_db()
    albums = gallery_db.albums
    same_name_album = albums.count({"name": album_name})
    if same_name_album > 0:
        return jsonify({'error': "album name exists"})

    res = albums.insert_one({"name": album_name, "author": username, "read": [], "write": [username], "images": []})
    # TODO maybe check if the insert was successful?
    return jsonify({'success': "album was created"})


@app.route('/album', methods=['GET'])
@requires_token
def get_album_list(username):
    # returns the album list for the user
    gallery_db = connect_to_db()
    albums = gallery_db.albums

    author_docs = albums.find({"author": username}, {'name': 1})
    write_docs = albums.find({"write": username}, {'name': 1})
    read_docs = albums.find({"read": username}, {'name': 1})

    author = [doc['name'] for doc in author_docs]
    write = [doc['name'] for doc in write_docs]    
    read = [doc['name'] for doc in read_docs]

    return jsonify({"author": author, "write": write, "read": read})


@app.route('/album/<album_name>/image/<image_name>', methods=['GET'])
@requires_token
def get_image(album_name, image_name, username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums

    requested_album = albums.find_one({"name": album_name})
    if not requested_album:
        return jsonify({'error': "album does not exist"})

    if not (username in requested_album["write"] or username in requested_album["read"]):
        return jsonify({'error': "no permission to get images"})

    if image_name not in requested_album["images"]:
        return jsonify({'error': "no such image in album"})

    blob_service = BlobService(account_name = ACCOUNT_NAME, account_key = ACCOUNT_KEY)
    data = blob_service.get_blob_to_text(CONTAINER_NAME, image_name)

    response = make_response(data.decode("base64"))
    response.headers["Content-Disposition"] = "attachment; filename=%s" % image_name
    return response


@app.route('/album/<album_name>/image', methods=['POST'])
@requires_token
def post_image(album_name, username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums

    requested_album = albums.find_one({"name": album_name})
    if not requested_album:
        return jsonify({'error': "album does not exist"})

    if not username in requested_album["write"]:
        return jsonify({'error': "no permission to post images"})

    req_file = request.json.get('data', '')
    if not req_file:
        return jsonify({'error': "no images"})

    file_name = uuid.uuid4().hex
    blob_service = BlobService(account_name = ACCOUNT_NAME, account_key = ACCOUNT_KEY)
    blob_service.put_block_blob_from_text(CONTAINER_NAME, file_name, req_file)

    gallery_db.albums.update({'name': album_name}, {'$push': {'images': file_name}})
    return jsonify({'success': "file uploaded"})


@app.route('/album/<album_name>/permissions/<permission>/<modified_username>', methods=['POST', 'DELETE'])
@requires_token
def add_permission(album_name, permission, modified_username, username):
    if permission not in ['read', 'write']:
        return jsonify({'error': 'no such permission level. accepts read/write levels'})

    gallery_db = connect_to_db()
    doc = gallery_db.albums.find_one({"name": album_name}, {'author': 1})
    if not doc:
        return jsonify({'error': 'album does not exist'})

    if username != doc['author']:
        return jsonify({'error': 'no permission to modify permissions'})

    if gallery_db.auth_collection.count({"username": modified_username}) == 0:
        return jsonify({'error': 'unknown username {}'.format(modified_username)})

    if request.method == 'POST':
        gallery_db.albums.update({'name': album_name}, {'$push': {permission: modified_username}})
        return jsonify({'success': 'added permission of {} to {}'.format(modified_username, permission)})
    else:
        # DELETE
        gallery_db.albums.update({'name': album_name}, {'$pull': {permission: modified_username}})
        return jsonify({'success': 'removed permission of {} from {}'.format(modified_username, permission)})


# TODO - add option to remove images
# manage permissions - at the mongodb
# add register option

if __name__ == '__main__':
    app.run(debug=True)