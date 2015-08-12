import tika.parser
import datetime
from elasticsearch import Elasticsearch
from Common import *
from azure.storage import BlobService
from pymongo import MongoClient
from time import sleep

def execute_pending_tasks(elastic_search_object, task_collection):
    while True:
        pending_tasks = task_collection.find({'status': 'pending'})
        if pending_tasks.count() > 0:
            for task in pending_tasks:
                print "the task was ", task
                # execute the task, update the status accordingly
                task_status = execute_given_task(elastic_search_object, task)
                task_collection.update(task, {"$set": {"status": task_status}})

                print "task status after execution: ", task_status
                
        else:
            print "no task to execute"
            # don't waste cpu - use sleep
            sleep(1)



def execute_given_task(elastic_search_object, task):
    #try:
        # Parse the data and update the task's status to "success" on success
        #If failed on any stage, the task's status would be "failed"
    blob_service = BlobService(account_name=BLOB_ACCOUNT_NAME, account_key=BLOB_ACCOUNT_KEY)
    data = blob_service.get_blob_to_bytes(BLOB_CONTAINER_NAME, task["filename"])
    parsed_data = tika.parser.from_buffer(data)
    current_user = task["username"]
    es_record = {'uploader': current_user, 'timestamp': datetime.datetime.utcnow().isoformat(), 'parsed_data': parsed_data}
    res = elastic_search_object.index(index="study_buddy", doc_type="parsed_file", body=es_record)
    task_status = "success"
    #except:
    #    task_status = "failure"

    return task_status


if __name__ == "__main__":
    collection = MongoClient(DB_ADDRESS, DB_PORT).studybuddy.task_collection
    es = Elasticsearch(hosts=[ES_ADDRESS])
    execute_pending_tasks(es, collection)
