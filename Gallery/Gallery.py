import hashlib
import uuid
import os

from flask import Flask, request, Response, jsonify, make_response, render_template, session, redirect, url_for
from pymongo import MongoClient
from collections import namedtuple
from time import time
from functools import wraps
from azure import WindowsAzureMissingResourceError
from azure.storage import BlobService


app = Flask(__name__,  static_folder='static')
app.secret_key = "A0Zr98j/3yXZohar R~XHH!jmN]LWX/,Yaniv?RT"

AuthTuple = namedtuple('AuthTuple', ('username', 'timestamp'))

token_to_auth = {} # maps a token to the username and timestamp

DB_ADDRESS = 'zorki.cloudapp.net'
DB_PORT = 27017

SESSION_TIMEOUT = 30 * 60

ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'tif']
ACCOUNT_NAME = 'cloudgallery'
ACCOUNT_KEY = 'WOfbtZx/P2LGtg4wdorJN0iXe1/9ShQFi7Rk1LRrm/nLwYRLsv09zvcct+N/xiCsSYBBQ/xnsdg8C4d2sHZ57w=='
CONTAINER_NAME = 'images'


#### HTML FRONTEND ####

def requires_session_token(func):
    @wraps(func)
    def f(*args, **kwargs):
        if 'token' not in session:
            return redirect(url_for('login'))
        else:
            # make sure the token is valid
            token = session['token']

            if token not in token_to_auth:
                print "Token in session, but not in token_to_auth dict"
                session.pop('token')
                return redirect(url_for('login'))

            auth_tup = token_to_auth[token]
            if time() - auth_tup.timestamp > SESSION_TIMEOUT:
                # session timeout
                token_to_auth.pop(token)
                return redirect(url_for('login'))

            kwargs["username"] = auth_tup.username
            return func(*args, **kwargs)

    return f


@app.route('/', methods=['GET'])
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if 'token' in session:
            return redirect(url_for('albums'))

        return render_template('login.html', title="login")
    else:
        # POST
        username = request.form.get('username', None)
        password = request.form.get('password', None)

        if not username or not password:
            return render_template('login.html', title="login", error="Missing username or password")

        token = login_handler(username, password)

        if token:
            session['token'] = token
            return redirect(url_for('albums'))
        else:
            return render_template('login.html', title="login", error="Login failed")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        if 'token' in session:
            return redirect(url_for('albums'))

        return render_template('register.html', title="register")
    else:
        # POST
        username = request.form.get('username', None)
        password = request.form.get('password', None)

        if not username or not password:
            return render_template('register.html', title="register", error="Missing username or password")

        token = register_handler(username, password)

        if token:
            session['token'] = token
            return redirect(url_for('albums'))
        else:
            return render_template('register.html', title="register", error="Username is already taken")


@app.route('/logout', methods=['GET'])
@requires_session_token
def logout(username):
    session.pop('token')
    try:
        token_to_auth.pop(username)
    except KeyError:
        pass
    return redirect(url_for('login'))


@app.route('/albums', methods=['GET'])
@requires_session_token
def albums(username):
    albums_author, albums_write, albums_read = get_albums(username)
    album_name = request.args.get('album', None)
    message = request.args.get('message', None)

    albums = list(set(albums_author) | set(albums_write) | set(albums_read))

    if not album_name:
        return render_template('albums.html', title="albums", albums=albums, message=message)
    else:
        album = get_album(album_name, username)
        if not album:
            return render_template('albums.html', title="albums", 
                albums=albums, 
                message="no permissions to album {}".format(album_name))

        return render_template('albums.html', title="albums", albums=albums,
            album_name=album_name, images=album['images'], is_author = (username == album['author']), 
            is_write = (username in album['write']), 
            is_read = (username in album['write'] or username in album['read']), 
            message=message)


@app.route('/album/<album_name>/image/<image_name>', methods=['GET'])
@requires_session_token
def get_image(album_name, image_name, username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums

    requested_album = albums.find_one({"name": album_name})
    if not requested_album:
        return redirect(url_for('static', filename='image_not_found.gif'))

    if not (username in requested_album["write"] or username in requested_album["read"]):
        return redirect(url_for('static', filename='image_not_found.gif'))

    if image_name not in requested_album["images"]:
        return redirect(url_for('static', filename='image_not_found.gif'))

    try:
        blob_service = BlobService(account_name=ACCOUNT_NAME, account_key=ACCOUNT_KEY)
        data = blob_service.get_blob_to_bytes(CONTAINER_NAME, image_name)

        response = make_response(data)
        response.headers["Content-Disposition"] = "filename=%s.jpg" % image_name
        response.headers['Content-type'] = 'image/jpeg'
        return response
    except Exception as ex:
        # TODO: different image in this case?
        return redirect(url_for('static', filename='image_not_found.gif'))


@app.route('/new_album', methods=['POST'])
@requires_session_token
def create_new_album(username):
    # POST
    album_name = request.form.get('album_name', None)
    if album_name:
        album = create_album(album_name, username)
        if not album:
            return redirect(url_for('albums', message="album name already exists"))
        else:
            return redirect(url_for('albums', message="album created successfully", album=album_name))
    else:
        return redirect(url_for('albums', message="no album name"))


@app.route('/remove_album', methods=['POST'])
@requires_session_token
def remove_old_album(username):
    album_name = request.form.get('album_name', None)
    if not album_name:
        return redirect(url_for('albums', message="no album name")) 
    if remove_album(album_name, username):
        return redirect(url_for('albums', message="removed album successfully"))

    return redirect(url_for('albums', message="failed to remove album"))        


@app.route('/album/<album_name>/remove_image', methods=['POST'])
@requires_session_token
def remove_image(album_name, username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums

    requested_album = albums.find_one({"name": album_name})
    if not requested_album:
        return redirect(url_for('albums', album =album_name, message="album not found"))

    if not username in requested_album["write"]:
        return redirect(url_for('albums', album = album_name, message="permission denied"))

    image = request.form.get('image', '')
    if not image:
        return redirect(url_for('albums', album=album_name, message="no image was chosen for removal"))

    blob_service = BlobService(account_name=ACCOUNT_NAME, account_key=ACCOUNT_KEY)
    try:
        blob_service.delete_blob(CONTAINER_NAME, image)
    except WindowsAzureMissingResourceError:
        # Even if the file is not in the blob storage, we want to remove it from the album
        pass

    gallery_db.albums.update({'name': album_name}, {'$pull': {'images': image}})
    return redirect(url_for('albums', album=album_name))


@app.route('/album/<album_name>/add_image', methods=['POST'])
@requires_session_token
def add_image(album_name, username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums

    requested_album = albums.find_one({"name": album_name})
    if not requested_album:
        return redirect(url_for('albums', album =album_name, message="album not found"))

    if not username in requested_album["write"]:
        return redirect(url_for('albums', album = album_name, message="permission denied"))

    if 'image[]' not in request.files:
        return redirect(url_for('albums', album = album_name, message="no file uploaded"))

    for req_file in request.files.getlist('image[]'):
        file_name = uuid.uuid4().hex
        blob_service = BlobService(account_name=ACCOUNT_NAME, account_key=ACCOUNT_KEY)
        blob_service.put_block_blob_from_file(CONTAINER_NAME, file_name, req_file.stream)

        gallery_db.albums.update({'name': album_name}, {'$push': {'images': file_name}})

    return redirect(url_for('albums', album = album_name))


@app.route('/album/<album_name>/permissions', methods=['GET', 'POST'])
@requires_session_token
def modify_permission(album_name, username):
    if request.method == 'GET':
        message = request.args.get('message', None)

        gallery_db = connect_to_db()
        albums = gallery_db.albums

        album = albums.find_one({"name": album_name})
        if not album:
            return redirect(url_for('albums', album=album_name, message="no such album to display permissions for"))

        if album['author'] != username:
            return redirect(url_for('albums', album=album_name, message="no permissions to modify permissions"))            

        return render_template('permissions.html', album_name=album_name, title="permissions",
                               author=album['author'], write=album['write'], read=album['read'], message=message)
    else:
        # POST - /<permission>/<alter_operation>/<modified_username>
        permission = request.form.get('permission', '')
        alter_operation = request.form.get('alter_operation', '')
        modified_username = request.form.get('modified_username', '')

        if not (permission and alter_operation and modified_username):
            return redirect(url_for('modify_permission', album_name=album_name, message="missing permission alteration parameters"))            

        if permission not in ['read', 'write']:
            return redirect(url_for('modify_permission', album_name=album_name, message="no such permission level. accepts read/write levels"))

        if alter_operation not in ['add', 'remove']:
            return redirect(url_for('modify_permission', album_name=album_name, message="no such alter operation. accepts add/remove levels"))

        gallery_db = connect_to_db()
        doc = gallery_db.albums.find_one({"name": album_name}, {'author': 1})
        if not doc:
            return redirect(url_for('modify_permission', album_name=album_name, message="album does not exist"))

        if username != doc['author']:
            return redirect(url_for('modify_permission', album_name=album_name, message="no permission to modify permissions"))

        if gallery_db.auth_collection.count({"username": modified_username}) == 0:
            return redirect(url_for('modify_permission', album_name=album_name, message="unknown username"))

        if alter_operation == 'add':
            gallery_db.albums.update({'name': album_name}, {'$push': {permission: modified_username}})
        else:
            # DELETE
            gallery_db.albums.update({'name': album_name}, {'$pull': {permission: modified_username}})

        return redirect(url_for('modify_permission', album_name=album_name))


#### REST API #####


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
    token_to_return = uuid.uuid4().hex
    token_to_auth[token_to_return] = AuthTuple(username=username, timestamp=time())
    return token_to_return


def login_handler(username, password):
    gallery_db = connect_to_db()
    auth_collection = gallery_db.auth_collection

    record = auth_collection.find_one({'username': username,
                                       'password': hashlib.sha1(password).hexdigest()})

    if record:
        return set_token(username)

    return None


@app.route('/rest/login', methods=['GET'])
def rest_login():
    auth_details = request.authorization
    if not auth_details:
        return jsonify({'error':"no auth details"}) # TODO update error

    token = login_handler(auth_details.username, auth_details.password)

    if token:
        return jsonify({'token': token})
    else:
        return jsonify({'error': "you are off limits!!!"})


def register_handler(username, password):
    gallery_db = connect_to_db()
    if gallery_db.auth_collection.count({"username": username}) > 0:
        return None # username in use

    gallery_db.auth_collection.insert_one({"username": username,
                                           "password": hashlib.sha1(password).hexdigest()})
    return set_token(username)


@app.route('/rest/register', methods=['GET'])
def rest_register():
    json = request.json
    if not json:
        return jsonify({'error': 'no data passed'})

    username = json.get("username", None)
    password = json.get("password", None)
    if not (username and password):
        return jsonify({'error': "missing username or password"})

    token = register_handler(username, password)
    if token:
        return jsonify({'token': token})
    else:
        return jsonify({'error': 'username already in use'})


def get_album(album_name, username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums
    album_doc = albums.find_one({"name": album_name})
    if not album_doc:
        return None

    if not (username in album_doc['read'] or username in album_doc['write'] or username == album_doc['author']):
        return None 

    return album_doc

@app.route('/rest/album/<album_name>', methods=['GET'])
@requires_token
def rest_get_album(album_name, username):
    # returns an album object
    album = get_album(album_name, username)
    if not album:
        jsonify({'error': 'no permissions to album'})

    return jsonify({'name': album_name, 'author': album['author'], 'images': album['images']})


def create_album(album_name, username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums
    same_name_album = albums.count({"name": album_name})
    if same_name_album > 0:
        return None

    return albums.insert_one({"name": album_name, "author": username, "read": [], "write": [username], "images": []})

def remove_album(album_name, username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums
    album = albums.find_one({"name": album_name})
    if not album:
        return None
    if album['author'] != username:
        return None

    return albums.remove({"name": album_name})


@app.route('/rest/album/<album_name>', methods=['POST', 'DELETE'])
@requires_token
def rest_modify_album(album_name, username):
    # posts/removes a new album
    # fields to save: name, author, date and read permission and write permission
    # TODO maybe check if the insert was successful?
    if request.method == 'POST':
        if not create_album(album_name, username):
            return jsonify({'error': "album name exists"})

        return jsonify({'success': "album was created"})
    else:
        if not remove_album(album_name, username):
            return jsonify({'error': "failed to remove the album"})

        return jsonify({'success': "album was removed"})



def get_albums(username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums

    author_docs = albums.find({"author": username}, {'name': 1})
    write_docs = albums.find({"write": username}, {'name': 1})
    read_docs = albums.find({"read": username}, {'name': 1})

    author = [doc['name'] for doc in author_docs]
    write = [doc['name'] for doc in write_docs]    
    read = [doc['name'] for doc in read_docs]

    return author, write, read


@app.route('/rest/album', methods=['GET'])
@requires_token
def rest_get_album_list(username):
    # returns the album list for the user
    author, write, read = get_albums(username)

    return jsonify({"author": author, "write": write, "read": read})


@app.route('/rest/album/<album_name>/image/<image_name>', methods=['GET'])
@requires_token
def rest_get_image(album_name, image_name, username):
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
    data = blob_service.get_blob_to_bytes(CONTAINER_NAME, image_name)

    response = make_response(data)
    response.headers["Content-Disposition"] = "attachment; filename=%s" % image_name
    return response


@app.route('/rest/album/<album_name>/image', methods=['POST', 'DELETE'])
@requires_token
def rest_modify_image(album_name, username):
    gallery_db = connect_to_db()
    albums = gallery_db.albums

    requested_album = albums.find_one({"name": album_name})
    if not requested_album:
        return jsonify({'error': "album does not exist"})

    if not username in requested_album["write"]:
        return jsonify({'error': "no permission to post images"})

    if request.method == 'POST':
        req_file = request.json.get('data', '')
        if not req_file:
            return jsonify({'error': "no images"})

        file_name = uuid.uuid4().hex
        blob_service = BlobService(account_name=ACCOUNT_NAME, account_key=ACCOUNT_KEY)
        blob_service.put_block_blob_from_bytes(CONTAINER_NAME, file_name, req_file.decode("base64"))

        gallery_db.albums.update({'name': album_name}, {'$push': {'images': file_name}})
        return jsonify({'success': "file uploaded"})
    else:
        # DELETE
        image = request.json.get('image', '')
        if not image:
            return jsonify({'error': 'no image name'})

        blob_service = BlobService(account_name=ACCOUNT_NAME, account_key=ACCOUNT_KEY)
        try:
            blob_service.delete_blob(CONTAINER_NAME, image)
        except WindowsAzureMissingResourceError:
            # Even if the file is not in the blob storage, we want to remove it from the album
            pass

        gallery_db.albums.update({'name': album_name}, {'$pull': {'images': image}})
        return jsonify({'success': "file deleted"})


@app.route('/rest/album/<album_name>/permissions/<permission>/<modified_username>', methods=['POST', 'DELETE'])
@requires_token
def rest_modify_permission(album_name, permission, modified_username, username):
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


if __name__ == '__main__':
    app.run(debug=True)