
import uuid

from flask import Flask, request, jsonify
from pymongo import MongoClient
from flask.ext.login import LoginManager, current_user, login_required, UserMixin
from flask.ext.bcrypt import Bcrypt
from RecurringFileHandler import ChecksumRecurringFileHandler
from azure.storage import BlobService
from Common import *

app = Flask(__name__,  static_folder='static')
app.secret_key = "A0Zr98j/3yXZohar R~XHH!jmN]LWX/,Yaniv?RT"

login_manager = LoginManager()
login_manager.init_app(app)

bcrypt = Bcrypt(app)


### Login management ###


class User(UserMixin):
	''' 
	This class defines the user and saves it's username 
	'''

    def __init__(self, username):
        super(User, self).__init__()
        self.username = username

    def get_id(self):
        return self.username


def login_handler(username, password):
	# handles the login request - asserts the password and username are correct
    auth_collection = get_db().auth_collection
    record = auth_collection.find_one(
        {'username': username}, {'username': 1, 'password': 1})

    if not record or not bcrypt.check_password_hash(record['password'], password):
        return None

    # the authentication was correct - return the user object
    return User(record['username']) if record is not None else None


@login_manager.request_loader
def load_user_from_request(request):
	# this function is called by flask on request 
    json = request.get_json()

    username = json.get('username', None)
    password = json.get('password', None)

    if not username or not password:
    	# missing information
        return None

    return login_handler(username, password)


### Flask ###

@app.route('/register', methods=['POST'])
def register():
    json = request.get_json()

    username = json.get('username', None)
    password = json.get('password', None)

    if not username or not password:
        return jsonify(status=400, message='Missing username or password')

    auth_collection = get_db().auth_collection

    record = auth_collection.find_one({'username': username}, {'username': 1})
    if record is not None:
        return jsonify(status=400, message='Username already taken')

    auth_collection.insert_one({"username": username,
                                "password": bcrypt.generate_password_hash(password)})

    return jsonify(status=200, message='Account created successfully')


@login_manager.unauthorized_handler
def unauthorized():
	# this handler is called (automaticaly) by flask login when the user is unauthorized
    return jsonify(status=400, message='Unauthorized')


@app.route('/upload_document', methods=['POST'])
@login_required
def upload_documents():
    data = request.json.get('data', None)
    if not data:
        return jsonify(status=400, message='No file content passed')

    data = data.decode("base64")
    upload_handler = get_upload_handler()

    # force is a flag that signals to upload the current file even if it was uploaded before
    force = request.json.get('force', None)
    if force is None or force.lower() != "true":
        if upload_handler.is_file_already_uploaded(data, current_user.get_id()):
            return jsonify(status=400, message='File content was already uploaded. Force upload by adding the force boolean')

    blob_service = BlobService(account_name=BLOB_ACCOUNT_NAME, account_key=BLOB_ACCOUNT_KEY)
    filename = uuid.uuid4().hex
    # put the data in the container using a random filename
    blob_service.put_block_blob_from_bytes(BLOB_CONTAINER_NAME, filename, data)

    task_collection = get_db().task_collection
    
    # update the task db with the new task (which is parsing the new data file)
    task_id = upload_handler.update_uploaded_file(filename, data, current_user.get_id())

    return jsonify(status=200, message='Task created successfully', task_id=task_id)


@app.route('/get_task_status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    task_status = get_upload_handler().get_task_status(task_id)

    if task_status is None:
        return jsonify(status=400, message="Task id does not exist")

    return jsonify(status=200, task_status=task_status)


### General ###


def get_db():
    client = MongoClient(DB_ADDRESS, DB_PORT)
    # the collection in this case is called studybuddy
    return client.studybuddy


def get_upload_handler():
    return ChecksumRecurringFileHandler(get_db())


### Main ###

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
