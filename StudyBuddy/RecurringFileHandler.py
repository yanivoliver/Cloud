import datetime
import hashlib
import pymongo
from bson.objectid import ObjectId


class RecurringFileHandler(object):
	'''
	An interface for uploading recurring files
	'''

    def __init__(self, db, *args, **kwargs):
        self._db = db

    def get_collection(self, name):
        return self._db[name]

    def update_uploaded_file(self, *args, **kwargs):
    	'''
    	update new file's upload information 
    	returns a unique id representing the uploaded file object
    	'''
        pass

    def is_file_already_uploaded(self, *args, **kwargs):
    	'''
    	checks if the file was already uploaded and parsed without failures
    	returns true if the file should be allowed to be uploaded
    	and false otherwise
    	'''
        pass

    def get_task_status(self, task_id, *args, **kwargs):
    	'''
    	returns the task's status if such a task exists, and None otherwise
    	'''
        pass


class ChecksumRecurringFileHandler(RecurringFileHandler):
    ''' 
    Checksum recurring file handler, that uses sha256 for the checksum 
    '''

    def __init__(self, *args, **kwargs):
        super(ChecksumRecurringFileHandler, self).__init__(*args, **kwargs)
        self._upload_collection = self.get_collection("upload_collection")
        self._task_collection = self.get_collection("task_collection")

    def update_uploaded_file(self, filename, data, username, *args, **kwargs):
        checksum = hashlib.sha256(data).hexdigest()
        self._upload_collection.insert_one({'username': username, 'filename': filename, 'checksum': checksum, 'timestamp': datetime.datetime.utcnow().isoformat()})
        result = self._task_collection.insert_one({"username": username, "status": "pending", "filename": filename, "timestamp": datetime.datetime.utcnow().isoformat()})

        return str(result.inserted_id)

    def is_file_already_uploaded(self, data, username, *args, **kwargs):
        checksum = hashlib.sha256(data).hexdigest()
        try:
        	# sort the records by timestamp in order to retreive the most recent record
            upload_record = self._upload_collection.find(
                {'username': username, 'checksum': checksum}, {'filename': 1}).sort("timestamp", pymongo.DESCENDING).limit(1)
        except:
            # failed - upload collection is empty, so the file was not already
            # uploaded
            return False

        if upload_record.count() == 0:
            return False

        record = upload_record.next()

        task_record = self._task_collection.find_one({'filename': record['filename']}, {'status': 1})

        # This shouldn't happen, but if it does, we'll assume that the file wasn't previously uploaded
        if task_record is None:
            return False

        return False if task_record['status'] == 'failed' else True

    def get_task_status(self, task_id, *args, **kwargs):
        task_record = self._task_collection.find_one({'_id': ObjectId(task_id)}, {'status': 1})

        return None if task_record is None else task_record['status']