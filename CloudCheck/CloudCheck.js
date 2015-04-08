// TODO: Ask Yaron about the displaying of the 'completed' attribute in exercises
// TODO: Make sure all responses are JSON responses

var mongo = require('mongodb').MongoClient;
var express = require('express');
var auth = require('basic-auth');
var body_parser = require('body-parser')
var assert = require('assert');
var busboy = require('connect-busboy');
var fs = require('fs');
var crypto = require('crypto');

// TODO: Add delete handlers for deleting students and files from existing exercises
ENDPOINTS = {'GET': {'/ping': ping_handler, 
					 '/': endpoints_handler, 
					 '/exercises': get_exercises_handler,
					 '/exercises/:id': get_exercise_by_id_handler,
					 '/exercises/:id/:path': get_exercise_file_handler},
			 'PUT': {'/exercises/:id': exercise_add_handler, 
			 		 '/exercises/:id/student': add_student_to_excersise_handler,
			 		 '/exercises/:id/file': add_file_to_excersise_handler},
			 'DELETE': {'/exercises/:id/student/:student': remove_student_from_excersise_handler,
			 		    '/exercises/:id/file/:file': remove_file_from_excersise_handler}};

SECURE_ENDPOINTS = {'GET': {'/ping': false, 
							'/': false, 
							'/exercises': false, 
							'/exercises/:id': false,
							'/exercises/:id/:path': true},
					'PUT': {'/exercises/:id': true,
							'/exercises/:id/student': true,
							'/exercises/:id/file': true},
					'DELETE': {'/exercises/:id/student/:student': true,
							   '/exercises/:id/file/:file': true}};

SERVER_PORT = 8080;

MONGODB_URL = 'mongodb://localhost:27017/cloudcheck';

USERNAME = 'yaron';
PASSWORD = 'MCMIITAGWVOUEG';

var app = express(); 
load_endpoints(app);

var server = app.listen(SERVER_PORT, function() {
	var host = server.address().address;
	var port = server.address().port;
	console.log('CloudCheck listening at http://%s:%s', host, port);
});

function load_endpoints(app) {
	app.use(body_parser.json());
	app.use(busboy());

	for (var key in ENDPOINTS['GET']) {
		if (SECURE_ENDPOINTS['GET'][key]) {
			app.get(key, auth_handler);
		}
    	app.get(key, ENDPOINTS['GET'][key]);
	}
	for (var key in ENDPOINTS['PUT']) {
		if (SECURE_ENDPOINTS['PUT'][key]) {
			app.put(key, auth_handler);
		}		
	    app.put(key, ENDPOINTS['PUT'][key]);
	}
	for (var key in ENDPOINTS['DELETE']) {
		if (SECURE_ENDPOINTS['DELETE'][key]) {
			app.delete(key, auth_handler);
		}		
	    app.delete(key, ENDPOINTS['DELETE'][key]);
	}
}

function auth_handler(req, res, next) {
	var credentials = auth(req);

	if (!credentials || credentials.name != USERNAME || credentials.pass != PASSWORD) {
		res.status(403).json('This page requires authentication. Invalid username or password');
		return;
	}

	next();
}

function ping_handler(req, res) {
	res.json({'ping': 'pong'});
}

function endpoints_handler(req, res) {
	var endpoints = {"endpoints": []}
	for (var type in ENDPOINTS) {
		for (var endpoint in ENDPOINTS[type]) {
			endpoints["endpoints"].push(type + " " + endpoint);
		}
	}
	res.json(endpoints);
}

// TODO: Handler completed=true flag as well
function get_exercises_handler(req, res) {
	var get_exercises = function(db) { 
		var collection = db.collection('exercises');
		collection.find({}, {'id': 1, 'name': 1, 'version': 1, '_id': 0}).toArray(function(err, docs) {
    		assert.equal(err, null);
    		res.json(docs);
		}); 
	}

	mongo.connect(MONGODB_URL, function(err, db) {
		assert.equal(null, err);
		get_exercises(db);
	});	

}

function get_exercise_by_id_handler(req, res) {
	var get_exercise_by_id = function(db) { 
		var collection = db.collection('exercises');
		collection.find({'id': req.params.id}, {'id': 0, '_id': 0}).toArray(function(err, docs) {
    		assert.equal(err, null);
		    assert.equal(1, docs.length);    		
    		res.json(docs[0]);
		}); 
	}

	mongo.connect(MONGODB_URL, function(err, db) {
		assert.equal(null, err);
		get_exercise_by_id(db);
	});	
}

function get_exercise_file_handler(req, res) {
	res.download(__dirname + '/files/' + req.params.id + "_" + req.params.path, req.params.path, function(err) {
		if (err) {
			res.status(404).json({"error": 
				{"message": "exercise '" + req.params.id + "' does not have a '" + req.params.path + "' file.",
    			 "code": 404}});
		}
	});
}

function exercise_add_handler(req, res) {
	var insert_document = function(db, record) { 
		var collection = db.collection('exercises');
		collection.insert(record, function(err, result) {
		    assert.equal(err, null);
			console.log("Inserted exercise document");
			res.json({"success": {"message": "Inserted new exercise", "code": 200}});
			db.close();
		});
	}

	// TODO: Check if req.params.id already exists in the DB. If so, override it
	if (req.body.hasOwnProperty('name') && req.body.hasOwnProperty('version') && req.body.hasOwnProperty('comment')) {
		var record = {'id': req.params.id,
					  'name': req.body.name,
					  'version': req.body.version,
					  'comment': req.body.comment,
					  'published_at': new Date().toISOString(),
					  'completed': false,
					  'files': [],
					  'students': [] };

		mongo.connect(MONGODB_URL, function(err, db) {
			assert.equal(null, err);
			insert_document(db, record);
		});	
	} else {
		res.status(400).send("Missing required fields");
	}
}

// TODO: Handle errors, such as invalid exercise id
function add_student_to_excersise_handler(req, res) {
	var update_document = function(db, exercise_id, student) { 
		var collection = db.collection('exercises');
		collection.find({'id': exercise_id}).toArray(function(err, docs) {
		    assert.equal(err, null);
		    assert.equal(1, docs.length);
		    console.log("Found the following records");
		    console.dir(docs);

		    var students = docs[0].students;
		    students.push(student);
		    
    		collection.update({'id': exercise_id}, { $set: { 'students': students } }, function(err, result) {
			    assert.equal(err, null);
				console.log("update exercise student");
				res.json({"success": {"message": "update new student to exercise", "code": 200}});
				db.close();
			});
		});      
	}

	if (req.body.hasOwnProperty('name') && req.body.hasOwnProperty('id')) {
		var record = {'id': req.body.id,
					  'name': req.body.name };

		mongo.connect(MONGODB_URL, function(err, db) {
			assert.equal(null, err);
			update_document(db, req.params.id, record);
		});	
	} else {
		res.status(400).send("Missing required fields");
	}

}

function add_file_to_excersise_handler(req, res) {
	var update_document = function(db, exercise_id, file) { 
		var collection = db.collection('exercises');
		collection.find({'id': exercise_id}).toArray(function(err, docs) {
		    assert.equal(err, null);
		    assert.equal(1, docs.length);
		    console.log("Found the following records");
		    console.dir(docs);

		    var files = docs[0].files;
		    var updated_files = files.slice(0);
		    for (id in files) {
		    	if (files[id].path === file.path) {
		    		console.log("File already exists in DB, removing it");
		    		updated_files.splice(updated_files.indexOf(files[id]), 1);
		    	}
		    }
		    updated_files.push(file);
		    
    		collection.update({'id': exercise_id}, { $set: { 'files': updated_files } }, function(err, result) {
			    assert.equal(err, null);
				console.log("update exercise file");
                res.json({"success": {"message": "File uploaded succesfully", "code": 200}});
				db.close();
			});
		});      
	}

	if (req.busboy) {
        req.busboy.on('file', function(fieldname, file, filename) {
        	if (fieldname != "manifest") {
        		res.status(400).json({"error": {"message": "Missing 'manifest' field", "code": 400}});
        		return;
        	}

            console.log("Uploading: " + filename);

            var full_filename = __dirname + '/files/' + req.params.id + "_" + filename
            var fstream = fs.createWriteStream(full_filename);
            file.pipe(fstream);
            fstream.on('close', function () {
                console.log("Upload Finished of " + filename);

				var fd = fs.createReadStream(full_filename);
				var hash = crypto.createHash('sha1');
				hash.setEncoding('hex');

				fd.on('end', function() {
				    hash.end();
				    sha1_hash = hash.read();
				    console.log("File's hash is " + sha1_hash);

				    filesize = fs.statSync(full_filename)["size"];
				    console.log("File's size is " + filesize);

				    file_record = {"path": filename, "sha1": sha1_hash, "size": filesize};

					mongo.connect(MONGODB_URL, function(err, db) {
						assert.equal(null, err);
						update_document(db, req.params.id, file_record);
					});
				});

				fd.pipe(hash);                
            });
            fstream.on('error', function(err) {
            	console.log("File " + filename + " failed uploading");
            	res.result(400).json({"error": {"message": "File upload failed", "code": 400}});
       		});
		});

    	req.pipe(req.busboy); 
	} else {
		res.status(400).json({"error": {"message": "Missing file data", "code": 400}});
	}
}

function remove_student_from_excersise_handler(req, res) {
	var update_document = function(db, exercise_id, student_id) { 
		var collection = db.collection('exercises');
		collection.find({'id': exercise_id}).toArray(function(err, docs) {
		    assert.equal(err, null);
		    assert.equal(1, docs.length);
		    console.log("Found the following records");
		    console.dir(docs);

		    var students = docs[0].students;
		    var updated_students = students.slice(0);
		    var student_removed = false
		    for (student_index in students) {
		    	if (students[student_index].id === student_id) {
		    		console.log("Removing student from exercise");
		    		updated_students.splice(updated_students.indexOf(students[student_index]), 1);
		    		student_removed = true
		    	}
		    }

		    if (!student_removed) {
		    	console.log("Student id was not found")
		    	res.status(400).json({"error": {"message": "No such student exists", "code": 400}});
		    	return
		    }
		    
    		collection.update({'id': exercise_id}, { $set: { 'students': updated_students } }, function(err, result) {
			    assert.equal(err, null);
				console.log("removed exercise student");
				res.status(200).json({"success": {"message" : "removed student from exercise", "code" : 200}});
				db.close();
			});
		});      
	}

	mongo.connect(MONGODB_URL, function(err, db) {
		assert.equal(null, err);
		update_document(db, req.params.id, req.params.student);
	});	
}

function remove_file_from_excersise_handler(req, res) { 
	var update_document = function(db, exercise_id, filename) { 
		var collection = db.collection('exercises');
		collection.find({'id': exercise_id}).toArray(function(err, docs) {
		    assert.equal(err, null);
		    assert.equal(1, docs.length);
		    console.log("Found the following records");
		    console.dir(docs);

		    var files = docs[0].files;
		    var updated_files = files.slice(0);
		    var file_removed = false
		    for (id in files) {
		    	if (files[id].path === filename) {
		    		console.log("File is removed");
		    		updated_files.splice(updated_files.indexOf(files[id]), 1);
		    		file_removed = true
		    	}
		    }

		    if (!file_removed) {
		    	console.log("file was not found")
		    	res.status(400).json({"error": {"message": "No such file exists", "code": 400}});
		    	return
		    }
		    
    		collection.update({'id': exercise_id}, { $set: { 'files': updated_files } }, function(err, result) {
			    assert.equal(err, null);
				console.log("removed exercise file");
                res.json({"success": {"message": "File removed succesfully", "code": 200}});
				db.close();

				fs.unlinkSync(__dirname + '/files/' + exercise_id + "_" + filename)

			});
		});      
	}

	

	mongo.connect(MONGODB_URL, function(err, db) {
		assert.equal(null, err);
		update_document(db, req.params.id, req.params.file);
	});
}

